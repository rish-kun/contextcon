"""Database-backed implementations of the hooks in `app.clients.base`.

- `DbCallRecorder` implements `CallRecorder`: the clients report each `CallRecord`
  as `started` (before the request), then `succeeded` / `failed`, or once as
  `cache_hit`. Reports share a `call_id`, so each one upserts a `call_attempts` row;
  the final report also writes the `cost_entries` row.
- `DbCache` implements `ResponseCache` (`get(key)` / `set(key, value)`) over
  `api_cache`.

Each write is its own short transaction, so the `started` row is committed before the
request leaves and survives a crash of the step that made the call.

    ctx = CostContext(workspace_id, case_id=case.id, run_id=run.id, step_id=step.id)
    client = CrustdataClient(key, recorder=DbCallRecorder(sm, ctx), cache=DbCache(sm, ctx))

Inside a job step these come ready-made as `ctx.recorder` and `ctx.cache`.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.base import CallRecord
from app.db.enums import CallStatus
from app.db.ledger import CostContext, record_cost
from app.db.models import ApiCache, CallAttempt, CostEntry

_FINAL = {CallStatus.SUCCEEDED, CallStatus.FAILED}


def _short_error(error: str | None) -> str | None:
    return None if error is None else error[:1000]


class DbCallRecorder:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], ctx: CostContext):
        self._sessionmaker = sessionmaker
        self.ctx = ctx

    async def __call__(self, record: CallRecord) -> None:
        status = CallStatus(record.status)
        values: dict[str, Any] = {
            "provider": record.provider,
            "endpoint": record.endpoint,
            "params_hash": record.params_hash,
            "cache_key": record.cache_key,
            "model": record.model,
            "status": status,
            "http_status": record.http_status,
            "http_attempts": record.attempts,
            "provider_request_id": record.provider_request_id,
            "error": _short_error(record.error),
            "started_at": record.started_at,
            "finished_at": record.finished_at,
        }
        stmt = (
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
                **values,
            )
            .on_conflict_do_update(index_elements=[CallAttempt.call_id], set_=values)
            .returning(CallAttempt.id)
        )
        async with self._sessionmaker() as session:
            attempt_id = (await session.execute(stmt)).scalar_one()
            if status in _FINAL:
                await self._record_cost(session, attempt_id, record)
            await session.commit()

    async def _record_cost(
        self, session: AsyncSession, attempt_id: uuid.UUID, record: CallRecord
    ) -> None:
        exists = await session.execute(
            select(CostEntry.id).where(CostEntry.call_attempt_id == attempt_id)
        )
        if exists.first() is not None:  # a repeated final report must not double count
            return
        await record_cost(
            session,
            self.ctx,
            provider=record.provider,
            endpoint=record.endpoint,
            credits=Decimal(str(record.credits_used or 0)),
            input_tokens=record.input_tokens or 0,
            output_tokens=record.output_tokens or 0,
            usd=Decimal(str(record.cost_usd or 0)),
            unknown=not record.usage_known,
            cached=record.from_cache,
            call_attempt_id=attempt_id,
        )


class DbCache:
    """`api_cache`-backed cache.

    Keys are scoped to the workspace, so nothing is served across tenants. Within a
    workspace, public data is shared: a case reuses what its discovery run already
    paid for, and that hit is recorded as a zero-cost ledger entry linked to the paying
    run (no double counting).

    `confidential=True` scopes keys to one case and stamps `delete_after`, so the purge
    job removes them and other cases never see them.
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
        if confidential and (ctx.case_id is None or delete_after is None):
            raise ValueError("a confidential cache needs a case and a delete_after")
        self._sessionmaker = sessionmaker
        self.ctx = ctx
        self.confidential = confidential
        self.delete_after = delete_after
        self.record_shared_hits = record_shared_hits

    def storage_key(self, key: str) -> str:
        if self.confidential:
            return f"case:{self.ctx.case_id}:{key}"
        return f"ws:{self.ctx.workspace_id}:{key}"

    async def get(self, key: str) -> Any | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    update(ApiCache)
                    .where(ApiCache.cache_key == self.storage_key(key))
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
            await session.execute(self._insert(key, value, provider, endpoint))
            await session.commit()

    def _insert(self, key: str, value: Any, provider: str | None, endpoint: str | None) -> Any:
        return (
            insert(ApiCache)
            .values(
                id=uuid.uuid4(),
                cache_key=self.storage_key(key),
                provider=provider,
                endpoint=endpoint,
                response=value,
                confidential=self.confidential,
                workspace_id=self.ctx.workspace_id,
                case_id=self.ctx.case_id if self.confidential else None,
                delete_after=self.delete_after if self.confidential else None,
                origin_run_id=self.ctx.run_id,
                origin_case_id=self.ctx.case_id,
                origin_discovery_run_id=self.ctx.discovery_run_id,
                origin_investor_run_id=self.ctx.investor_run_id,
            )
            .on_conflict_do_nothing(index_elements=[ApiCache.cache_key])
        )

    def _same_owner(self, row: ApiCache) -> bool:
        kind, owner_id = self.ctx.owner
        origin = {
            "case": row.origin_case_id,
            "discovery_run": row.origin_discovery_run_id,
            "investor_run": row.origin_investor_run_id,
        }[kind]
        return origin == owner_id
