"""Database-backed implementations of the hooks in `app.clients.base`.

`DbCallRecorder` implements `CallRecorder` plus the optional operation hooks:

- `operation_key(cache_key)`: a stable key per external call within the step
  (step id, the call's request hash, and its occurrence number in the step), shared by
  that call's dispatches. A resumed step computes the same keys.
- `reconcile(operation_key)`: an attempt with that key still `started` was left by a
  worker that crashed or lost its lease. It becomes `unknown` with an unknown-cost
  ledger entry, so it is never silently free; the caller then looks in the cache
  (under the lock) before paying again.
- `before_dispatch(record)`: in one transaction, checks that this worker's claim token
  is still live (`LeaseLost` otherwise), reserves the dispatch's estimated credits
  against the owner's budget under a row lock on `credit_budgets`
  (`BudgetExceeded` otherwise), and inserts the `started` attempt holding that
  reservation. Committed before the request leaves.
- `finish(record, cache=..., cache_value=...)`: the final attempt row, its
  `cost_entries` row and the cache entry are written in one transaction, so a crash
  leaves either all of them or none (and then a `started` row to reconcile).

`DbCache` implements `ResponseCache` over `api_cache`, plus `lock(key)` (a
transaction-scoped advisory lock that serialises concurrent misses on one key) and
`confidential()` (a case-scoped, expiring view).

    ctx = CostContext(workspace_id, case_id=case.id, run_id=run.id, step_id=step.id)
    client = CrustdataClient(key, recorder=DbCallRecorder(sm, ctx), cache=DbCache(sm, ctx))

Inside a job step these come ready-made as `ctx.recorder` and `ctx.cache`.
"""

import hashlib
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.activity import CallReport
from app.clients.base import CallRecord, safe_error_code, stable_hash
from app.db.enums import CallStatus, StepState
from app.db.errors import BudgetExceeded, LeaseLost
from app.db.ledger import CostContext, budget_used, record_cost
from app.db.models import (
    ApiCache,
    CallAttempt,
    CostEntry,
    CreditBudget,
    Document,
    Run,
    Step,
)
from app.settings import get_settings

_FINAL = {CallStatus.SUCCEEDED, CallStatus.FAILED, CallStatus.UNKNOWN}


def retention_deadline(now: datetime | None = None) -> datetime:
    """Default `delete_after` for confidential derivatives: now + UPLOAD_RETENTION_DAYS."""
    return (now or datetime.now(UTC)) + timedelta(days=get_settings().upload_retention_days)


def confidential_delete_after_sql(case_id: uuid.UUID) -> Any:
    """SQL for a confidential derivative's `delete_after`: the earlier of the retention
    deadline and the case's next pending document deletion (LEAST ignores the NULL
    when the case has no documents), so a derivative never outlives its source."""
    next_document = (
        select(func.min(Document.delete_after))
        .where(Document.case_id == case_id, Document.deleted_at.is_(None))
        .scalar_subquery()
    )
    return func.least(retention_deadline(), next_document)


def _dec(value: float | None) -> Decimal:
    return Decimal(0) if value is None else Decimal(str(value))


def _advisory_key(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)


class DbCallRecorder:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        ctx: CostContext,
        *,
        lease_token: uuid.UUID | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self.ctx = ctx
        self.lease_token = lease_token
        self._occurrences: Counter[str] = Counter()
        self.activity_sink: Callable[[CallReport], Awaitable[None]] | None = None
        self._mine: set[str] = set()

    # --- operation hooks ----------------------------------------------------------

    def operation_key(self, cache_key: str) -> str | None:
        if self.ctx.step_id is None:
            return None
        n = self._occurrences[cache_key]
        self._occurrences[cache_key] += 1
        return stable_hash({"step": str(self.ctx.step_id), "call": cache_key, "n": n})

    async def reconcile(self, operation_key: str) -> int:
        """Settle attempts a previous worker left `started` for this operation."""
        async with self._sessionmaker() as session:
            rows = list(
                (
                    await session.execute(
                        select(CallAttempt)
                        .where(
                            CallAttempt.operation_key == operation_key,
                            CallAttempt.status == CallStatus.STARTED,
                            CallAttempt.call_id.not_in(self._mine or {""}),
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).scalars()
            )
            for row in rows:
                row.status = CallStatus.UNKNOWN
                row.error = "interrupted"
                row.finished_at = func.now()
                await session.execute(
                    insert(CostEntry)
                    .values(
                        id=uuid.uuid4(),
                        workspace_id=row.workspace_id,
                        case_id=row.case_id,
                        discovery_run_id=row.discovery_run_id,
                        investor_run_id=row.investor_run_id,
                        run_id=row.run_id,
                        step_id=row.step_id,
                        call_attempt_id=row.id,
                        provider=row.provider,
                        endpoint=row.endpoint,
                        unknown=True,
                    )
                    .on_conflict_do_nothing(index_elements=[CostEntry.call_attempt_id])
                )
            await session.commit()
            return len(rows)

    async def before_dispatch(self, record: CallRecord) -> None:
        estimate = _dec(record.credits_estimate)
        async with self._sessionmaker() as session:
            if self.lease_token is not None and self.ctx.step_id is not None:
                if not await self._lease_live(session):
                    await session.rollback()
                    raise LeaseLost(str(self.ctx.step_id))
            if estimate > 0:
                limit = await self._budget_limit(session)
                if limit is not None:
                    await self._lock_budget(session)
                    if await budget_used(session, self.ctx) + estimate > limit:
                        await session.rollback()
                        raise BudgetExceeded()
            await session.execute(self._upsert(record, reserved=estimate))
            await session.commit()
        self._mine.add(record.call_id)

    async def finish(
        self, record: CallRecord, *, cache: Any = None, cache_value: Any | None = None
    ) -> None:
        deferred = False
        async with self._sessionmaker() as session:
            attempt_id = (await session.execute(self._upsert(record))).scalar_one()
            await self._settle(session, attempt_id, record)
            if cache is not None and cache_value is not None:
                if isinstance(cache, DbCache):
                    await session.execute(
                        cache.insert_statement(
                            record.cache_key, cache_value, record.provider, record.endpoint
                        )
                    )
                else:
                    deferred = True
            await session.commit()
        if deferred:
            await cache.set(record.cache_key, cache_value)

    async def activity(self, report: CallReport) -> None:
        """The clients' live-activity hook. Inside a job step the worker points
        `activity_sink` at the step's emitter (`ctx.activity.report`)."""
        if self.activity_sink is not None:
            await self.activity_sink(report)

    # --- plain recorder (cache hits, and clients without the operation hooks) ------

    async def __call__(self, record: CallRecord) -> None:
        async with self._sessionmaker() as session:
            attempt_id = (await session.execute(self._upsert(record))).scalar_one()
            # A cache hit costs nothing and gets no ledger row of its own (a reuse of
            # another owner's data is recorded by `DbCache.get`).
            if CallStatus(record.status) in _FINAL:
                await self._settle(session, attempt_id, record)
            await session.commit()

    # --- internals ------------------------------------------------------------------

    def _upsert(self, record: CallRecord, *, reserved: Decimal | None = None) -> Any:
        values: dict[str, Any] = {
            "provider": record.provider,
            "endpoint": record.endpoint,
            "params_hash": record.params_hash,
            "cache_key": record.cache_key,
            "model": record.model,
            "status": CallStatus(record.status),
            "http_status": record.http_status,
            "http_attempts": record.attempts,
            "provider_request_id": record.provider_request_id,
            "error": safe_error_code(record.error),
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "operation_key": record.operation_key,
            "dispatch_index": record.dispatch_index,
        }
        insert_values = {**values, "reserved_credits": reserved or Decimal(0)}
        return (
            insert(CallAttempt)
            .values(
                id=uuid.uuid4(),
                call_id=record.call_id,
                workspace_id=self.ctx.workspace_id,
                case_id=self.ctx.case_id,
                discovery_run_id=self.ctx.discovery_run_id,
                investor_run_id=self.ctx.investor_run_id,
                run_id=self.ctx.run_id,
                step_id=self.ctx.step_id,
                **insert_values,
            )
            .on_conflict_do_update(index_elements=[CallAttempt.call_id], set_=values)
            .returning(CallAttempt.id)
        )

    async def _settle(
        self, session: AsyncSession, attempt_id: uuid.UUID, record: CallRecord
    ) -> None:
        """One ledger row per attempt. A known figure replaces an earlier unknown one
        (a reconciled attempt whose worker did finish); otherwise a repeated final
        report changes nothing."""
        values = {
            "credits": _dec(record.credits_used),
            "input_tokens": record.input_tokens or 0,
            "output_tokens": record.output_tokens or 0,
            "usd": _dec(record.cost_usd),
            "unknown": not record.usage_known,
            "cached": record.from_cache,
        }
        await session.execute(
            insert(CostEntry)
            .values(
                id=uuid.uuid4(),
                workspace_id=self.ctx.workspace_id,
                case_id=self.ctx.case_id,
                discovery_run_id=self.ctx.discovery_run_id,
                investor_run_id=self.ctx.investor_run_id,
                run_id=self.ctx.run_id,
                step_id=self.ctx.step_id,
                call_attempt_id=attempt_id,
                provider=record.provider,
                endpoint=record.endpoint,
                **values,
            )
            .on_conflict_do_update(
                index_elements=[CostEntry.call_attempt_id],
                set_=values,
                where=CostEntry.unknown.is_(True),
            )
        )

    async def _lease_live(self, session: AsyncSession) -> bool:
        found = await session.execute(
            select(Step.id).where(
                Step.id == self.ctx.step_id,
                Step.lease_token == self.lease_token,
                Step.state == StepState.RUNNING,
                Step.lease_until > func.clock_timestamp(),
            )
        )
        return found.first() is not None

    async def _budget_limit(self, session: AsyncSession) -> Decimal | None:
        if self.ctx.run_id is None:
            return None
        limit = await session.scalar(select(Run.budget_credits).where(Run.id == self.ctx.run_id))
        return None if limit is None else Decimal(limit)

    async def _lock_budget(self, session: AsyncSession) -> None:
        owner = self.ctx.owner_filter
        await session.execute(
            insert(CreditBudget)
            .values(id=uuid.uuid4(), workspace_id=self.ctx.workspace_id, **owner)
            .on_conflict_do_nothing()
        )
        ((column, owner_id),) = owner.items()
        await session.execute(
            select(CreditBudget.id)
            .where(getattr(CreditBudget, column) == owner_id)
            .with_for_update()
        )


class DbCache:
    """`api_cache`-backed cache.

    The default scope is the workspace, for public lookups only (Crustdata requests
    are built from public terms): a case reuses what its discovery run already paid
    for, and that hit is recorded as a zero-cost ledger entry linked to the paying run
    (no double counting). Nothing is served across workspaces.

    `confidential()` (or `confidential=True`) scopes keys to one case and stamps
    `delete_after` (default: the earlier of now + UPLOAD_RETENTION_DAYS and the case's
    next document deletion), so a response derived from private case text is never
    served to another case and never outlives the retention schedule. Expired rows
    are never returned, even before the purge job deletes them.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        ctx: CostContext,
        *,
        confidential: bool = False,
        delete_after: datetime | None = None,
        record_shared_hits: bool = True,
    ) -> None:
        if confidential and ctx.case_id is None:
            raise ValueError("a confidential cache needs a case")
        self._sessionmaker = sessionmaker
        self.ctx = ctx
        self.confidential_scope = confidential
        self.delete_after = delete_after
        self.record_shared_hits = record_shared_hits

    def confidential(self, delete_after: datetime | None = None) -> "DbCache | None":
        """The case-scoped, expiring view (None outside a case: then don't cache)."""
        if self.ctx.case_id is None:
            return None
        if self.confidential_scope and delete_after is None:
            return self
        return DbCache(
            self._sessionmaker,
            self.ctx,
            confidential=True,
            delete_after=delete_after or self.delete_after,
            record_shared_hits=False,
        )

    def storage_key(self, key: str) -> str:
        if self.confidential_scope:
            return f"case:{self.ctx.case_id}:{key}"
        return f"ws:{self.ctx.workspace_id}:{key}"

    @asynccontextmanager
    async def lock(self, key: str) -> AsyncIterator[None]:
        """Serialise concurrent misses on one key: the second caller waits here, then
        finds the first caller's entry instead of paying again. Transaction-scoped,
        so it is released on commit, rollback or a dropped connection."""
        async with self._sessionmaker() as session:
            await session.execute(
                select(func.pg_advisory_xact_lock(_advisory_key(self.storage_key(key))))
            )
            try:
                yield
            finally:
                await session.rollback()

    async def get(self, key: str) -> Any | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    update(ApiCache)
                    .where(
                        ApiCache.cache_key == self.storage_key(key),
                        or_(ApiCache.delete_after.is_(None), ApiCache.delete_after > func.now()),
                    )
                    .values(hit_count=ApiCache.hit_count + 1)
                    .returning(ApiCache)
                )
            ).scalar_one_or_none()
            if row is None:
                await session.rollback()
                return None
            if self.record_shared_hits and not self._same_owner(row):
                await record_cost(
                    session,
                    self.ctx,
                    provider=row.provider or "unknown",
                    endpoint=row.endpoint or "unknown",
                    cached=True,
                    shared_from_run_id=row.origin_run_id,
                )
            response = row.response
            await session.commit()
            return response

    async def set(
        self, key: str, value: Any, *, provider: str | None = None, endpoint: str | None = None
    ) -> None:
        async with self._sessionmaker() as session:
            if provider is None:
                # The clients pass only (key, value); the call that produced the value
                # was recorded under the same cache key.
                found = (
                    await session.execute(
                        select(CallAttempt.provider, CallAttempt.endpoint)
                        .where(
                            CallAttempt.cache_key == key,
                            CallAttempt.workspace_id == self.ctx.workspace_id,
                        )
                        .order_by(CallAttempt.created_at.desc())
                        .limit(1)
                    )
                ).first()
                if found is not None:
                    provider, endpoint = found
            await session.execute(self.insert_statement(key, value, provider, endpoint))
            await session.commit()

    def insert_statement(
        self, key: str, value: Any, provider: str | None, endpoint: str | None
    ) -> Any:
        delete_after: Any = None
        if self.confidential_scope:
            delete_after = self.delete_after or self._default_delete_after()
        return (
            insert(ApiCache)
            .values(
                id=uuid.uuid4(),
                cache_key=self.storage_key(key),
                provider=provider,
                endpoint=endpoint,
                response=value,
                confidential=self.confidential_scope,
                workspace_id=self.ctx.workspace_id,
                case_id=self.ctx.case_id if self.confidential_scope else None,
                delete_after=delete_after,
                origin_run_id=self.ctx.run_id,
                origin_case_id=self.ctx.case_id,
                origin_discovery_run_id=self.ctx.discovery_run_id,
                origin_investor_run_id=self.ctx.investor_run_id,
            )
            .on_conflict_do_nothing(index_elements=[ApiCache.cache_key])
        )

    def _default_delete_after(self) -> Any:
        assert self.ctx.case_id is not None
        return confidential_delete_after_sql(self.ctx.case_id)

    def _same_owner(self, row: ApiCache) -> bool:
        kind, owner_id = self.ctx.owner
        origin = {
            "case": row.origin_case_id,
            "discovery_run": row.origin_discovery_run_id,
            "investor_run": row.origin_investor_run_id,
        }[kind]
        return origin == owner_id
