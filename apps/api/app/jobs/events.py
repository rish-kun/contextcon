"""Run status for the API contract (`app.api.schemas.runs`): snapshot, resume and SSE.

These are the implementations behind the CP-03 stubs in `app/api/runs.py`
(`GET /runs/{id}`, `GET /runs/{id}/events`, `POST /runs/{id}/resume`). They take the
caller's `workspace_id` from whoever wires auth; nothing here trusts request headers.
A run in another workspace raises `repo.NotFound` (map it to 404).

Wiring, once auth provides the workspace (outside fixture mode):

    run = await events.load_run_out(session, workspace_id, run_id)
    stream = events.run_event_stream(get_sessionmaker(), workspace_id, run_id,
                                     is_disconnected=request.is_disconnected)
    return EventStreamResponse(stream, headers={"Cache-Control": "no-cache"})

SSE polls the steps table (default every second), which works on every instance and
through Neon's pooled endpoint, where LISTEN/NOTIFY is unavailable. The stream sends
`event: run` (run without steps), then `event: step` for every step, then one
`event: step` per change, and a final `event: run` once the run is `done`/`failed`.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas.common import CostTotalsOut, RunKind, StepState
from app.api.schemas.common import RunState as ContractRunState
from app.api.schemas.runs import RunEvent, RunOut, StepEvent, StepOut
from app.db import repo
from app.db.enums import CallStatus, RunState
from app.db.models import CallAttempt, Case, CostEntry, DiscoveryRun, InvestorRun, Run, Thesis
from app.jobs.engine import resume_run

POLL_SECONDS = 1.0
KEEPALIVE_EVERY = 15  # polls

_NOT_RUN = {StepState.skipped_budget, StepState.failed}


def _totals(row, unresolved: int = 0) -> CostTotalsOut:  # type: ignore[no-untyped-def]
    """`unresolved`: attempts still `started` (no final usage yet), counted as calls of
    unknown cost."""
    if row is None:
        return CostTotalsOut(unknown_cost_calls=unresolved)
    return CostTotalsOut(
        crustdata_credits=float(row.credits or 0),
        llm_usd=float(row.usd or 0),
        input_tokens=int(row.input_tokens or 0),
        output_tokens=int(row.output_tokens or 0),
        unknown_cost_calls=int(row.unknown or 0) + unresolved,
    )


def _cost_columns():  # type: ignore[no-untyped-def]
    return (
        func.sum(CostEntry.credits).label("credits"),
        func.sum(CostEntry.usd).label("usd"),
        func.sum(CostEntry.input_tokens).label("input_tokens"),
        func.sum(CostEntry.output_tokens).label("output_tokens"),
        func.count(case((CostEntry.unknown, 1))).label("unknown"),
    )


async def _subject(session: AsyncSession, run: Run) -> str:
    # Every lookup is pinned to the run's workspace as well as its owner id.
    ws = run.workspace_id
    if run.case_id is not None:
        name = await session.scalar(
            select(Case.company_name).where(Case.id == run.case_id, Case.workspace_id == ws)
        )
        return name or ""
    if run.discovery_run_id is not None:
        text = await session.scalar(
            select(Thesis.text)
            .join(DiscoveryRun, DiscoveryRun.thesis_id == Thesis.id)
            .where(
                DiscoveryRun.id == run.discovery_run_id,
                DiscoveryRun.workspace_id == ws,
                Thesis.workspace_id == ws,
            )
        )
        return text or ""
    if run.investor_run_id is not None:
        profile = await session.scalar(
            select(InvestorRun.profile).where(
                InvestorRun.id == run.investor_run_id, InvestorRun.workspace_id == ws
            )
        )
        if isinstance(profile, dict):
            parts = [str(profile[k]) for k in ("sector", "location", "stage") if profile.get(k)]
            return ", ".join(parts)
    return ""


async def load_run_out(session: AsyncSession, workspace_id: uuid.UUID, run_id: uuid.UUID) -> RunOut:
    """The run with every step, in the contract's shape. Raises `repo.NotFound` for a
    run outside `workspace_id`; every joined lookup is scoped to the workspace too."""
    run = await repo.get_run(session, workspace_id, run_id)
    if run.workspace_id != workspace_id:  # defence in depth over the scoped query
        raise repo.NotFound("run")
    step_costs = {
        r.step_id: r
        for r in (
            await session.execute(
                select(CostEntry.step_id, *_cost_columns())
                .where(CostEntry.run_id == run.id, CostEntry.workspace_id == workspace_id)
                .group_by(CostEntry.step_id)
            )
        ).all()
    }
    run_cost = (
        await session.execute(
            select(*_cost_columns()).where(
                CostEntry.run_id == run.id, CostEntry.workspace_id == workspace_id
            )
        )
    ).one()
    calls = {
        r.step_id: r
        for r in (
            await session.execute(
                select(
                    CallAttempt.step_id,
                    func.count().label("total"),
                    func.count(case((CallAttempt.status == CallStatus.CACHE_HIT, 1))).label("hits"),
                    func.count(case((CallAttempt.status == CallStatus.STARTED, 1))).label(
                        "unresolved"
                    ),
                )
                .where(CallAttempt.run_id == run.id, CallAttempt.workspace_id == workspace_id)
                .group_by(CallAttempt.step_id)
            )
        ).all()
    }
    steps = []
    for step in run.steps:
        c = calls.get(step.id)
        steps.append(
            StepOut(
                id=str(step.id),
                run_id=str(run.id),
                key=step.key,
                label=step.label,
                position=step.position,
                state=StepState(step.state),
                attempts=step.attempts,
                detail=step.detail if step.state == "running" else None,
                result=step.result
                or (
                    f"Not checked: {step.skip_reason}"
                    if step.state == "skipped_budget" and step.skip_reason
                    else None
                ),
                error=step.error if step.state != "done" else None,
                from_cache=bool(c and c.total and c.hits == c.total),
                cost=_totals(step_costs.get(step.id), c.unresolved if c else 0),
                started_at=step.started_at,
                finished_at=step.finished_at,
            )
        )
    return RunOut(
        id=str(run.id),
        kind=RunKind(run.kind),
        state=ContractRunState(run.state),
        subject=await _subject(session, run),
        case_id=str(run.case_id) if run.case_id else None,
        thesis_id=str(
            await session.scalar(
                select(DiscoveryRun.thesis_id).where(
                    DiscoveryRun.id == run.discovery_run_id,
                    DiscoveryRun.workspace_id == workspace_id,
                )
            )
        )
        if run.discovery_run_id
        else None,
        investor_search_id=str(run.investor_run_id) if run.investor_run_id else None,
        budget_credits=float(run.budget_credits or Decimal(0)),
        cost=_totals(run_cost, sum(c.unresolved for c in calls.values())),
        checks_not_run=sum(1 for s in steps if s.state in _NOT_RUN),
        created_at=run.created_at,
        finished_at=run.finished_at,
        resumed_at=run.resumed_at,
        error=run.error,
        steps=steps,
    )


async def resume_run_out(
    session: AsyncSession, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> RunOut:
    """Re-queue failed and budget-skipped steps (after a fix or a budget increase).
    Done steps stay done and their paid calls replay from the cache. Commits."""
    run = await repo.get_run(session, workspace_id, run_id, with_steps=False)
    await resume_run(session, run.id)
    await session.commit()
    session.expunge_all()
    return await load_run_out(session, workspace_id, run_id)


def _sse(event: StepEvent | RunEvent) -> str:
    return f"event: {event.event}\ndata: {event.data.model_dump_json()}\n\n"


async def run_event_stream(
    sessionmaker: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    poll_seconds: float | None = None,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """SSE frames for one run until it is done or failed. Check access (call
    `load_run_out`) before starting the response, so a 404 is not sent mid-stream."""
    poll = POLL_SECONDS if poll_seconds is None else poll_seconds
    seen: dict[str, tuple] = {}
    last_state: str | None = None
    polls = 0
    while True:
        async with sessionmaker() as session:
            out = await load_run_out(session, workspace_id, run_id)
        first = last_state is None
        terminal = out.state in (RunState.DONE, RunState.FAILED)
        run_event = _sse(RunEvent(data=out.model_copy(update={"steps": []})))
        if first:
            yield run_event
        for step in out.steps:
            signature = (step.state, step.attempts, step.detail, step.result, step.error)
            if seen.get(step.id) != signature:
                seen[step.id] = signature
                yield _sse(StepEvent(data=step))
        # Every run state change is announced; the stream always ends on a run event.
        if (not first and out.state != last_state) or (first and terminal):
            yield run_event
        last_state = out.state
        if terminal:
            return
        polls += 1
        if polls % KEEPALIVE_EVERY == 0:
            yield ": keepalive\n\n"
        if is_disconnected is not None and await is_disconnected():
            return
        await asyncio.sleep(poll)
