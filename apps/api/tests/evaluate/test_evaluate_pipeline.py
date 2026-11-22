"""CP-22: the evaluate step and immutable assessment versions."""

import pytest
from sqlalchemy import func, select

from app.db.models import AssessmentVersion, Case, Run, Step
from app.jobs import StepRegistry, StepSpec, create_run
from app.jobs import registry as default_registry
from app.pipelines import evaluate
from app.pipelines.evaluate import step as evaluate_step_module
from tests.evaluate.builders import (
    INDIA_MUST,
    TODAY,
    add_payroll,
    api_client,
    confirmed_world,
    thesis,
)
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


async def _versions(session, case_id) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(AssessmentVersion)
        .where(AssessmentVersion.case_id == case_id)
    )


async def _evaluate(session, w, **kw):
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY, **kw)
    await session.commit()
    return out


async def test_first_version_then_same_inputs_give_no_new_version(session) -> None:
    w = await confirmed_world(session)
    first = await _evaluate(session, w)
    assert first.created and first.version.version == 1
    assert first.version.diff_from_previous is None
    assert first.assessment.judgments.opportunity_fit.fit == 100  # India + 180 >= 100

    again = await _evaluate(session, w)
    assert not again.created
    assert again.version.id == first.version.id
    assert await _versions(session, w.t.case.id) == 1


async def test_later_day_with_nothing_changed_is_not_a_new_version(session) -> None:
    w = await confirmed_world(session)
    await _evaluate(session, w)
    later = await evaluate.evaluate_case(
        session, w.t.workspace.id, w.t.case.id, today=TODAY.replace(day=23)
    )
    assert not later.created


async def test_changed_claim_gives_new_version_with_diff_naming_the_reason(session) -> None:
    w = await confirmed_world(session)
    v1 = await _evaluate(session, w)
    claim_id = str(w.claim.id)
    assert {o.claim_id: o.status.value for o in v1.assessment.outcomes} == {
        claim_id: "cannot_verify"
    }

    payroll = await add_payroll(session, w)
    v2 = await _evaluate(session, w, trigger="seller documents payroll_summary.pdf")
    assert v2.created and v2.version.version == 2
    assert v2.version.previous_version_id == v1.version.id
    change = v2.diff.claim_changes[0]
    assert (change.claim_id, change.before.value, change.after.value) == (
        claim_id,
        "cannot_verify",
        "supported",
    )
    assert str(payroll.id) in change.evidence_added
    assert "payroll_summary.pdf, p. 2" in change.reason
    assert "seller_document" in change.reason

    # The earlier view is kept, unchanged.
    rows = (
        (
            await session.execute(
                select(AssessmentVersion)
                .where(AssessmentVersion.case_id == w.t.case.id)
                .order_by(AssessmentVersion.version)
            )
        )
        .scalars()
        .all()
    )
    assert [r.version for r in rows] == [1, 2]
    assert rows[0].inputs_hash == v1.version.inputs_hash
    assert evaluate.stored_assessment(rows[0]).outcomes[0].status.value == "cannot_verify"

    out = await evaluate.list_versions_out(session, w.t.case.id, list(rows))
    line = next(d for d in out[1].diff_from_previous if d.kind == "claim")
    assert line.subject == "We have 250 employees"
    assert line.before == "cannot_verify" and line.after == "supported"
    assert "payroll_summary.pdf, p. 2" in line.because
    assert [e.quote for e in line.evidence] == ["Total employees on payroll: 250"]


async def test_identity_unresolved_cannot_assess(session) -> None:
    w = await confirmed_world(session, identity="ambiguous")
    out = await _evaluate(session, w)
    assert out.assessment.disposition.value == "cannot_assess"
    assert out.assessment.judgments.disposition.rule == "identity_uncertain"
    [view] = await evaluate.list_versions_out(session, w.t.case.id, [out.version])
    assert view.judgments.opportunity_fit.state == "identity_unresolved"
    assert view.judgments.opportunity_fit.fit is None


async def test_zero_assessable_criteria_gives_fit_unavailable(session) -> None:
    w = await confirmed_world(session, with_thesis=False)
    unknowable = {
        "label": "Serves hospitals",
        "kind": "preference",
        "dimension": "customer_type",
        "operator": "eq",
        "value": "hospitals",
    }
    await thesis(session, w.t, [unknowable])
    await session.commit()
    out = await _evaluate(session, w)
    fit = out.assessment.judgments.opportunity_fit
    assert fit.fit is None and fit.assessable_pct == 0
    assert out.assessment.disposition.value == "cannot_assess"
    [view] = await evaluate.list_versions_out(session, w.t.case.id, [out.version])
    assert view.judgments.opportunity_fit.state == "unavailable"
    assert view.judgments.opportunity_fit.fit is None


async def test_direct_verify_waits_for_strategy_criteria_then_scores(sm, session) -> None:
    w = await confirmed_world(session, with_thesis=False)
    v1 = await _evaluate(session, w)
    [view] = await evaluate.list_versions_out(session, w.t.case.id, [v1.version])
    assert view.judgments.opportunity_fit.state == "awaiting_strategy_criteria"
    assert view.judgments.opportunity_fit.fit is None
    assert v1.assessment.disposition.value == "cannot_assess"

    async with api_client(sm, w.t.workspace.id, w.t.user.id) as client:
        body = {
            "criteria": [
                {k: v for k, v in INDIA_MUST.items() if k != "crustdata_filter"}
                | {"crustdata_filter": None}
            ]
        }
        res = await client.put(f"/cases/{w.t.case.id}/criteria", json=body)
    assert res.status_code == 200, res.text
    run = res.json()["run"]
    assert run["kind"] == "evaluate"
    [step] = run["steps"]
    assert step["key"] == "evaluate"

    worker = make_worker(sm, default_registry)
    assert await worker.run_once()
    async with sm() as s:
        row = (await s.execute(select(Step).where(Step.run_id == run["id"]))).scalar_one()
        assert row.state == "done", row.error
        assert row.output["created"] is True and row.output["version"] == 2
        latest = (
            (
                await s.execute(
                    select(AssessmentVersion)
                    .where(AssessmentVersion.case_id == w.t.case.id)
                    .order_by(AssessmentVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
        assert latest.trigger == "strategy criteria updated"
        [out] = await evaluate.list_versions_out(s, w.t.case.id, [latest])
    assert out.judgments.opportunity_fit.state == "scored"
    assert out.judgments.opportunity_fit.fit == 100
    assert out.judgments.opportunity_fit.criterion_results[0].label == "Based in India"


async def test_evaluate_step_costs_nothing_and_tolerates_failed_steps() -> None:
    spec = evaluate.evaluate_step(depends_on=["identity", "profile"])
    assert spec.handler == "evaluate.assess"
    assert spec.uses_budget is False
    assert spec.tolerate_failed_deps is True
    assert default_registry.get("evaluate.assess") is evaluate_step_module.assess_case


async def test_step_runs_after_a_failed_dependency(sm, session) -> None:
    w = await confirmed_world(session)
    reg = StepRegistry()

    async def boom(ctx):
        raise RuntimeError("provider down")

    reg.register("test.boom", boom)
    reg.register("evaluate.assess", evaluate_step_module.assess_case)
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="verify",
        case_id=w.t.case.id,
        steps=[
            StepSpec("profile", "test.boom", max_attempts=1),
            evaluate.evaluate_step(depends_on=["profile"]),
        ],
    )
    await session.commit()
    worker = make_worker(sm, reg)
    while await worker.run_once():
        pass
    async with sm() as s:
        steps = {
            st.key: st
            for st in (await s.execute(select(Step).where(Step.run_id == run.id))).scalars()
        }
        assert steps["profile"].state == "failed"
        assert steps["evaluate"].state == "done"
        assert steps["evaluate"].output["version"] == 1
        assert "assessed with unfinished steps: profile" in steps["evaluate"].output["_log"]
        assert (await s.get(Run, run.id)).state in ("done", "failed")
        assert (await s.get(Case, w.t.case.id)) is not None


async def test_assessments_route_lists_history_with_diffs(sm, session) -> None:
    w = await confirmed_world(session)
    await _evaluate(session, w)
    await add_payroll(session, w)
    await _evaluate(session, w)
    async with api_client(sm, w.t.workspace.id) as client:
        res = await client.get(f"/cases/{w.t.case.id}/assessments")
        other = await client.get("/cases/00000000-0000-0000-0000-000000000000/assessments")
    assert res.status_code == 200, res.text
    body = res.json()
    assert [v["version"] for v in body] == [1, 2]
    assert body[0]["diff_from_previous"] is None
    kinds = {d["kind"] for d in body[1]["diff_from_previous"]}
    assert "claim" in kinds
    assert other.status_code == 404


async def test_case_routes_need_a_session() -> None:
    import httpx2 as httpx

    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.get("/cases/00000000-0000-0000-0000-000000000000/assessments")
    assert res.status_code == 401
