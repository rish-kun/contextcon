"""B2: DecisionFlip persistence and the `evaluate.decision_flip` step.

Order (assess → decision_flip → request_list), idempotency by `analysis_key`,
immutability, workspace scoping, the `hypothetical` marking, and restart recovery
when a worker dies mid-step.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.api import fixture_decision_flip as fx
from app.db import repo
from app.db.models import AssessmentVersion, ImmutableRowError, Run, Step
from app.db.models import DecisionFlipAnalysis as FlipRow
from app.db.repo import NotFound
from app.domain.enums import ClaimStatus
from app.jobs import StepContext, StepRegistry, create_run
from app.pipelines import evaluate
from app.pipelines.act import request_list_step
from app.pipelines.evaluate import flip as flip_service
from app.pipelines.evaluate import flip_step
from app.pipelines.evaluate import step as assess_module
from app.pipelines.evaluate.cases import queue_evaluation
from app.rules.decision_flip import FLIP_VERSION
from tests.db.factories import tenant
from tests.evaluate.builders import TODAY, confirmed_world
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


# --- Helpers -------------------------------------------------------------------------


def _registry(request_list_calls: list[dict[str, Any]] | None = None) -> StepRegistry:
    """The real assess and flip handlers; the request list only records what it saw."""
    reg = StepRegistry()
    reg.register(evaluate.HANDLER, assess_module.assess_case)
    reg.register(flip_step.HANDLER, flip_step.decision_flip)

    async def request_list(ctx: StepContext) -> dict:
        if request_list_calls is not None:
            request_list_calls.append(
                {k: (d["state"], d["output"]) for k, d in ctx.dependencies.items()}
            )
        return {}

    reg.register("act.request_list", request_list)
    return reg


async def _rows(sm, case_id) -> list[FlipRow]:
    async with sm() as s:
        rows = await s.execute(select(FlipRow).where(FlipRow.case_id == case_id))
        return list(rows.scalars())


async def _steps(sm, run_id) -> dict[str, Step]:
    async with sm() as s:
        rows = await s.execute(select(Step).where(Step.run_id == run_id))
        return {st.key: st for st in rows.scalars()}


async def _assess_run(session, w):
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="verify",
        case_id=w.t.case.id,
        steps=[evaluate.evaluate_step(), flip_step.decision_flip_step(), request_list_step()],
    )
    await session.commit()
    return run


async def _crash_mid_step(sm, run_id, key: str) -> None:
    """Leave a step `running` with an expired lease, as a killed worker would."""
    async with sm() as s:
        await s.execute(
            update(Step)
            .where(Step.run_id == run_id, Step.key == key)
            .values(
                state="running",
                attempts=Step.attempts + 1,
                lease_owner="dead-worker",
                lease_until=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1),
            )
        )
        await s.commit()


def _walk_outcomes(node: Any) -> list[dict]:
    """Every simulated outcome or set in a serialised analysis."""
    found: list[dict] = []
    if isinstance(node, dict):
        if "disposition" in node and "rule" in node or "item_ids" in node and "outcome" in node:
            found.append(node)
        for v in node.values():
            found += _walk_outcomes(v)
    elif isinstance(node, list):
        for v in node:
            found += _walk_outcomes(v)
    return found


async def _stored_version(session, t, statuses, results=None, **kw):
    """A stored version built by the rules from fixture outcomes (no case records)."""
    v, _, _ = fx.fixture_version(str(t.case.id), 1, statuses, results, **kw)
    row = await repo.add_assessment_version(
        session,
        t.workspace.id,
        t.case.id,
        policy_version=v.policy_version,
        inputs_hash=v.inputs_hash,
        judgments={"assessment": v.model_dump(mode="json")},
        disposition=v.disposition.value,
        reasons=list(v.judgments.disposition.reasons),
    )
    await session.commit()
    return row


# --- The step and its place in the plans ----------------------------------------------


async def test_step_spec_costs_nothing_and_follows_its_assessment() -> None:
    spec = flip_step.decision_flip_step()
    assert (spec.key, spec.handler) == ("decision_flip", "evaluate.decision_flip")
    assert spec.depends_on == ("evaluate",)
    assert spec.uses_budget is False and spec.tolerate_failed_deps is True
    second = flip_step.decision_flip_step(after="evaluate@2")
    assert (second.key, second.depends_on) == ("decision_flip@2", ("evaluate@2",))
    assert request_list_step().depends_on == ("evaluate", "decision_flip")


async def test_step_runs_after_assess_and_before_the_request_list(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    calls: list[dict] = []
    run = await _assess_run(session, w)
    await make_worker(sm, _registry(calls)).drain()
    steps = await _steps(sm, run.id)
    assert {k: s.state for k, s in steps.items()} == {
        "evaluate": "done",
        "decision_flip": "done",
        "request_list": "done",
    }
    assert steps["evaluate"].finished_at <= steps["decision_flip"].started_at
    assert steps["decision_flip"].finished_at <= steps["request_list"].started_at
    out = steps["decision_flip"].output
    assert out["created"] is True
    assert out["assessment_version_id"] == steps["evaluate"].output["assessment_version_id"]
    # The request list saw both: the version and its analysis.
    [seen] = calls
    assert seen["decision_flip"][0] == "done"
    assert seen["decision_flip"][1]["analysis_id"] == out["analysis_id"]
    [row] = await _rows(sm, case_id)
    assert str(row.id) == out["analysis_id"] and row.run_id == run.id
    assert row.flip_version == FLIP_VERSION
    assert row.blocker_count == out["blocker_count"]


async def test_manual_evaluate_and_criteria_runs_schedule_the_step(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    run = await queue_evaluation(session, w.t.case, trigger="manual re-run")
    await session.commit()
    keys = [(s.key, list(s.depends_on)) for s in (await _steps(sm, run.id)).values()]
    assert sorted(keys) == [
        ("decision_flip", ["evaluate"]),
        ("evaluate", []),
        ("request_list", ["evaluate", "decision_flip"]),
    ]
    calls: list[dict[str, Any]] = []
    await make_worker(sm, _registry(calls)).drain()
    assert len(await _rows(sm, case_id)) == 1
    # The criteria/manual re-evaluation also redrafts the request list, after both steps.
    assert len(calls) == 1
    assert set(calls[0]) == {"evaluate", "decision_flip"}


async def test_step_runs_when_assessment_fails_and_reports_no_version(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    reg = _registry()

    async def boom(ctx):
        raise RuntimeError("down")

    reg.register(evaluate.HANDLER, boom, replace=True)
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="evaluate",
        case_id=w.t.case.id,
        steps=[evaluate.evaluate_step(), flip_step.decision_flip_step()],
        max_attempts=1,
    )
    await session.commit()
    await make_worker(sm, reg).drain()
    steps = await _steps(sm, run.id)
    assert steps["evaluate"].state == "failed"
    assert steps["decision_flip"].state == "done"
    assert steps["decision_flip"].result == "No assessment yet: nothing to analyse"
    assert await _rows(sm, case_id) == []


async def test_step_runs_when_the_budget_is_spent(sm, session) -> None:
    w = await confirmed_world(session)
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="verify",
        case_id=w.t.case.id,
        budget_credits=0,
        steps=[evaluate.evaluate_step(), flip_step.decision_flip_step()],
    )
    await session.commit()
    await make_worker(sm, _registry()).drain()
    steps = await _steps(sm, run.id)
    assert steps["decision_flip"].state == "done"


# --- Idempotency ------------------------------------------------------------------------


async def test_idempotent_by_analysis_key(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    first = await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    await session.commit()
    again = await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    await session.commit()
    assert first.created and not again.created
    assert again.row.id == first.row.id
    assert again.analysis == first.analysis
    assert len(await _rows(sm, case_id)) == 1


async def test_unchanged_inputs_rerun_writes_no_new_analysis(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    for _ in range(2):
        run = await queue_evaluation(session, w.t.case, trigger="manual re-run")
        await session.commit()
        await make_worker(sm, _registry()).drain()
    steps = await _steps(sm, run.id)
    assert steps["evaluate"].output["created"] is False
    assert steps["decision_flip"].output["created"] is False
    assert steps["decision_flip"].result.startswith("No change")
    assert len(await _rows(sm, case_id)) == 1


# --- Immutability -------------------------------------------------------------------


async def test_rows_are_immutable(session) -> None:
    w = await confirmed_world(session)
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    result = await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    await session.commit()
    row = result.row
    row_id = row.id
    row.state = "no_blockers"
    with pytest.raises(ImmutableRowError):
        await session.flush()
    await session.rollback()
    for sql in (
        "UPDATE decision_flip_analyses SET state = 'x' WHERE id = :id",
        "DELETE FROM decision_flip_analyses WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(text(sql), {"id": row_id})
        await session.rollback()


# --- Workspace scoping --------------------------------------------------------------


async def test_another_workspace_cannot_analyse_or_read(session) -> None:
    w = await confirmed_world(session)
    other = await tenant(session, "other")
    case_id, ws_id, other_ws = w.t.case.id, w.t.workspace.id, other.workspace.id
    out = await evaluate.evaluate_case(session, ws_id, case_id, today=TODAY)
    await session.commit()
    version_id = out.version.id
    with pytest.raises(NotFound):
        await flip_service.flip_for_version(session, other_ws, out.version)
    await session.rollback()
    version = await session.get(AssessmentVersion, version_id)
    await flip_service.flip_for_version(session, ws_id, version)
    await session.commit()
    assert await flip_service.flip_of_version(session, other_ws, version_id) is None
    assert await flip_service.latest_flip(session, other_ws, case_id) is None
    assert await flip_service.flip_of_version(session, ws_id, version_id) is not None
    # The database refuses a row whose case is in another workspace.
    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                "INSERT INTO decision_flip_analyses (id, workspace_id, case_id, "
                "assessment_version_id, analysis_key, policy_version, inputs_hash, "
                "flip_version, state, blocker_count, payload) VALUES (gen_random_uuid(), "
                ":ws, :case, :v, 'k', 'p', 'h', 'f', 'has_blockers', 0, '{}')"
            ),
            {"ws": other_ws, "case": case_id, "v": version_id},
        )
    await session.rollback()


# --- Output -------------------------------------------------------------------------


async def test_every_output_is_marked_hypothetical(session) -> None:
    w = await confirmed_world(session)
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    result = await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    await session.commit()
    payload = result.row.payload
    assert payload["hypothetical"] is True
    simulated = _walk_outcomes(payload)
    assert simulated, "the analysis has simulated outcomes"
    assert all(o["hypothetical"] is True for o in simulated)
    # No claim text in the stored document.
    assert "We have 250 employees" not in str(payload)


async def test_version_with_no_unresolved_items_has_no_blockers(session) -> None:
    t = await tenant(session, "clean")
    statuses = dict.fromkeys(fx.SUPPORTED, ClaimStatus.SUPPORTED)
    row = await _stored_version(session, t, statuses)
    result = await flip_service.flip_for_version(session, t.workspace.id, row)
    await session.commit()
    a = result.analysis
    assert a.state.value == "no_blockers"
    assert a.items == [] and a.target is None and a.minimum_evidence is None
    assert result.row.state == "no_blockers" and result.row.blocker_count == 0


async def test_disqualifier_risk_is_persisted(session) -> None:
    t = await tenant(session, "risk")
    statuses = {**fx.SUPPORTED, "fx-claim-2": ClaimStatus.CANNOT_VERIFY}
    row = await _stored_version(session, t, statuses, {"fx-crit-2": fx.U})
    result = await flip_service.flip_for_version(session, t.workspace.id, row)
    await session.commit()
    by_id = {i.id: i for i in result.analysis.items}
    crit = by_id["criterion:fx-crit-2"]
    # Policy 2026-11-22.3: an unknown must-have also blocks Prioritise.
    assert crit.disqualifier_risk and crit.decision_blocker
    assert crit.if_contradicted.disposition.value == "deprioritise"
    assert result.row.blocker_count == 2 and result.row.target == "prioritise"


# --- Restart recovery ----------------------------------------------------------------


async def test_worker_killed_after_the_insert_resumes_without_a_second_row(sm, session) -> None:
    """The worker dies after its insert committed but before the step was marked done.
    The re-claimed attempt finds the row by key and finishes with `created: false`; the
    request list still waits for it."""
    w = await confirmed_world(session)
    case_id = w.t.case.id
    calls: list[dict] = []
    run = await _assess_run(session, w)
    worker = make_worker(sm, _registry(calls))
    assert await worker.run_once()  # evaluate.assess
    steps = await _steps(sm, run.id)
    assert steps["evaluate"].state == "done" and steps["decision_flip"].state == "pending"

    # The dead attempt: claimed the step, wrote the analysis, never reported back.
    async with sm() as s:
        version = await repo.latest_assessment(s, w.t.workspace.id, w.t.case.id)
        dead = await flip_service.flip_for_version(s, w.t.workspace.id, version, run_id=run.id)
        await s.commit()
    await _crash_mid_step(sm, run.id, "decision_flip")
    assert calls == []  # the request list did not run past the dead step

    await make_worker(sm, _registry(calls)).drain()
    steps = await _steps(sm, run.id)
    flip = steps["decision_flip"]
    assert flip.state == "done" and flip.attempts == 2
    assert flip.output["analysis_id"] == str(dead.row.id)
    assert flip.output["created"] is False
    assert steps["request_list"].state == "done"
    assert flip.finished_at <= steps["request_list"].started_at
    rows = await _rows(sm, case_id)
    assert [r.id for r in rows] == [dead.row.id]
    assert len(calls) == 1
    async with sm() as s:
        assert (await s.get(Run, run.id)).state == "done"


async def test_worker_killed_before_the_insert_writes_once_on_resume(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    run = await _assess_run(session, w)
    worker = make_worker(sm, _registry())
    assert await worker.run_once()  # evaluate.assess
    await _crash_mid_step(sm, run.id, "decision_flip")  # died before writing anything
    assert await _rows(sm, case_id) == []
    await make_worker(sm, _registry()).drain()
    steps = await _steps(sm, run.id)
    assert steps["decision_flip"].state == "done"
    assert steps["decision_flip"].output["created"] is True
    assert steps["request_list"].state == "done"
    assert len(await _rows(sm, case_id)) == 1


async def test_a_handler_retry_after_a_failed_commit_keeps_one_row(sm, session) -> None:
    """The handler runs twice in one step (first attempt crashes after its insert, which
    rolls back): one row, and the analysis is identical across attempts."""
    w = await confirmed_world(session)
    case_id = w.t.case.id
    reg = _registry()
    attempts: list[dict] = []

    async def flaky(ctx: StepContext) -> dict:
        out = await flip_step.decision_flip(ctx)
        attempts.append(out)
        if ctx.attempt == 1:
            raise RuntimeError("killed after insert, before commit")
        return out

    reg.register(flip_step.HANDLER, flaky, replace=True)
    run = await _assess_run(session, w)
    await make_worker(sm, reg).drain()
    steps = await _steps(sm, run.id)
    assert steps["decision_flip"].state == "done"
    assert [a["created"] for a in attempts] == [True, True]  # the first insert rolled back
    assert attempts[0]["analysis_key"] == attempts[1]["analysis_key"]
    assert len(await _rows(sm, case_id)) == 1


async def test_version_the_rules_cannot_replay_is_stored_not_reproducible(sm, session) -> None:
    """A version made under an older policy: the step never crashes the run; it stores
    a `not_reproducible` row once, and the request list still runs."""
    t = await tenant(session, "old")
    case_id = t.case.id
    v, _, _ = fx.fixture_version(str(case_id), 1, dict(fx.SUPPORTED))
    doc = v.model_dump(mode="json")
    doc["judgments"]["disposition"]["reasons"] = ["Reason from an older policy"]
    await repo.add_assessment_version(
        session,
        t.workspace.id,
        case_id,
        policy_version="2026-01-01.1",
        inputs_hash=v.inputs_hash,
        judgments={"assessment": doc},
        disposition=v.disposition.value,
        reasons=["Reason from an older policy"],
    )
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="evaluate",
        case_id=case_id,
        steps=[evaluate.evaluate_step(), flip_step.decision_flip_step(), request_list_step()],
    )
    await session.commit()
    reg = _registry()

    async def no_new_version(ctx):  # the stored version stands; nothing re-assessed
        return {}

    reg.register(evaluate.HANDLER, no_new_version, replace=True)
    await make_worker(sm, reg).drain()
    steps = await _steps(sm, run.id)
    assert steps["decision_flip"].state == "done"
    assert steps["decision_flip"].output["state"] == "not_reproducible"
    assert steps["request_list"].state == "done"
    [row] = await _rows(sm, case_id)
    assert row.state == "not_reproducible" and row.blocker_count == 0
    assert row.payload["not_reproducible_reason"].startswith("Replaying version 1")
    async with sm() as s:
        version = await repo.latest_assessment(s, t.workspace.id, case_id)
        again = await flip_service.flip_for_version(s, t.workspace.id, version)
    assert not again.created and again.row.id == row.id and again.analysis is None
