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
state or cost change, and a final `event: run` once the run is `done`/`failed`,
followed by `event: end` once every activity has been sent.
"""

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

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
from app.jobs.activity import public_step_text
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


_COST_KEYS = ("credits", "usd", "input_tokens", "output_tokens", "unknown")


def _cost_columns():  # type: ignore[no-untyped-def]
    return (
        func.sum(CostEntry.credits).label("credits"),
        func.sum(CostEntry.usd).label("usd"),
        func.sum(CostEntry.input_tokens).label("input_tokens"),
        func.sum(CostEntry.output_tokens).label("output_tokens"),
        func.count(case((CostEntry.unknown, 1))).label("unknown"),
    )


def _investor_subject(profile: object) -> str:
    if isinstance(profile, dict):
        parts = [str(profile[k]) for k in ("sector", "location", "stage") if profile.get(k)]
        return ", ".join(parts)
    return ""


async def _owners(
    session: AsyncSession, workspace_id: uuid.UUID, runs: list[Run]
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str | None]]:
    """Each run's subject (case name, thesis text or investor profile) and, for discovery
    runs, its thesis id. One query per owner kind present; every lookup is pinned to the
    workspace as well as the owner id."""
    ws = workspace_id
    case_ids = {r.case_id for r in runs if r.case_id is not None}
    discovery_ids = {r.discovery_run_id for r in runs if r.discovery_run_id is not None}
    investor_ids = {r.investor_run_id for r in runs if r.investor_run_id is not None}
    names: dict[uuid.UUID, str] = {}
    if case_ids:
        rows = await session.execute(
            select(Case.id, Case.company_name).where(Case.id.in_(case_ids), Case.workspace_id == ws)
        )
        names = dict(rows.all())
    theses: dict[uuid.UUID, tuple[uuid.UUID, str | None]] = {}
    if discovery_ids:
        rows = await session.execute(
            select(DiscoveryRun.id, DiscoveryRun.thesis_id, Thesis.text)
            .outerjoin(Thesis, (Thesis.id == DiscoveryRun.thesis_id) & (Thesis.workspace_id == ws))
            .where(DiscoveryRun.id.in_(discovery_ids), DiscoveryRun.workspace_id == ws)
        )
        theses = {i: (thesis_id, text) for i, thesis_id, text in rows.all()}
    profiles: dict[uuid.UUID, object] = {}
    if investor_ids:
        rows = await session.execute(
            select(InvestorRun.id, InvestorRun.profile).where(
                InvestorRun.id.in_(investor_ids), InvestorRun.workspace_id == ws
            )
        )
        profiles = dict(rows.all())
    subjects: dict[uuid.UUID, str] = {}
    thesis_ids: dict[uuid.UUID, str | None] = {}
    for run in runs:
        subject = ""
        if run.case_id is not None:
            subject = names.get(run.case_id) or ""
        elif run.discovery_run_id is not None:
            subject = (theses.get(run.discovery_run_id) or (None, None))[1] or ""
        elif run.investor_run_id is not None:
            subject = _investor_subject(profiles.get(run.investor_run_id))
        subjects[run.id] = subject
        if run.discovery_run_id is not None:
            # str(None) when the discovery run is not in the workspace, as before.
            thesis_ids[run.id] = str((theses.get(run.discovery_run_id) or (None, None))[0])
        else:
            thesis_ids[run.id] = None
    return subjects, thesis_ids


async def load_run_out(session: AsyncSession, workspace_id: uuid.UUID, run_id: uuid.UUID) -> RunOut:
    """The run with every step, in the contract's shape. Raises `repo.NotFound` for a
    run outside `workspace_id`; every joined lookup is scoped to the workspace too."""
    run = await repo.get_run(session, workspace_id, run_id)
    if run.workspace_id != workspace_id:  # defence in depth over the scoped query
        raise repo.NotFound("run")
    return (await run_outs(session, workspace_id, [run]))[0]


async def run_outs(session: AsyncSession, workspace_id: uuid.UUID, runs: list[Run]) -> list[RunOut]:
    """`RunOut` for runs already loaded with their steps (`selectinload(Run.steps)`), in
    the same order. Costs and calls are aggregated for all runs at once, so a list of 20
    runs costs the same handful of queries as one."""
    runs = [r for r in runs if r.workspace_id == workspace_id]
    if not runs:
        return []
    run_ids = [r.id for r in runs]
    step_costs: dict[uuid.UUID, dict[uuid.UUID | None, object]] = {}
    run_costs: dict[uuid.UUID, dict[str, Decimal | int | None]] = {}
    for r in (
        await session.execute(
            select(CostEntry.run_id, CostEntry.step_id, *_cost_columns())
            .where(CostEntry.run_id.in_(run_ids), CostEntry.workspace_id == workspace_id)
            .group_by(CostEntry.run_id, CostEntry.step_id)
        )
    ).all():
        step_costs.setdefault(r.run_id, {})[r.step_id] = r
        # The run's totals are the sum of its step groups (the null step included).
        total = run_costs.setdefault(r.run_id, dict.fromkeys(_COST_KEYS))
        for key in _COST_KEYS:
            value = getattr(r, key)
            if value is not None:
                total[key] = (total[key] or 0) + value
    calls: dict[uuid.UUID, dict[uuid.UUID | None, object]] = {}
    for r in (
        await session.execute(
            select(
                CallAttempt.run_id,
                CallAttempt.step_id,
                func.count().label("total"),
                func.count(case((CallAttempt.status == CallStatus.CACHE_HIT, 1))).label("hits"),
                func.count(case((CallAttempt.status == CallStatus.STARTED, 1))).label("unresolved"),
                func.sum(
                    case(
                        (
                            CallAttempt.status == CallStatus.STARTED,
                            func.coalesce(CallAttempt.reserved_credits, 0),
                        ),
                        else_=0,
                    )
                ).label("reserved"),
            )
            .where(CallAttempt.run_id.in_(run_ids), CallAttempt.workspace_id == workspace_id)
            .group_by(CallAttempt.run_id, CallAttempt.step_id)
        )
    ).all():
        calls.setdefault(r.run_id, {})[r.step_id] = r
    subjects, thesis_ids = await _owners(session, workspace_id, runs)
    return [
        _run_out(
            run,
            step_costs.get(run.id, {}),
            run_costs.get(run.id),
            calls.get(run.id, {}),
            subjects[run.id],
            thesis_ids[run.id],
        )
        for run in runs
    ]


def _run_out(  # type: ignore[no-untyped-def]
    run: Run, step_costs, run_cost, calls, subject: str, thesis_id: str | None
) -> RunOut:
    steps = []
    for step in run.steps:
        c = calls.get(step.id)
        # Document steps: fixed words and counts, also for rows written before that rule.
        label, detail, result = public_step_text(step.key, step.label, step.detail, step.result)
        steps.append(
            StepOut(
                id=str(step.id),
                run_id=str(run.id),
                key=step.key,
                label=label,
                position=step.position,
                state=StepState(step.state),
                attempts=step.attempts,
                detail=detail if step.state == "running" else None,
                result=result
                or (
                    f"Not checked: {step.skip_reason}"
                    if step.state == "skipped_budget" and step.skip_reason
                    else None
                ),
                error=step.error if step.state != "done" else None,
                from_cache=bool(c and c.total and c.hits == c.total),
                cost=_totals(step_costs.get(step.id), c.unresolved if c else 0),
                reserved_credits=float(c.reserved or 0) if c else 0.0,
                started_at=step.started_at,
                finished_at=step.finished_at,
            )
        )
    return RunOut(
        id=str(run.id),
        kind=RunKind(run.kind),
        state=ContractRunState(run.state),
        subject=subject,
        case_id=str(run.case_id) if run.case_id else None,
        thesis_id=thesis_id,
        investor_search_id=str(run.investor_run_id) if run.investor_run_id else None,
        budget_credits=float(run.budget_credits or Decimal(0)),
        cost=_totals(
            SimpleNamespace(**run_cost) if run_cost else None,
            sum(c.unresolved for c in calls.values()),
        ),
        reserved_credits=float(sum((c.reserved or 0) for c in calls.values())),
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


def _run_signature(out: RunOut) -> tuple:
    return (
        out.state,
        out.cost.model_dump_json(),
        out.reserved_credits,
        out.checks_not_run,
        out.resumed_at,
        out.error,
    )


def _sse(event: StepEvent | RunEvent) -> str:
    return f"event: {event.event}\ndata: {event.data.model_dump_json()}\n\n"


def activity_frame(activity: ActivityOut) -> str:
    return f"id: {activity.seq}\nevent: activity\ndata: {activity.model_dump_json()}\n\n"


LIVE_MARKER = ": live\n\n"
# The last frame of a finished run, after the backlog and the final `event: run`. Clients
# close on this, never on a finished `run` snapshot: on a reconnect that snapshot comes
# before the backlog.
END_FRAME = "event: end\ndata: {}\n\n"


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
    last_run: tuple | None = None
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
            # Every run change (state, spend, reservations, skipped checks) is announced,
            # so the header's credits keep up with the steps; the stream ends on a run event.
            signature = _run_signature(out)
            changed = out.state != last_state or signature != last_run
            if (not first and changed) or (first and terminal):
                yield run_event
            last_state, last_run = out.state, signature
        if terminal:
            yield END_FRAME
            return
        ticks += 1
        if ticks % max(1, round(KEEPALIVE_SECONDS / max(tick, 0.05))) == 0:
            yield ": keepalive\n\n"
        if is_disconnected is not None and await is_disconnected():
            return
        await asyncio.sleep(tick)
