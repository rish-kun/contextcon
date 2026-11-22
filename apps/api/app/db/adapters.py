"""Database-backed implementations of the hooks the API clients call.

`app/clients/` (built in parallel) takes two hooks:

- an async *recorder*, called before each external request with an attempt record and
  after it with usage (credits_used, input/output tokens, USD, and an `unknown` flag
  when the provider did not report cost);
- an async *cache* with `get(key)` / `set(key, value)`.

The exact client-side types were not merged when this was written, so both adapters
read attributes duck-typed (object attributes or mapping keys) and accept a few
calling styles; see `DbCallRecorder.__call__`. Each adapter writes in its own short
transaction, so an attempt row survives even if the step that made the call crashes.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import func

from app.db.enums import CallStatus
from app.db.ledger import CostContext, record_cost
from app.db.models import ApiCache, CallAttempt, CostEntry


def _read(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    for name in names:
        if isinstance(obj, Mapping):
            if name in obj and obj[name] is not None:
                return obj[name]
        else:
            value = getattr(obj, name, None)
            if value is not None:
                return value
    return default


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return {"value": str(value)}


class DbCallRecorder:
    """Persists a `call_attempts` row before each call and a `cost_entries` row after.

    Supported calling styles:
      `await recorder.before(attempt) -> attempt_id`, then `await recorder.after(attempt, usage)`
      `await recorder("before", attempt)` / `await recorder("after", attempt, usage)`
      `await recorder(attempt)` / `await recorder(attempt, usage)`
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], ctx: CostContext):
        self._sessionmaker = sessionmaker
        self.ctx = ctx
        self._open: dict[int, uuid.UUID] = {}

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        phase: str | None = None
        if args and isinstance(args[0], str) and args[0] in {"before", "after"}:
            phase, args = args[0], args[1:]
        attempt = kwargs.get("attempt", args[0] if args else None)
        usage = kwargs.get("usage", args[1] if len(args) > 1 else None)
        if phase == "after" or (phase is None and usage is not None):
            return await self.after(attempt, usage)
        return await self.before(attempt)

    async def before(self, attempt: Any) -> uuid.UUID:
        row = CallAttempt(
            workspace_id=self.ctx.workspace_id,
            case_id=self.ctx.case_id,
            discovery_run_id=self.ctx.discovery_run_id,
            investor_run_id=self.ctx.investor_run_id,
            run_id=self.ctx.run_id,
            step_id=self.ctx.step_id,
            provider=str(_read(attempt, "provider", default="unknown")),
            endpoint=str(_read(attempt, "endpoint", "path", "method", default="unknown")),
            request_hash=_read(attempt, "request_hash", "cache_key", "key"),
            request=_as_dict(_read(attempt, "request", "params", "body")),
            status=CallStatus.STARTED,
        )
        async with self._sessionmaker() as session:
            session.add(row)
            await session.commit()
        self._open[id(attempt)] = row.id
        return row.id

    async def after(self, attempt: Any, usage: Any) -> CostEntry:
        attempt_id = self._open.pop(id(attempt), None) or _read(
            attempt, "db_attempt_id", "attempt_id"
        )
        if attempt_id is None:
            attempt_id = await self.before(attempt)
            self._open.pop(id(attempt), None)
        error = _read(usage, "error")
        credits = _read(usage, "credits_used", "credits")
        usd = _read(usage, "usd", "cost_usd")
        unknown = bool(_read(usage, "unknown", default=False))
        async with self._sessionmaker() as session:
            await session.execute(
                update(CallAttempt)
                .where(CallAttempt.id == attempt_id)
                .values(
                    status=CallStatus.FAILED if error else CallStatus.SUCCEEDED,
                    status_code=_read(usage, "status_code"),
                    error=None if error is None else str(error),
                    finished_at=func.now(),
                )
            )
            provider, endpoint = (
                await session.execute(
                    select(CallAttempt.provider, CallAttempt.endpoint).where(
                        CallAttempt.id == attempt_id
                    )
                )
            ).one()
            entry = await record_cost(
                session,
                self.ctx,
                provider=provider,
                endpoint=endpoint,
                credits=credits,
                input_tokens=_read(usage, "input_tokens", default=0),
                output_tokens=_read(usage, "output_tokens", default=0),
                usd=usd,
                unknown=unknown,
                cached=bool(_read(usage, "cached", default=False)),
                call_attempt_id=attempt_id,
            )
            await session.commit()
        return entry


class DbCache:
    """`api_cache`-backed cache.

    Public data is shared across owners (a case reuses what discovery already paid
    for). A hit served to a different owner records a zero-cost ledger entry linked to
    the run that paid, so the reuse is visible without double counting.

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
        return f"pub:{key}"

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
            await session.commit()
            return row.response

    async def set(
        self, key: str, value: Any, *, provider: str | None = None, endpoint: str | None = None
    ) -> None:
        stmt = (
            insert(ApiCache)
            .values(
                id=uuid.uuid4(),
                cache_key=self.storage_key(key),
                provider=provider,
                endpoint=endpoint,
                response=value,
                confidential=self.confidential,
                workspace_id=self.ctx.workspace_id if self.confidential else None,
                case_id=self.ctx.case_id if self.confidential else None,
                delete_after=self.delete_after if self.confidential else None,
                origin_run_id=self.ctx.run_id,
                origin_case_id=self.ctx.case_id,
                origin_discovery_run_id=self.ctx.discovery_run_id,
                origin_investor_run_id=self.ctx.investor_run_id,
            )
            .on_conflict_do_nothing(index_elements=[ApiCache.cache_key])
        )
        async with self._sessionmaker() as session:
            await session.execute(stmt)
            await session.commit()

    def _same_owner(self, row: ApiCache) -> bool:
        kind, owner_id = self.ctx.owner
        origin = {
            "case": row.origin_case_id,
            "discovery_run": row.origin_discovery_run_id,
            "investor_run": row.origin_investor_run_id,
        }[kind]
        return origin == owner_id
