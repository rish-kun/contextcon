"""CP-23 request list: assessment → documents → drafted message revision, on Postgres."""

import json
import uuid
from contextlib import asynccontextmanager

import httpx2 as httpx
import pytest
from sqlalchemy import func, select

from app.act.models import Actor, MessageStatus, SendStatus, ValidationError
from app.act.pg_repository import PostgresActRepository
from app.act.service import ActService, SendConfig
from app.api import requests as requests_api
from app.auth.deps import current_user
from app.auth.sessions import AuthUser
from app.db.models import (
    Approval,
    Claim,
    MessageRevision,
    RequestItem,
    RequestItemClaim,
    RequestList,
    Run,
    Step,
)
from app.jobs import StepSpec, create_run
from app.jobs import registry as default_registry
from app.jobs.purge import SCRUBBED_CLAIM_TEXT
from app.main import create_app
from app.pipelines import act as act_pipeline
from app.pipelines import evaluate
from app.pipelines.act import llm as llm_module
from app.pipelines.act.request_list import NoAssessment, build_request_list_for_case
from tests.act.fakes import send_current
from tests.evaluate.builders import TODAY, confirmed_world
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


class FakeLlm:
    """Drafts a valid email naming every requested document, and counts calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def draft_text(self, system: str, user: str):
        self.calls += 1
        payload = json.loads(user.split("\n", 1)[1])
        lines = ["Subject: Documents for our review", "", "Hello,", ""]
        lines += [f"- {d['document']}" for d in payload["documents"]]
        lines += ["", "Thank you."]
        return "\n".join(lines), None


async def _world(session):
    w = await confirmed_world(session)
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    await session.commit()
    return w, out


async def test_builds_items_links_and_a_draft_revision(session) -> None:
    w, out = await _world(session)
    llm = FakeLlm()
    built = await build_request_list_for_case(
        session, w.t.workspace.id, w.t.case.id, llm=llm, sender_name="Test analyst"
    )
    await session.commit()
    assert built.created and llm.calls == 1

    rl = await session.get(RequestList, built.request_list.id)
    assert rl.assessment_version_id == out.version.id and rl.status == "draft"
    items = (
        (
            await session.execute(
                select(RequestItem)
                .where(RequestItem.request_list_id == rl.id)
                .order_by(RequestItem.position)
            )
        )
        .scalars()
        .all()
    )
    expected = out.assessment.requests.documents
    assert [i.document_requested for i in items] == [d.document for d in expected]
    for item, doc in zip(items, expected, strict=True):
        links = (
            await session.execute(
                select(RequestItemClaim.claim_id).where(RequestItemClaim.request_item_id == item.id)
            )
        ).scalars()
        assert sorted(str(c) for c in links) == sorted(doc.claim_ids)
        assert item.reason and "We have 250 employees" not in item.reason  # no claim text copied

    (revision,) = (
        (
            await session.execute(
                select(MessageRevision).where(MessageRevision.request_list_id == rl.id)
            )
        )
        .scalars()
        .all()
    )
    assert revision.revision == 1 and revision.recipient == "" and revision.created_by is None
    for doc in expected:  # test_draft_contains_every_item
        assert doc.document in revision.body
    assert (await session.scalar(select(func.count()).select_from(Approval))) == 0


async def test_same_assessment_version_is_built_once(session) -> None:
    w, _ = await _world(session)
    llm = FakeLlm()
    first = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=llm)
    await session.commit()
    again = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=llm)
    assert not again.created and again.request_list.id == first.request_list.id
    assert llm.calls == 1
    assert await session.scalar(select(func.count()).select_from(RequestList)) == 1
    assert await session.scalar(select(func.count()).select_from(MessageRevision)) == 1


async def test_no_assessment_means_nothing_to_build(session) -> None:
    w = await confirmed_world(session)
    with pytest.raises(NoAssessment):
        await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)


async def test_draft_is_an_act_message_that_needs_a_recipient_then_sends_once(session, sm) -> None:
    w, _ = await _world(session)
    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    case_id, message_id = str(w.t.case.id), str(built.request_list.id)
    actor = Actor(user_id=str(w.t.user.id), display_name=w.t.user.display_name)
    service = ActService(PostgresActRepository(sm), SendConfig(enabled=False))

    state = await service.get_state(case_id, message_id)
    assert state.status is MessageStatus.DRAFT and state.approval is None
    with pytest.raises(ValidationError):  # no recipient typed in yet
        await service.approve(case_id, message_id, actor, revision_id=state.current_revision.id)

    edited = await service.revise(
        case_id,
        message_id,
        actor,
        subject=state.current_revision.subject,
        body=state.current_revision.body,
        recipient="cfo@seller.example",
    )
    approved = await service.approve(
        case_id, message_id, actor, revision_id=edited.current_revision.id
    )
    assert approved.status is MessageStatus.APPROVED
    send = await send_current(service, case_id, message_id, actor)
    assert send.status is SendStatus.SUPPRESSED_TEST_MODE


async def test_step_handler_builds_the_list_in_a_run(session, sm, monkeypatch) -> None:
    w, out = await _world(session)
    llm = FakeLlm()

    @asynccontextmanager
    async def fake_factory(*_args):
        yield llm

    monkeypatch.setattr(llm_module, "llm_factory", fake_factory)
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="evaluate",
        case_id=w.t.case.id,
        steps=[StepSpec(act_pipeline.STEP_KEY, act_pipeline.HANDLER, uses_budget=False)],
    )
    await session.commit()
    worker = make_worker(sm, default_registry)
    assert await worker.run_once()
    async with sm() as s:
        step = (await s.execute(select(Step).where(Step.run_id == run.id))).scalar_one()
        assert step.state == "done", step.error
        assert step.output["created"] is True
        assert step.output["items"] == len(out.assessment.requests.documents)
        rl = await s.get(RequestList, uuid.UUID(step.output["request_list_id"]))
        assert rl.assessment_version_id == out.version.id
        assert (await s.get(Run, run.id)).state == "done"
    assert llm.calls == 1
    assert "act.request_list" in default_registry.names()
    spec = act_pipeline.request_list_step()
    assert spec.depends_on == ("evaluate", "decision_flip")
    assert spec.tolerate_failed_deps is True  # a failed analysis never blocks Act


def _client(sm, user: AuthUser) -> httpx.AsyncClient:
    app = create_app()

    async def as_user() -> AuthUser:
        return user

    async def db():
        async with sm() as s:
            yield s

    app.dependency_overrides[current_user] = as_user
    app.dependency_overrides[requests_api.requests_session] = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_post_and_get_requests_routes(session, sm, monkeypatch) -> None:
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)

    @asynccontextmanager
    async def no_llm(*_args):
        yield None

    monkeypatch.setattr(llm_module, "llm_factory", no_llm)
    w = await confirmed_world(session)
    user = AuthUser(
        id=w.t.user.id,
        workspace_id=w.t.workspace.id,
        email=w.t.user.email,
        display_name=w.t.user.display_name,
    )
    path = f"/cases/{w.t.case.id}/requests"
    async with _client(sm, user) as client:
        assert (await client.get(path)).status_code == 404
        early = await client.post(path)
        assert early.status_code == 409 and "assessment" in early.json()["detail"]

        await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
        await session.commit()
        created = await client.post(path)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["case_id"] == str(w.t.case.id) and body["assessment_version"] == 1
        assert body["message_id"] == body["id"]
        assert body["email_send_enabled"] is False
        assert body["items"] and all(i["questions"] for i in body["items"])
        claim_items = [i for i in body["items"] if i["claim_ids"]]
        assert any('"We have 250 employees"' in q for i in claim_items for q in i["questions"])
        assert body["draft"]["subject"] and body["draft"]["body"]
        assert all(i["document"] in body["draft"]["body"] for i in body["items"])

        again = await client.post(path)
        assert again.json()["id"] == body["id"]
        fetched = await client.get(path)
        assert fetched.status_code == 200 and fetched.json() == body

        # Questions are rendered from the claims, so retention scrubbing shows through.
        claim = (await session.execute(select(Claim))).scalars().first()
        claim.original_text = SCRUBBED_CLAIM_TEXT
        await session.commit()
        scrubbed = (await client.get(path)).json()
        flat = [q for i in scrubbed["items"] for q in i["questions"]]
        assert not any("250 employees" in q for q in flat)
        assert any(SCRUBBED_CLAIM_TEXT in q for q in flat)

        stranger = AuthUser(
            id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="x@y.example", display_name="X"
        )
    async with _client(sm, stranger) as client:
        assert (await client.get(path)).status_code == 404
        assert (await client.post(path)).status_code == 404


async def test_settings_llm_is_off_without_a_key_and_case_scoped_with_one(sm, monkeypatch) -> None:
    from types import SimpleNamespace

    from pydantic import SecretStr

    from app.clients.llm import LLMClient
    from app.db.ledger import CostContext

    cost = CostContext(workspace_id=uuid.uuid4(), case_id=uuid.uuid4())
    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: SimpleNamespace(anthropic_api_key=SecretStr(""), upload_retention_days=30),
    )
    async with llm_module.settings_llm(sm, cost) as llm:
        assert llm is None

    from app.settings import Settings

    keyed = Settings(_env_file=None, anthropic_api_key="test-key")
    monkeypatch.setattr(llm_module, "get_settings", lambda: keyed)
    monkeypatch.setattr("app.clients.llm.get_settings", lambda: keyed)
    async with llm_module.settings_llm(sm, cost) as llm:
        assert isinstance(llm, LLMClient)
        assert llm.cache.confidential and llm.cache.ctx.case_id == cost.case_id


async def test_case_detail_shows_request_list_and_message_through_send(session, sm) -> None:
    """Live case detail carries the request list and the Act message state, so the UI can
    reach approve and send: approver name and time, send status and test mode."""
    from tests.evaluate.builders import api_client

    w, _ = await _world(session)
    case_id = str(w.t.case.id)
    async with api_client(sm, w.t.workspace.id) as client:
        before = (await client.get(f"/cases/{case_id}")).json()
    assert before["request_list"] is None and before["message"] is None

    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    message_id = str(built.request_list.id)
    async with api_client(sm, w.t.workspace.id) as client:
        body = (await client.get(f"/cases/{case_id}")).json()
    rl = body["request_list"]
    assert rl["id"] == message_id and rl["message_id"] == message_id
    assert rl["assessment_version"] == 1 and rl["email_send_enabled"] is False
    assert rl["items"] and all(i["questions"] for i in rl["items"])
    assert any(i["claim_ids"] for i in rl["items"])
    msg = body["message"]
    assert msg["id"] == message_id and msg["status"] == "draft"
    assert msg["current_revision"]["number"] == 1 and msg["approval"] is None

    actor = Actor(user_id=str(w.t.user.id), display_name=w.t.user.display_name)
    service = ActService(PostgresActRepository(sm), SendConfig(enabled=False))
    state = await service.get_state(case_id, message_id)
    edited = await service.revise(
        case_id,
        message_id,
        actor,
        subject=state.current_revision.subject,
        body=state.current_revision.body,
        recipient="cfo@seller.example",
    )
    await service.approve(case_id, message_id, actor, revision_id=edited.current_revision.id)
    async with api_client(sm, w.t.workspace.id) as client:
        approved = (await client.get(f"/cases/{case_id}")).json()["message"]
    assert approved["status"] == "approved"
    assert approved["current_revision"]["number"] == 2
    assert approved["approval"]["approver_display_name"] == w.t.user.display_name
    assert approved["approval"]["approved_at"]

    await send_current(service, case_id, message_id, actor)
    async with api_client(sm, w.t.workspace.id) as client:
        sent = (await client.get(f"/cases/{case_id}")).json()["message"]
    assert sent["status"] == "suppressed_test_mode"
    assert sent["send"]["test_mode"] is True and sent["send"]["status"] == "suppressed_test_mode"
