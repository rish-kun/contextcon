"""A case's verify run ends with evaluate → request list, after every claim check.

Covers the scheduling gaps a review found: verify runs that never produced an
assessment or a request list, and claims left `not_checked` after a manual identity
pick. Fake clients only (see `tests.pipelines.verify.fakes`)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

import app.pipelines.verify  # noqa: F401 - registers the step handlers
from app.api.cases_deps import CaseActor
from app.api.cases_service import pick_identity
from app.api.schemas.cases import IdentityPickIn
from app.db.models import AssessmentVersion, Case, ClaimCheck, RequestList, Run, Step
from app.jobs import registry
from app.pipelines.evaluate.cases import case_out
from app.pipelines.verify import common
from app.pipelines.verify.checks.clients import set_client_factory
from app.pipelines.verify.claims.intake import (
    CHECK_HANDLER,
    add_typed_claim,
    schedule_claim_checks,
    verify_run_for_case,
)
from app.pipelines.verify.tail import ensure_assessment_tail
from tests.jobs.helpers import make_worker
from tests.pipelines import case_fakes
from tests.pipelines.verify.fakes import FakeFactory
from tests.pipelines.verify.test_checks import (
    CID,
    DOMAIN,
    NAME,
    PUNE,
    _case,
    _claims,
    _registry_evidence,
    intake_llm,
    pune_crustdata,
)

pytestmark = pytest.mark.asyncio

SENTENCES = [(s, c, comps) for s, c, comps, _ in PUNE[:2]]


async def _steps(session, run_id) -> dict[str, Step]:
    session.expire_all()
    rows = await session.execute(select(Step).where(Step.run_id == run_id))
    return {s.key: s for s in rows.scalars()}


async def _count(session, model, case_id) -> int:
    return await session.scalar(
        select(func.count()).select_from(model).where(model.case_id == case_id)
    )


async def _drain(sm) -> int:
    return await make_worker(sm, registry).drain()


async def test_verify_run_ends_with_assessment_and_request_list(sm, session) -> None:
    case = await _case(session)
    await _registry_evidence(session, case)
    llm = intake_llm(SENTENCES)
    await _claims(session, case, llm, SENTENCES)
    run = await verify_run_for_case(session, case)
    run_id, case_id = run.id, case.id
    set_client_factory(FakeFactory(llm_client=llm, crustdata_client=pune_crustdata()))
    await _drain(sm)

    steps = await _steps(session, run_id)
    checks = [k for k, s in steps.items() if s.handler == CHECK_HANDLER]
    assert checks and all(steps[k].state == "done" for k in checks)
    # evaluate waited for every check, including any deferred re-check added later
    assert set(checks) <= set(steps["evaluate"].depends_on)
    assert steps["evaluate"].state == "done" and steps["request_list"].state == "done"
    assert steps["request_list"].depends_on == ["evaluate"]
    assert all(steps[k].finished_at <= steps["evaluate"].started_at for k in checks)
    assert await _count(session, AssessmentVersion, case_id) == 1
    assert await _count(session, RequestList, case_id) == 1
    assert (await session.get(Run, run_id)).state == "done"
    out = await case_out(session, await session.get(Case, case_id))
    assert out.status.value == "assessed"

    # A claim added later re-opens the run and re-assesses with it.
    [late_sentence] = [(s, c, comps) for s, c, comps, _ in PUNE[3:4]]
    late_llm = intake_llm([late_sentence])
    late = await add_typed_claim(
        session,
        case=await session.get(Case, case_id),
        text=late_sentence[0],
        llm=late_llm,
        retention_days=30,
    )
    late_id = late.id
    added = await schedule_claim_checks(session, run_id=run_id, claims=[late])
    assert [s.key for s in added] == [f"checks.claim:{late_id}", "evaluate@2", "request_list@2"]
    await session.commit()
    set_client_factory(FakeFactory(llm_client=late_llm, crustdata_client=pune_crustdata()))
    await _drain(sm)
    steps = await _steps(session, run_id)
    assert steps["evaluate@2"].state == "done" and steps["request_list@2"].state == "done"
    assert steps["request_list@2"].depends_on == ["evaluate@2"]
    assert f"checks.claim:{late_id}" in steps["evaluate@2"].depends_on
    assert (await session.get(Run, run_id)).state == "done"


async def test_batches_join_a_pending_assessment(sm, session) -> None:
    """Claims queued while the closing evaluate is still pending join it: one
    assessment for both batches, with both batches' trigger documents."""
    case = await _case(session)
    llm = intake_llm(SENTENCES)
    run = await verify_run_for_case(session, case)
    run_id = run.id
    first, second = [
        await add_typed_claim(session, case=case, text=t, llm=llm, retention_days=30)
        for t, _, _ in SENTENCES
    ]
    second_id = second.id
    a = await schedule_claim_checks(session, run_id=run_id, claims=[first], document_ids=["d1"])
    b = await schedule_claim_checks(session, run_id=run_id, claims=[second], document_ids=["d2"])
    await session.commit()
    assert [s.key for s in a][1:] == ["evaluate", "request_list"]
    assert [s.key for s in b] == [f"checks.claim:{second_id}"]
    steps = await _steps(session, run_id)
    assert f"checks.claim:{second_id}" in steps["evaluate"].depends_on
    assert steps["evaluate"].input["document_ids"] == ["d1", "d2"]
    # a second call with nothing new is a no-op
    assert await ensure_assessment_tail(session, run_id=run_id) == []


async def test_manual_pick_rechecks_claims_then_assesses(sm, session, monkeypatch) -> None:
    case = await _case(session, identity="ambiguous")
    case.crustdata_company_id = None
    case.identity_candidates = [
        {
            "crustdata_company_id": cid,
            "name": name,
            "domains": [DOMAIN],
            "found_by": [],
            "matching": [],
            "differing": [],
            "confidence_score": 0.5,
        }
        for cid, name in ((CID, NAME), (CID + 1, f"{NAME} Holdings"))
    ]
    await session.commit()
    llm = intake_llm(SENTENCES)
    claims = await _claims(session, case, llm, SENTENCES)
    claim_ids = [c.id for c in claims]
    run = await verify_run_for_case(session, case)
    run_id, case_id, user_id, ws_id = run.id, case.id, case.created_by, case.workspace_id
    await session.commit()
    set_client_factory(FakeFactory(llm_client=llm, crustdata_client=pune_crustdata()))
    await _drain(sm)
    session.expire_all()
    statuses = (await session.execute(select(ClaimCheck.status))).scalars().all()
    assert set(statuses) == {"not_checked"}

    # The pick: identity-dependent steps use the CP-19 clients.
    profile_api = case_fakes.FakeCrustdata()
    profile_api.enrich[CID] = case_fakes.enrich_record(CID, NAME, DOMAIN)
    monkeypatch.setattr(common.clients, "crustdata", profile_api.factory)
    monkeypatch.setattr(common.clients, "llm", lambda ctx: case_fakes.FakeLlm())
    actor = CaseActor(workspace_id=ws_id, user_id=user_id, display_name="Analyst")
    await pick_identity(session, actor, str(case_id), IdentityPickIn(crustdata_company_id=CID))
    await _drain(sm)

    # The claims run had no identity step, so the pick opened a verify run of its own.
    pick_run = await session.scalar(
        select(Run.id).where(Run.case_id == case_id).order_by(Run.created_at.desc()).limit(1)
    )
    assert pick_run != run_id
    steps = await _steps(session, pick_run)
    for claim_id in claim_ids:
        recheck = steps[f"checks.claim:{claim_id}"]
        assert recheck.state == "done"
        assert "verify.profile" in recheck.depends_on
        assert recheck.key in steps["evaluate"].depends_on
        latest = await session.scalar(
            select(ClaimCheck).where(
                ClaimCheck.claim_id == claim_id, ClaimCheck.step_id == recheck.id
            )
        )
        assert latest is not None and latest.status != "not_checked"
    assert steps["evaluate"].state == "done" and steps["request_list"].state == "done"
    assert await _count(session, AssessmentVersion, case_id) >= 1
    assert await _count(session, RequestList, case_id) >= 1
    out = await case_out(session, await session.get(Case, case_id))
    assert out.status.value == "assessed"
