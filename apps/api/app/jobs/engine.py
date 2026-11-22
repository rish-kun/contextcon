"""Runs and steps: creation, claiming, leases, completion and budget.

A Run is a set of Steps. A step is `pending → running → done | failed | skipped_budget`.
Workers claim one ready step at a time with `SELECT … FOR UPDATE SKIP LOCKED`, hold a
lease they renew while the handler runs, and lose the step back to the queue if the
lease expires. Each claim gets a fresh `lease_token`. Renewal, completion and failure
require that token *and* an unexpired lease, and the recorder checks the same before
every paid dispatch, so a worker that lost its lease can neither overwrite the result
of the worker that took over nor start new paid calls.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.adapters import DbCache, DbCallRecorder
from app.db.enums import TERMINAL_STEP_STATES, RunState, StepState
from app.db.errors import BUDGET_REACHED, BudgetExceeded, LeaseLost
from app.db.ledger import CostContext, budget_used
from app.db.models import Case, DiscoveryRun, InvestorRun, Run, Step
from app.jobs.activity import ActivityEmitter, NullEmitter
from app.jobs.config import get_job_settings
from app.settings import get_settings

log = logging.getLogger(__name__)

__all__ = ["BUDGET_REACHED", "BudgetExceeded", "LeaseLost"]  # re-exported for handlers


def public_error(exc: BaseException) -> str:
    """What a step stores and the API shows for a handler error: the error type only.

    Exception messages are untrusted (they can carry URLs, keys or document text), so
    they go to the server log (`log.exception` in the worker), never to the database.
    """
    return type(exc).__name__


@dataclass(frozen=True)
class StepSpec:
    key: str
    handler: str
    # Human label for the progress list; defaults to the key.
    label: str | None = None
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

    The owner (case, discovery run or investor run) must belong to `workspace_id`;
    this is checked whether or not a budget is given (and enforced again by composite
    foreign keys). Raises `LookupError` otherwise.

    Case runs get the case's `credit_budget`, else `CASE_CREDIT_BUDGET`; the budget is
    per case, so every run of the case draws on the same credits. Discovery and
    investor runs default to `DISCOVER_CREDIT_BUDGET` / `INVESTOR_CREDIT_BUDGET`.
    """
    owners = [o for o in (case_id, discovery_run_id, investor_run_id) if o is not None]
    if len(owners) > 1:
        raise ValueError("a run has at most one owner")
    if case_id is not None:
        case_row = await _owned(session, Case, case_id, workspace_id, "case")
        if budget_credits is None:
            budget_credits = case_row.credit_budget
        if budget_credits is None:
            budget_credits = get_settings().case_credit_budget
    if discovery_run_id is not None:
        await _owned(session, DiscoveryRun, discovery_run_id, workspace_id, "discovery run")
        if budget_credits is None:
            budget_credits = get_job_settings().discover_credit_budget
    if investor_run_id is not None:
        await _owned(session, InvestorRun, investor_run_id, workspace_id, "investor run")
        if budget_credits is None:
            budget_credits = get_job_settings().investor_credit_budget
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


async def _owned(
    session: AsyncSession, model: type, owner_id: uuid.UUID, workspace_id: uuid.UUID, label: str
) -> Any:
    row = await session.get(model, owner_id)
    if row is None or row.workspace_id != workspace_id:
        raise LookupError(f"{label} not found in this workspace")
    return row


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
            label=spec.label or spec.key,
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
    """Credits left for this run's owner, or None when the run has no budget.

    Counts settled spend, unknown-cost dispatches at their reserved estimate, and
    reservations still held by in-flight (or crashed) dispatches (`budget_used`)."""
    ctx = cost_context(run)
    if run.budget_credits is None or ctx is None:
        return None
    return Decimal(run.budget_credits) - await budget_used(session, ctx)


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
    # One-line result shown when the step is done ("3 matches; identity confirmed").
    result: str | None = None
    # This claim's fencing token (the recorder checks it before every paid dispatch).
    lease_token: uuid.UUID | None = None
    # Set by `keep_output_confidential()`: the output goes to an expiring payload.
    confidential_output: bool = False
    confidential_output_until: datetime | None = None
    # The live activity stream (`app.jobs.activity`): `await ctx.activity.status(...)`,
    # `.source`, `.finding`, `.notice`. The worker gives each step its own emitter.
    activity: ActivityEmitter = field(default_factory=NullEmitter)

    async def set_detail(self, detail: str) -> None:
        """Live sub-line while the step runs; visible to the SSE stream at once. Also a
        `status` activity with the same words, so pass public words only: never a
        filename, claim text or anything read from a document."""
        async with self.sessionmaker() as session:
            await session.execute(
                update(Step).where(Step.id == self.step_id).values(detail=detail[:500])
            )
            await session.commit()
        await self.activity.status(detail)

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

    def keep_output_confidential(self, delete_after: datetime | None = None) -> None:
        """This step's output carries confidential (document-derived) text.

        The worker stores the output in an expiring `confidential_payloads` row
        (default expiry: the earlier of now + UPLOAD_RETENTION_DAYS and the case's next
        document deletion) and leaves a marker on the step. Dependents still read it
        via `ctx.dependencies` until then. Case runs only. See `app.jobs.retention`."""
        if self.run.case_id is None:
            raise ValueError("confidential outputs need a case run")
        self.confidential_output = True
        self.confidential_output_until = delete_after

    async def store_confidential(
        self, payload: Any, *, kind: str, assessment_version_id: uuid.UUID | None = None
    ) -> dict[str, str]:
        """Store confidential JSON apart from a snapshot (e.g. an assessment version's
        input excerpts) and return the reference to embed instead. Written in the
        step's session, so it commits with the step."""
        from app.jobs.retention import confidential_ref, store_confidential

        if self.run.case_id is None:
            raise ValueError("confidential payloads need a case run")
        payload_id = await store_confidential(
            self.session,
            workspace_id=self.run.workspace_id,
            case_id=self.run.case_id,
            kind=kind,
            payload=payload,
            run_id=self.run.id,
            assessment_version_id=assessment_version_id,
        )
        return confidential_ref(payload_id)


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


@dataclass(frozen=True)
class StepClaim:
    """A claimed step and the fencing token every later state change must present."""

    id: uuid.UUID
    token: uuid.UUID


def _live(token: uuid.UUID) -> Any:
    """Fence: this claim's token, still running, lease not yet expired (wall clock, not
    transaction start, so a long handler transaction cannot use a stale `now()`)."""
    return (
        (Step.lease_token == token)
        & (Step.state == StepState.RUNNING)
        & (Step.lease_until > func.clock_timestamp())
    )


async def lease_is_live(session: AsyncSession, step_id: uuid.UUID, token: uuid.UUID) -> bool:
    found = await session.execute(select(Step.id).where(Step.id == step_id, _live(token)))
    return found.first() is not None


async def claim_step(
    session: AsyncSession, worker_id: str, lease_seconds: float
) -> StepClaim | None:
    """Claim one ready step and lease it to `worker_id` under a new token. Commits."""
    step_id = (await session.execute(_CLAIM_SQL)).scalar_one_or_none()
    if step_id is None:
        await session.rollback()
        return None
    token = uuid.uuid4()
    lease = timedelta(seconds=lease_seconds)
    run_id = (
        await session.execute(
            update(Step)
            .where(Step.id == step_id)
            .values(
                state=StepState.RUNNING,
                attempts=Step.attempts + 1,
                lease_owner=worker_id,
                lease_token=token,
                lease_until=func.clock_timestamp() + lease,
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
    return StepClaim(step_id, token)


async def renew_lease(
    session: AsyncSession, step_id: uuid.UUID, token: uuid.UUID, lease_seconds: float
) -> bool:
    """Extend a live lease. False once the lease expired or the step was re-claimed."""
    result = await session.execute(
        update(Step)
        .where(Step.id == step_id, _live(token))
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
    resumed_runs: set[uuid.UUID] = set()
    for step in rows:
        log.warning("step %s: lease of %s expired; reclaiming", step.id, step.lease_owner)
        step.lease_owner = None
        step.lease_token = None
        step.lease_until = None
        if step.attempts >= step.max_attempts:
            step.state = StepState.FAILED
            step.error = f"interrupted {step.attempts} times; giving up"
            step.finished_at = func.now()
            failed_runs.add(step.run_id)
        else:
            step.state = StepState.PENDING
            step.next_attempt_at = None
            step.error = "interrupted; retrying"
            resumed_runs.add(step.run_id)
        reclaimed.append(step.id)
    await session.flush()
    if resumed_runs:
        await session.execute(
            update(Run).where(Run.id.in_(resumed_runs)).values(resumed_at=func.now())
        )
    for run_id in failed_runs:
        await propagate_and_complete(session, run_id)
    await session.commit()
    return reclaimed


async def mark_done(
    session: AsyncSession,
    step_id: uuid.UUID,
    token: uuid.UUID,
    output: dict[str, Any] | None,
    result: str | None = None,
    *,
    confidential_output_id: uuid.UUID | None = None,
) -> None:
    """Fenced completion, in the handler's own transaction. Raises `LeaseLost`."""
    result = await session.execute(
        update(Step)
        .where(Step.id == step_id, _live(token))
        .values(
            state=StepState.DONE,
            output=output or {},
            confidential_output_id=confidential_output_id,
            result=None if result is None else result[:500],
            detail=None,
            error=None,
            lease_owner=None,
            lease_token=None,
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
    token: uuid.UUID,
    error: str,
    *,
    retry_base: float,
    retry_max: float,
    retryable: bool = True,
) -> str | None:
    """After a handler error: back off and retry, or fail when out of attempts."""
    step = (
        await session.execute(
            select(Step).where(Step.id == step_id, _live(token)).with_for_update()
        )
    ).scalar_one_or_none()
    if step is None:
        await session.rollback()
        return None
    step.error = error[:4000]
    step.lease_owner = None
    step.lease_token = None
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
    session: AsyncSession, step_id: uuid.UUID, token: uuid.UUID, reason: str = BUDGET_REACHED
) -> bool:
    result = await session.execute(
        update(Step)
        .where(Step.id == step_id, _live(token))
        .values(
            state=StepState.SKIPPED_BUDGET,
            skip_reason=reason,
            lease_owner=None,
            lease_token=None,
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
            .values(state=RunState.RUNNING, finished_at=None, error=None, resumed_at=func.now())
        )
    return count  # type: ignore[no-any-return]


async def dependency_outputs(
    session: AsyncSession, run_id: uuid.UUID, keys: Iterable[str]
) -> dict[str, dict[str, Any]]:
    keys = list(keys)
    if not keys:
        return {}
    from app.jobs.retention import CONFIDENTIAL_MARKER, EXPIRED_OUTPUT, load_confidential

    rows = (
        await session.execute(
            select(
                Step.key,
                Step.state,
                Step.output,
                Step.skip_reason,
                Step.error,
                Step.confidential_output_id,
            ).where(Step.run_id == run_id, Step.key.in_(keys))
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        output = r.output
        if r.output == CONFIDENTIAL_MARKER:
            # Stored apart; gone once purged (link nulled) or past its expiry.
            payload = None
            if r.confidential_output_id is not None:
                payload = await load_confidential(session, r.confidential_output_id)
            output = EXPIRED_OUTPUT if payload is None else payload
        out[r.key] = {
            "state": r.state,
            "output": output,
            "skip_reason": r.skip_reason,
            "error": r.error,
        }
    return out
