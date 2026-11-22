"""The workspace's job queue for `GET /runs`: runs still working, and the latest ones.

Every item is built from the same `RunOut` the run page streams (`events.load_run_out`),
so a queue row's credits, step count and current step always match what the run's own
header and step list show.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import RunState, StepState
from app.api.schemas.runs import (
    RunCreditsOut,
    RunOut,
    RunOwnerKind,
    RunOwnerOut,
    RunQueueItemOut,
    RunQueueOut,
    RunQueueStatus,
)
from app.db.enums import RunState as DbRunState
from app.db.models import Run
from app.jobs.events import load_run_out

ACTIVE_STATES = (DbRunState.PENDING, DbRunState.RUNNING)
_SETTLED = {StepState.done, StepState.failed, StepState.skipped_budget}


def owner_of(run: RunOut) -> RunOwnerOut | None:
    if run.case_id:
        return RunOwnerOut(kind=RunOwnerKind.case, id=run.case_id, label=run.subject)
    if run.thesis_id:
        return RunOwnerOut(kind=RunOwnerKind.thesis, id=run.thesis_id, label=run.subject)
    if run.investor_search_id:
        return RunOwnerOut(
            kind=RunOwnerKind.investor_search, id=run.investor_search_id, label=run.subject
        )
    return None


def queue_item(run: RunOut, *, updated_at: datetime | None = None) -> RunQueueItemOut:
    """One queue row from a run with its steps. Credits are the run's own totals, which
    the steps add up to (see `load_run_out`)."""
    steps = sorted(run.steps, key=lambda s: s.position)
    active = run.state in (RunState.pending, RunState.running)
    current = None
    if active:
        current = next((s for s in steps if s.state == StepState.running), None) or next(
            (s for s in steps if s.state == StepState.pending), None
        )
    started = [s.started_at for s in steps if s.started_at is not None]
    touched = [
        t for t in (run.created_at, run.finished_at, run.resumed_at, *started) if t is not None
    ] + [s.finished_at for s in steps if s.finished_at is not None]
    return RunQueueItemOut(
        id=run.id,
        kind=run.kind,
        state=run.state,
        owner=owner_of(run),
        created_at=run.created_at,
        started_at=min(started) if started else None,
        # The run row's own timestamp moves on state changes only; step times move more.
        updated_at=max([*touched, *([updated_at] if updated_at else [])]),
        finished_at=run.finished_at,
        steps_done=sum(1 for s in steps if s.state in _SETTLED),
        steps_total=len(steps),
        current_step=current.label if current else None,
        credits=RunCreditsOut(
            settled=run.cost.crustdata_credits,
            reserved=run.reserved_credits,
            unknown_cost_calls=run.cost.unknown_cost_calls,
        ),
        llm_usd=run.cost.llm_usd,
        budget_credits=run.budget_credits,
    )


async def list_run_queue(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    status: RunQueueStatus = RunQueueStatus.active,
    limit: int = 20,
) -> RunQueueOut:
    """Active runs (oldest first, the order the worker takes them) or the most recently
    updated runs of any state. Scoped to `workspace_id` throughout."""
    query = select(Run.id, Run.updated_at).where(Run.workspace_id == workspace_id)
    if status == RunQueueStatus.active:
        query = query.where(Run.state.in_(ACTIVE_STATES)).order_by(Run.created_at.asc(), Run.id)
    else:
        query = query.order_by(Run.updated_at.desc(), Run.id)
    rows = (await session.execute(query.limit(limit))).all()
    items = []
    for run_id, updated_at in rows:
        out = await load_run_out(session, workspace_id, run_id)
        items.append(queue_item(out, updated_at=updated_at))
    active_count = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.workspace_id == workspace_id, Run.state.in_(ACTIVE_STATES))
    )
    return RunQueueOut(items=items, active_count=int(active_count or 0))
