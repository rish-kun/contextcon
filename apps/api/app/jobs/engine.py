"""Runs and steps: creation, claiming, leases, completion and budget.

A Run is a set of Steps. A step is `pending → running → done | failed | skipped_budget`.
Workers claim one ready step at a time with `SELECT … FOR UPDATE SKIP LOCKED`, hold a
lease they renew while the handler runs, and lose the step back to the queue if the
lease expires. Every state change is fenced on `lease_owner`, so a worker that lost its
lease cannot overwrite the result of the worker that took over.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.adapters import DbCache, DbCallRecorder
from app.db.enums import TERMINAL_STEP_STATES, RunState, StepState
from app.db.ledger import CostContext, spent_credits
from app.db.models import Case, Run, Step
from app.jobs.config import get_job_settings
from app.settings import get_settings

log = logging.getLogger(__name__)

BUDGET_REACHED = "budget reached"


class BudgetExceeded(Exception):
    """Raise from a handler (or `ctx.require_budget`) when a call would overspend."""

    def __init__(self, reason: str = BUDGET_REACHED) -> None:
        super().__init__(reason)
        self.reason = reason


class LeaseLost(Exception):
    """Another worker owns this step now; this worker's result is discarded."""


@dataclass(frozen=True)
class StepSpec:
    key: str
    handler: str
    input: dict[str, Any] = field(default_factory=dict)
    depends_on: Sequence[str] = ()
    # False for steps that cost no credits (e.g. evaluate): they still run after the
    # budget is spent, so the case can render "Not checked: budget reached".
    uses_budget: bool = True
    # Run even if a dependency failed or was skipped for budget (the handler reads
    # `ctx.dependencies` to see which). Otherwise the failure/skip propagates.
    tolerate_failed_deps: bool = False
    max_attempts: int | None = None


# --- Creating runs -----------------------------------------------------------


async def create_run(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    kind: str,
    steps: Sequence[StepSpec],
    case_id: uuid.UUID | None = None,
    discovery_run_id: uuid.UUID | None = None,
    investor_run_id: uuid.UUID | None = None,
    budget_credits: Decimal | float | int | None = None,
    created_by: uuid.UUID | None = None,
    max_attempts: int | None = None,
) -> Run:
    """Insert a run and its steps (flushes, does not commit).

    Case runs get the case's `credit_budget`, else `CASE_CREDIT_BUDGET`. The budget is
    per case: every run of the case draws on the same credits.
    """
    if budget_credits is None and case_id is not None:
        case_row = await session.get(Case, case_id)
        if case_row is None or case_row.workspace_id != workspace_id:
            raise LookupError("case not found in this workspace")
        budget_credits = case_row.credit_budget
        if budget_credits is None:
            budget_credits = get_settings().case_credit_budget
    run = Run(
        workspace_id=workspace_id,
        kind=kind,
        case_id=case_id,
        discovery_run_id=discovery_run_id,
        investor_run_id=investor_run_id,
        budget_credits=None if budget_credits is None else Decimal(str(budget_credits)),
        created_by=created_by,
        state=RunState.PENDING,
    )
    session.add(run)
    await session.flush()
    await append_steps(session, run.id, steps, max_attempts=max_attempts)
    return run


async def append_steps(
    session: AsyncSession,
    run_id: uuid.UUID,
    steps: Sequence[StepSpec],
    *,
    max_attempts: int | None = None,
) -> list[Step]:
    """Add steps to a run (e.g. a handler fanning out one step per claim).

    Keys must be unique within the run; dependencies must name steps that exist in the
    run or in this batch. Re-appending an existing key with the same handler is a no-op,
    which keeps fan-out handlers idempotent.
    """

    default_attempts = max_attempts or get_job_settings().worker_max_attempts
    existing = {
        s.key: s
        for s in (await session.execute(select(Step).where(Step.run_id == run_id))).scalars()
    }
    batch_keys = [s.key for s in steps]
    if len(set(batch_keys)) != len(batch_keys):
        raise ValueError("duplicate step keys in batch")
    known = set(existing) | set(batch_keys)
    position = max((s.position for s in existing.values()), default=-1) + 1
    created: list[Step] = []
    for spec in steps:
        missing = [d for d in spec.depends_on if d not in known]
        if missing:
            raise ValueError(f"step {spec.key!r} depends on unknown steps {missing}")
        if spec.key in existing:
            if existing[spec.key].handler != spec.handler:
                raise ValueError(f"step {spec.key!r} already exists with another handler")
            continue
        step = Step(
            run_id=run_id,
            key=spec.key,
            handler=spec.handler,
            position=position,
            input=spec.input,
            depends_on=list(spec.depends_on),
            uses_budget=spec.uses_budget,
            tolerate_failed_deps=spec.tolerate_failed_deps,
            max_attempts=spec.max_attempts or default_attempts,
            state=StepState.PENDING,
        )
        position += 1
        session.add(step)
        created.append(step)
    await session.flush()
    if created:
        # A finished run that gains steps is live again.
        await session.execute(
            update(Run)
            .where(Run.id == run_id, Run.state.in_([RunState.DONE, RunState.FAILED]))
            .values(state=RunState.RUNNING, finished_at=None)
        )
    return created


# --- Budget --------------------------------------------------------------------


@dataclass(frozen=True)
class RunInfo:
    """Plain snapshot of a run, safe to use outside the session that loaded it."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    kind: str
    case_id: uuid.UUID | None
    discovery_run_id: uuid.UUID | None
    investor_run_id: uuid.UUID | None
    budget_credits: Decimal | None

    @classmethod
    def of(cls, run: Run) -> "RunInfo":
        return cls(
            id=run.id,
            workspace_id=run.workspace_id,
            kind=run.kind,
            case_id=run.case_id,
            discovery_run_id=run.discovery_run_id,
            investor_run_id=run.investor_run_id,
            budget_credits=run.budget_credits,
        )


async def budget_remaining(session: AsyncSession, run: Run | RunInfo) -> Decimal | None:
    """Credits left for this run's owner, or None when the run has no budget."""
    if run.budget_credits is None:
        return None
    spent = await spent_credits(
        session,
        case_id=run.case_id,
        discovery_run_id=run.discovery_run_id,
        investor_run_id=run.investor_run_id,
        run_id=run.id,
    )
    return Decimal(run.budget_credits) - spent


def cost_context(run: Run | RunInfo, step_id: uuid.UUID | None = None) -> CostContext | None:
    if run.case_id is None and run.discovery_run_id is None and run.investor_run_id is None:
        return None
    return CostContext(
        workspace_id=run.workspace_id,
        case_id=run.case_id,
        discovery_run_id=run.discovery_run_id,
        investor_run_id=run.investor_run_id,
        run_id=run.id,
        step_id=step_id,
    )


# --- Step context handed to handlers -------------------------------------------


@dataclass
class StepContext:
    run: RunInfo
    step_id: uuid.UUID
    key: str
    input: dict[str, Any]
    attempt: int
    # Handler writes go in this session; the worker commits them together with marking
    # the step done, or rolls them back if the handler fails or the lease was lost.
    session: AsyncSession
    sessionmaker: async_sessionmaker[AsyncSession]
    dependencies: dict[str, dict[str, Any]]
    cost: CostContext | None
    recorder: DbCallRecorder | None
    cache: DbCache | None
    logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.logs.append(message)
        log.info("[%s/%s] %s", self.run.id, self.key, message)

    async def budget_remaining(self) -> Decimal | None:
        async with self.sessionmaker() as session:
            return await budget_remaining(session, self.run)

    async def require_budget(self, estimate: Decimal | float | int) -> None:
        """Raise `BudgetExceeded` if a call estimated at `estimate` credits won't fit."""
        remaining = await self.budget_remaining()
        if remaining is not None and Decimal(str(estimate)) > remaining:
            raise BudgetExceeded()

    async def append_steps(self, steps: Sequence[StepSpec]) -> list[Step]:
        return await append_steps(self.session, self.run.id, steps)


# --- Claiming, leases, completion ----------------------------------------------

_CLAIM_SQL = text(
    """
    SELECT s.id
    FROM steps s
    JOIN runs r ON r.id = s.run_id
    WHERE s.state = 'pending'
      AND r.state IN ('pending', 'running')
      AND (s.next_attempt_at IS NULL OR s.next_attempt_at <= now())
      AND NOT EXISTS (
          SELECT 1 FROM steps d
          WHERE d.run_id = s.run_id
            AND jsonb_exists(s.depends_on, d.key)
            AND NOT (
                d.state = 'done'
                OR (s.tolerate_failed_deps AND d.state IN ('failed', 'skipped_budget'))
            )
      )
    ORDER BY r.created_at, s.position
    LIMIT 1
    FOR UPDATE OF s SKIP LOCKED
    """
)


async def claim_step(
    session: AsyncSession, worker_id: str, lease_seconds: float
) -> uuid.UUID | None:
    """Claim one ready step and lease it to `worker_id`. Commits."""
    step_id = (await session.execute(_CLAIM_SQL)).scalar_one_or_none()
    if step_id is None:
        await session.rollback()
        return None
    lease = timedelta(seconds=lease_seconds)
    run_id = (
        await session.execute(
            update(Step)
            .where(Step.id == step_id)
            .values(
                state=StepState.RUNNING,
                attempts=Step.attempts + 1,
                lease_owner=worker_id,
                lease_until=func.now() + lease,
                started_at=func.coalesce(Step.started_at, func.now()),
                next_attempt_at=None,
            )
            .returning(Step.run_id)
        )
    ).scalar_one()
    await session.execute(
        update(Run)
        .where(Run.id == run_id, Run.state == RunState.PENDING)
        .values(state=RunState.RUNNING)
    )
    await session.commit()
    return step_id


async def renew_lease(
    session: AsyncSession, step_id: uuid.UUID, worker_id: str, lease_seconds: float
) -> bool:
    result = await session.execute(
        update(Step)
        .where(Step.id == step_id, Step.lease_owner == worker_id, Step.state == StepState.RUNNING)
        .values(lease_until=func.clock_timestamp() + timedelta(seconds=lease_seconds))
    )
    await session.commit()
    return result.rowcount == 1  # type: ignore[attr-defined]


async def reclaim_expired_leases(session: AsyncSession) -> list[uuid.UUID]:
    """Return steps whose lease expired to the queue (or fail them if out of attempts).

    Called on every worker loop iteration, so a crashed worker's steps are picked up
    while the system keeps running, not only at boot. Commits.
    """
    rows = (
        await session.execute(
            select(Step)
            .where(Step.state == StepState.RUNNING, Step.lease_until < func.now())
            .with_for_update(skip_locked=True)
        )
    ).scalars()
    reclaimed: list[uuid.UUID] = []
    failed_runs: set[uuid.UUID] = set()
    for step in rows:
        expired_owner = step.lease_owner
        step.lease_owner = None
        step.lease_until = None
        if step.attempts >= step.max_attempts:
            step.state = StepState.FAILED
            step.error = f"lease expired (worker {expired_owner}) after {step.attempts} attempts"
            step.finished_at = func.now()
            failed_runs.add(step.run_id)
        else:
            step.state = StepState.PENDING
            step.next_attempt_at = None
            step.error = f"lease expired (worker {expired_owner}); retrying"
        reclaimed.append(step.id)
    await session.flush()
    for run_id in failed_runs:
        await propagate_and_complete(session, run_id)
    await session.commit()
    return reclaimed


async def mark_done(
    session: AsyncSession, step_id: uuid.UUID, worker_id: str, output: dict[str, Any] | None
) -> None:
    """Fenced completion, in the handler's own transaction. Raises `LeaseLost`."""
    result = await session.execute(
        update(Step)
        .where(Step.id == step_id, Step.lease_owner == worker_id, Step.state == StepState.RUNNING)
        .values(
            state=StepState.DONE,
            output=output or {},
            error=None,
            lease_owner=None,
            lease_until=None,
            finished_at=func.now(),
        )
        .returning(Step.run_id)
    )
    run_id = result.scalar_one_or_none()
    if run_id is None:
        raise LeaseLost(str(step_id))
    await propagate_and_complete(session, run_id)


async def mark_retry_or_failed(
    session: AsyncSession,
    step_id: uuid.UUID,
    worker_id: str,
    error: str,
    *,
    retry_base: float,
    retry_max: float,
    retryable: bool = True,
) -> str | None:
    """After a handler error: back off and retry, or fail when out of attempts."""
    step = (
        await session.execute(
            select(Step)
            .where(
                Step.id == step_id,
                Step.lease_owner == worker_id,
                Step.state == StepState.RUNNING,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if step is None:
        await session.rollback()
        return None
    step.error = error[:4000]
    step.lease_owner = None
    step.lease_until = None
    if retryable and step.attempts < step.max_attempts:
        delay = min(retry_base * (2 ** (step.attempts - 1)), retry_max)
        step.state = StepState.PENDING
        step.next_attempt_at = func.now() + timedelta(seconds=delay)
    else:
        step.state = StepState.FAILED
        step.finished_at = func.now()
    await session.flush()
    await propagate_and_complete(session, step.run_id)
    await session.commit()
    return step.state


async def mark_skipped_budget(
    session: AsyncSession, step_id: uuid.UUID, worker_id: str, reason: str = BUDGET_REACHED
) -> bool:
    result = await session.execute(
        update(Step)
        .where(Step.id == step_id, Step.lease_owner == worker_id, Step.state == StepState.RUNNING)
        .values(
            state=StepState.SKIPPED_BUDGET,
            skip_reason=reason,
            lease_owner=None,
            lease_until=None,
            finished_at=func.now(),
        )
        .returning(Step.run_id)
    )
    run_id = result.scalar_one_or_none()
    if run_id is None:
        await session.rollback()
        return False
    await propagate_and_complete(session, run_id)
    await session.commit()
    return True


async def skip_remaining_budgeted(session: AsyncSession, run_id: uuid.UUID) -> int:
    """Budget is spent: every pending step that needs credits becomes skipped_budget."""
    result = await session.execute(
        update(Step)
        .where(
            Step.run_id == run_id,
            Step.state == StepState.PENDING,
            Step.uses_budget.is_(True),
        )
        .values(state=StepState.SKIPPED_BUDGET, skip_reason=BUDGET_REACHED, finished_at=func.now())
    )
    await propagate_and_complete(session, run_id)
    return result.rowcount  # type: ignore[attr-defined,no-any-return]


async def propagate_and_complete(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Push failures/skips to dependents that don't tolerate them, then close the run
    if every step is terminal."""
    # Serialise per run: without this, two workers finishing the last two steps at
    # the same time each see the other's step still running and nobody closes the run.
    await session.execute(select(Run.id).where(Run.id == run_id).with_for_update())
    steps = list(
        (
            await session.execute(
                select(Step).where(Step.run_id == run_id).execution_options(populate_existing=True)
            )
        ).scalars()
    )
    by_key = {s.key: s for s in steps}
    changed = True
    while changed:
        changed = False
        for step in steps:
            if step.state != StepState.PENDING or step.tolerate_failed_deps:
                continue
            deps = [by_key[k] for k in step.depends_on if k in by_key]
            failed = [d.key for d in deps if d.state == StepState.FAILED]
            skipped = [d.key for d in deps if d.state == StepState.SKIPPED_BUDGET]
            if failed:
                step.state = StepState.FAILED
                step.error = f"dependency failed: {', '.join(failed)}"
            elif skipped:
                step.state = StepState.SKIPPED_BUDGET
                step.skip_reason = BUDGET_REACHED
            else:
                continue
            step.finished_at = func.now()
            changed = True
    await session.flush()
    if steps and all(s.state in TERMINAL_STEP_STATES for s in steps):
        any_failed = any(s.state == StepState.FAILED for s in steps)
        await session.execute(
            update(Run)
            .where(Run.id == run_id, Run.state.in_([RunState.PENDING, RunState.RUNNING]))
            .values(
                state=RunState.FAILED if any_failed else RunState.DONE,
                finished_at=func.now(),
                error="one or more steps failed" if any_failed else None,
            )
        )


async def resume_run(session: AsyncSession, run_id: uuid.UUID) -> int:
    """Put failed and budget-skipped steps back in the queue (after a fix or a budget
    increase). Steps that are done stay done. Returns how many were re-queued."""
    result = await session.execute(
        update(Step)
        .where(
            Step.run_id == run_id,
            Step.state.in_([StepState.FAILED, StepState.SKIPPED_BUDGET]),
        )
        .values(
            state=StepState.PENDING,
            attempts=0,
            error=None,
            skip_reason=None,
            next_attempt_at=None,
            finished_at=None,
        )
    )
    count = result.rowcount  # type: ignore[attr-defined]
    if count:
        await session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(state=RunState.RUNNING, finished_at=None, error=None)
        )
    return count  # type: ignore[no-any-return]


async def dependency_outputs(
    session: AsyncSession, run_id: uuid.UUID, keys: Iterable[str]
) -> dict[str, dict[str, Any]]:
    keys = list(keys)
    if not keys:
        return {}
    rows = (
        await session.execute(
            select(Step.key, Step.state, Step.output, Step.skip_reason, Step.error).where(
                Step.run_id == run_id, Step.key.in_(keys)
            )
        )
    ).all()
    return {
        r.key: {
            "state": r.state,
            "output": r.output,
            "skip_reason": r.skip_reason,
            "error": r.error,
        }
        for r in rows
    }
