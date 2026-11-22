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

SSE polls the database (activities every 0.5 s, the run and steps every second), which
works on every instance and through Neon's pooled endpoint, where LISTEN/NOTIFY is
unavailable. The stream sends `event: run` (run without steps), `event: step` for
every step, the `event: activity` backlog (each with `id: {seq}`), a `: live` comment,
then one `event: step` per change, every new `event: activity`, `event: run` on every
state or cost change, and a final `event: run` once the run is `done`/`failed`.
"""

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas.common import CostTotalsOut, RunKind, StepState
from app.api.schemas.common import RunState as ContractRunState
from app.api.schemas.runs import (
    ActivityOut,
    ActivityPage,
    ActivitySummaryOut,
    RunEvent,
    RunOut,
    StepEvent,
    StepOut,
)
from app.db import repo
from app.db.enums import CallStatus, RunState
from app.db.models import (
    CallAttempt,
    Case,
    CostEntry,
    DiscoveryRun,
    InvestorRun,
    Run,
    RunActivity,
    Thesis,
)
from app.jobs.engine import resume_run

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0
ACTIVITY_POLL_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0

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


def activity_frame(activity: ActivityOut) -> str:
    return f"id: {activity.seq}\nevent: activity\ndata: {activity.model_dump_json()}\n\n"


LIVE_MARKER = ": live\n\n"


# --- Activity: reading -------------------------------------------------------------------


async def activity_since(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    after: int = 0,
    limit: int | None = None,
) -> list[ActivityOut]:
    """Activities with seq > `after`, in seq order, of a run in `workspace_id`."""
    stmt = (
        select(RunActivity.payload)
        .where(
            RunActivity.run_id == run_id,
            RunActivity.workspace_id == workspace_id,
            RunActivity.seq > after,
        )
        .order_by(RunActivity.seq)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    out = []
    for payload in (await session.execute(stmt)).scalars():
        try:
            out.append(ActivityOut.model_validate(payload))
        except ValidationError:
            log.warning("activity: stored event does not fit the contract; skipped")
    return out


async def load_activity_page(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    after: int = 0,
    limit: int = 500,
) -> ActivityPage:
    """`GET /runs/{id}/activity`: one page after `after`, plus the run's summary. Raises
    `repo.NotFound` for a run outside `workspace_id`."""
    run = await repo.get_run(session, workspace_id, run_id, with_steps=False)
    if run.workspace_id != workspace_id:
        raise repo.NotFound("run")
    limit = max(1, min(limit, 2000))
    items = await activity_since(session, workspace_id, run.id, after, limit)
    return ActivityPage(
        items=items,
        next_after=items[-1].seq if len(items) == limit else None,
        summary=await activity_summary(session, workspace_id, run),
    )


async def activity_summary(
    session: AsyncSession, workspace_id: uuid.UUID, run: Run
) -> ActivitySummaryOut:
    """Totals over every activity of the run; credits and USD from the cost ledger."""
    payloads = (
        await session.execute(
            select(RunActivity.payload)
            .where(RunActivity.run_id == run.id, RunActivity.workspace_id == workspace_id)
            .order_by(RunActivity.seq)
        )
    ).scalars()
    by_kind: Counter[str] = Counter()
    calls = records = read = failed = last_seq = 0
    domains: set[str] = set()
    companies: set[str] = set()
    investors: set[str] = set()
    claims: dict[str, str] = {}
    for p in payloads:
        last_seq = max(last_seq, int(p.get("seq") or 0))
        by_kind[p.get("kind") or "?"] += 1
        call = p.get("call") or {}
        if p.get("kind") == "call" and call.get("provider") == "crustdata":
            calls += 1
            counts = p.get("counts") or {}
            records += sum(int(counts.get(k) or 0) for k in _RECORD_KEYS)
        source = p.get("source") or {}
        if p.get("kind") == "source":
            if source.get("state") == "read":
                read += 1
            elif source.get("state") == "failed":
                failed += 1
            if source.get("domain"):
                domains.add(source["domain"])
        subject = p.get("subject")
        for item in p.get("items") or []:
            if subject == "company" and item.get("stage") == "found":
                companies.add(str(item.get("id")))
            elif subject == "investor":
                investors.add(str(item.get("id")))
            elif subject == "round":
                investors.update(str(i.get("key")) for i in item.get("investors") or [])
            elif subject == "claim":
                claims[str(item.get("id"))] = str(item.get("stage"))
    cost = (
        await session.execute(
            select(
                func.coalesce(func.sum(CostEntry.credits), 0),
                func.coalesce(func.sum(CostEntry.usd), 0),
            ).where(CostEntry.run_id == run.id, CostEntry.workspace_id == workspace_id)
        )
    ).one()
    end = run.finished_at or datetime.now(UTC)
    return ActivitySummaryOut(
        by_kind=dict(by_kind),
        crustdata_calls=calls,
        records_returned=records,
        sources_read=read,
        sources_failed=failed,
        domains=len(domains),
        companies_found=len(companies),
        investors_found=len(investors),
        claims_settled=sum(stage in ("settled", "not_checked") for stage in claims.values()),
        credits=float(cost[0] or 0),
        llm_usd=float(cost[1] or 0),
        elapsed_seconds=round(max(0.0, (end - run.created_at).total_seconds()), 3),
        last_seq=last_seq,
    )


_RECORD_KEYS = ("returned", "candidates", "postings")


# --- The stream --------------------------------------------------------------------------


async def run_event_stream(
    sessionmaker: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    after: int | None = None,
    poll_seconds: float | None = None,
    activity_poll_seconds: float | None = None,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """SSE frames for one run until it is done or failed. Check access (call
    `load_run_out`) before starting the response, so a 404 is not sent mid-stream.

    Sends the run, every step, the activity backlog after `after` (from `Last-Event-ID`
    or `?after=`), then `: live`, then changes as they happen: steps when they change,
    activities as they are written (polled every 0.5 s), and the run again on every
    state or cost change. The run and steps are reloaded every second."""
    run_poll = POLL_SECONDS if poll_seconds is None else poll_seconds
    tick = ACTIVITY_POLL_SECONDS if activity_poll_seconds is None else activity_poll_seconds
    tick = min(tick, run_poll)
    every = max(1, round(run_poll / tick)) if tick > 0 else 1
    seen: dict[str, tuple] = {}
    last_seq = max(0, after or 0)
    last_state: str | None = None
    last_cost: CostTotalsOut | None = None
    ticks = 0
    while True:
        out: RunOut | None = None
        async with sessionmaker() as session:
            if ticks % every == 0:
                out = await load_run_out(session, workspace_id, run_id)
            # Read after the run, so a run seen finished has all its activities here.
            activities = await activity_since(session, workspace_id, run_id, last_seq)
        first = last_state is None
        terminal = out is not None and out.state in (RunState.DONE, RunState.FAILED)
        if out is not None:
            run_event = _sse(RunEvent(data=out.model_copy(update={"steps": []})))
            if first:
                yield run_event
            for step in out.steps:
                signature = (step.state, step.attempts, step.detail, step.result, step.error)
                if seen.get(step.id) != signature:
                    seen[step.id] = signature
                    yield _sse(StepEvent(data=step))
        for activity in activities:
            last_seq = max(last_seq, activity.seq)
            yield activity_frame(activity)
        if first:
            yield LIVE_MARKER
        if out is not None:
            changed = out.state != last_state or out.cost != last_cost
            # Every state or cost change is announced; the stream ends on a run event.
            if (not first and changed) or (first and terminal):
                yield run_event
            last_state, last_cost = out.state, out.cost
        if terminal:
            return
        ticks += 1
        if ticks % max(1, round(KEEPALIVE_SECONDS / max(tick, 0.05))) == 0:
            yield ": keepalive\n\n"
        if is_disconnected is not None and await is_disconnected():
            return
        await asyncio.sleep(tick)
