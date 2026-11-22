"""CP-24: a seller response answers request items and starts a recheck run."""

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

import app.pipelines.verify.claims.steps  # noqa: F401  (registers the step handlers)
from app.auth import sessions
from app.db.models import (
    AssessmentVersion,
    Claim,
    DocumentRequestItem,
    RequestItem,
    RequestItemClaim,
    RequestList,
    Run,
    Step,
)
from app.jobs import registry
from app.pipelines import evaluate
from app.pipelines.act import llm as act_llm
from app.pipelines.act.request_list import build_request_list_for_case
from app.pipelines.evaluate import step as evaluate_step_module
from app.pipelines.verify.checks.clients import set_client_factory
from app.pipelines.verify.claims.intake import CHECK_HANDLER
from tests.auth.helpers import PASSWORD, login
from tests.documents.conftest import make_pdf
from tests.evaluate.builders import TODAY, confirmed_world
from tests.jobs.helpers import make_worker
from tests.pipelines.verify.fakes import FakeCrustdata, FakeFactory, RoutedLlm, claims_draft

pytestmark = pytest.mark.asyncio

PDF = "application/pdf"


@pytest.fixture(autouse=True)
def _no_models(monkeypatch):
    @asynccontextmanager
    async def no_llm(*_args):
        yield None

    monkeypatch.setattr(act_llm, "llm_factory", no_llm)
    monkeypatch.setattr(evaluate_step_module, "memo_llm", lambda ctx: None)


async def _world_with_requests(session):
    w = await confirmed_world(session)
    await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    await session.commit()
    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    item = (
        await session.execute(
            select(RequestItem)
            .join(RequestItemClaim, RequestItemClaim.request_item_id == RequestItem.id)
            .where(
                RequestItem.request_list_id == built.request_list.id,
                RequestItemClaim.claim_id == w.claim.id,
            )
        )
    ).scalar_one()
    user = await sessions.create_user(
        session,
        w.t.workspace.id,
        email=f"recheck-{uuid.uuid4().hex[:6]}@fund.example",
        display_name="Recheck Analyst",
        password=PASSWORD,
    )
    await session.commit()
    return w, item, user


def _upload(client, case_id, data, *, kind="seller_response", answers=()):
    return client.post(
        f"/cases/{case_id}/documents",
        files={"file": ("payroll.pdf", data, PDF)},
        data={"kind": kind, "answers_request_item_ids": list(answers)},
    )


def _payroll_llm():
    return RoutedLlm(
        responders={
            "ClaimsDraft": claims_draft(
                {
                    "assertion": "Payroll lists 250 employees",
                    "category": "team_size",
                    "components": [{"name": "count", "value": "250"}],
                    "quote": "Payroll lists 250 employees",
                    "page": 1,
                }
            ),
            "NormaliseDraft": {
                "claims": [{"index": 0, "components": [{"name": "employee_count", "value": "250"}]}]
            },
        }
    )


async def test_seller_response_links_items_and_runs_a_recheck(api, client, session, sm):
    w, item, user = await _world_with_requests(session)
    assert (await login(client, user.email)).status_code == 200
    set_client_factory(FakeFactory(llm_client=_payroll_llm(), crustdata_client=FakeCrustdata()))

    response = await _upload(
        client, w.t.case.id, make_pdf(["Payroll lists 250 employees"]), answers=[str(item.id)]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["answers_request_item_ids"] == [str(item.id)]
    assert body["run"] is not None and body["run"]["kind"] == "recheck"
    doc_id = uuid.UUID(body["id"])
    links = (await session.execute(select(DocumentRequestItem))).scalars().all()
    assert [(link.document_id, link.request_item_id) for link in links] == [(doc_id, item.id)]

    await make_worker(sm, registry).drain()

    run = await session.get(Run, uuid.UUID(body["run"]["id"]), populate_existing=True)
    assert run.state == "done", run.error
    steps = {
        s.key: s
        for s in (await session.execute(select(Step).where(Step.run_id == run.id))).scalars()
    }
    extract = steps[f"claims.extract:{doc_id}"]
    assert extract.label == "Read claims from the uploaded PDF"
    assert extract.result == "1 claim read from the uploaded PDF"
    new_claim = (
        await session.execute(select(Claim).where(Claim.document_id == doc_id))
    ).scalar_one()
    checks = [k for k, s in steps.items() if s.handler == CHECK_HANDLER]
    # The new claim and the claim behind the answered item are both checked, and
    # neither waits for (or defers behind) the evaluate step that follows them.
    assert set(checks) == {f"checks.claim:{new_claim.id}", f"checks.claim:{w.claim.id}"}
    assert not any("evaluate" in steps[k].depends_on for k in checks)
    assert all(s.state == "done" for s in steps.values()), {
        k: (s.state, s.error) for k, s in steps.items()
    }
    assert set(checks) <= set(steps["evaluate"].depends_on)
    assert steps["decision_flip"].depends_on == ["evaluate"]
    assert steps["request_list"].depends_on == ["evaluate", "decision_flip"]

    latest = (
        await session.execute(
            select(AssessmentVersion)
            .where(AssessmentVersion.case_id == w.t.case.id)
            .order_by(AssessmentVersion.version.desc())
            .limit(1)
        )
    ).scalar_one()
    assert latest.version == 2
    assert [str(d) for d in latest.trigger_document_ids] == [str(doc_id)]
    lists = (
        await session.execute(select(RequestList).where(RequestList.case_id == w.t.case.id))
    ).scalars()
    assert latest.id in {rl.assessment_version_id for rl in lists}

    detail = (await client.get(f"/cases/{w.t.case.id}")).json()
    [doc] = [d for d in detail["documents"] if d["id"] == str(doc_id)]
    assert doc["kind"] == "seller_response"
    assert doc["answers_request_item_ids"] == [str(item.id)]


async def test_answered_items_must_belong_to_the_case(api, client, session):
    w, item, user = await _world_with_requests(session)
    assert (await login(client, user.email)).status_code == 200
    pdf = make_pdf(["Payroll lists 250 employees"])
    for bad in ([str(uuid.uuid4())], ["not-a-uuid"]):
        res = await _upload(client, w.t.case.id, pdf, answers=bad)
        assert res.status_code == 422, res.text
    other = await _upload(client, w.t.case.id, pdf, kind="seller_deck", answers=[str(item.id)])
    assert other.status_code == 422, other.text
    assert (await session.execute(select(DocumentRequestItem))).first() is None
