"""Shared plumbing for external API clients: call records, recorder hook, cache.

One logical external call (an *operation*) is a cache lookup followed by one or more
HTTP *dispatches* (the first try plus any retries). Every dispatch is its own
`CallRecord`, with its own ``call_id``, provider request id and usage, so a retry
never hides or overwrites what an earlier dispatch cost. A client reports each
dispatch to an optional async `recorder` twice:

1. before the request, with ``status="started"`` (the attempt record), and
2. after it, with the final status (``succeeded`` / ``failed``) and the usage that is
   known (credits, tokens, USD). ``usage_known=False`` means the dispatch may have
   been billed but the provider did not say how much.

A cache hit is reported once, with ``status="cache_hit"`` and zero usage. An attempt
left ``started`` by a crash is later reconciled to ``unknown``.

`CallOperation` drives that sequence for both clients. A recorder or cache may
implement optional hooks, which the operation uses when present:

- ``recorder.operation_key(cache_key)`` — a stable key for this call within its step,
  so a resumed step can find the attempt a crashed worker left behind;
- ``recorder.reconcile(operation_key)`` — settle such leftover ``started`` attempts;
- ``recorder.before_dispatch(record)`` — fence, reserve budget and persist ``started``
  (instead of a plain report);
- ``recorder.finish(record, cache=..., cache_value=...)`` — persist the final usage and
  the cache entry in one transaction;
- ``cache.lock(key)`` — an async context manager serialising misses on one key;
- ``cache.confidential()`` — a case-scoped, expiring view of the cache (see
  `confidential_cache`).

Plain callables (`InMemoryRecorder`) and plain caches (`InMemoryCache`) still work.

Errors: provider error text never reaches a `CallRecord`, an exception message or
the database. Records keep the HTTP status, the provider request id and an
allowlisted error code (`safe_error_code`).
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

Provider = Literal["crustdata", "anthropic"]
CallStatus = Literal["started", "succeeded", "failed", "cache_hit", "unknown"]

# Error codes that may be stored or shown. Anything else becomes "other".
ERROR_CODES: frozenset[str] = frozenset(
    {
        # Raised locally by the clients.
        "network_error",
        "timeout",
        "decode_error",
        "http_error",
        "interrupted",
        "refusal",
        "max_tokens",
        "no_output",
        "invalid_output",
        "invalid_response",
        "empty_reply",
        # Anthropic error types.
        "invalid_request_error",
        "authentication_error",
        "permission_error",
        "not_found_error",
        "request_too_large",
        "rate_limit_error",
        "api_error",
        "overloaded_error",
        "billing_error",
        "timeout_error",
        # Crustdata error types (and common generic ones).
        "invalid_request",
        "bad_request",
        "validation_error",
        "unauthorized",
        "forbidden",
        "not_found",
        "rate_limited",
        "insufficient_credits",
        "payment_required",
        "internal_error",
        "server_error",
        "service_unavailable",
    }
)


def safe_error_code(code: object) -> str | None:
    """`code` if it is an allowlisted error code, "other" for anything else."""
    if code is None:
        return None
    return code if isinstance(code, str) and code in ERROR_CODES else "other"


def utcnow() -> datetime:
    return datetime.now(UTC)


def stable_hash(value: Any) -> str:
    """SHA-256 of a canonical JSON encoding (sorted keys, no whitespace)."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def make_cache_key(provider: str, endpoint: str, params: Any) -> str:
    return stable_hash({"provider": provider, "endpoint": endpoint, "params": params})


class CallRecord(BaseModel):
    """What one HTTP dispatch (or one cache hit) did and what it cost."""

    call_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    provider: Provider
    endpoint: str
    params_hash: str
    cache_key: str
    status: CallStatus = "started"
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    http_status: int | None = None
    # 1-based number of this dispatch within its operation (0 for a cache hit).
    attempts: int = 0
    provider_request_id: str | None = None
    from_cache: bool = False
    # Stable key of the logical call within its step (set by a DB recorder), and this
    # dispatch's 0-based position among the operation's dispatches.
    operation_key: str | None = None
    dispatch_index: int = 0

    # Crustdata: credits from the X-Credits-Used header. None when not reported.
    credits_used: float | None = None
    # Upper-bound credits reserved against the budget before this dispatch.
    credits_estimate: float | None = None
    # Anthropic: tokens and computed USD.
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cost_usd: float | None = None
    # False when the dispatch may have been billed but its usage is not known
    # (no credits header, a timeout after the request was sent, an unpriced model).
    usage_known: bool = False

    # An allowlisted error code (`safe_error_code`), never provider text.
    error: str | None = None


class CallRecorder(Protocol):
    async def __call__(self, record: CallRecord) -> None: ...


class ResponseCache(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any) -> None: ...


class InMemoryRecorder:
    """Keeps a snapshot of every report, in order."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def __call__(self, record: CallRecord) -> None:
        self.records.append(record.model_copy(deep=True))

    def final(self) -> list[CallRecord]:
        """The last report for each call id (what a DB upsert would hold)."""
        latest: dict[str, CallRecord] = {}
        for record in self.records:
            latest[record.call_id] = record
        return list(latest.values())


class InMemoryCache:
    """Process-local cache. Values are deep-copied in and out.

    `confidential()` returns a separate namespace, standing in for the case-scoped
    cache a DB cache provides."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._confidential: InMemoryCache | None = None

    async def get(self, key: str) -> Any | None:
        value = self._data.get(key)
        return copy.deepcopy(value) if value is not None else None

    async def set(self, key: str, value: Any) -> None:
        self._data[key] = copy.deepcopy(value)

    def confidential(self) -> InMemoryCache:
        if self._confidential is None:
            self._confidential = InMemoryCache()
        return self._confidential

    def __len__(self) -> int:
        return len(self._data)


def confidential_cache(cache: Any) -> Any | None:
    """The case-scoped, expiring view of `cache` for requests carrying private text.

    None (no caching) when the cache cannot provide one: a confidential response must
    never land in a shared cache."""
    if cache is None:
        return None
    view = getattr(cache, "confidential", None)
    return view() if callable(view) else None


async def report(recorder: CallRecorder | None, record: CallRecord) -> None:
    if recorder is not None:
        await recorder(record.model_copy(deep=True))


class CallOperation:
    """One logical call: lock, reconcile, cache lookup, then dispatches.

    async with CallOperation(recorder, cache, provider=..., endpoint=...,
                             cache_key=key, params_hash=h) as op:
        cached = await op.lookup()
        if cached is not None:
            return cached, await op.cache_hit()
        record = op.new_record()
        await op.start(record)          # may raise (lease lost, budget exceeded)
        ...HTTP...
        await op.finish(record, cache_value=value)
    """

    def __init__(
        self,
        recorder: CallRecorder | None,
        cache: ResponseCache | None,
        *,
        provider: Provider,
        endpoint: str,
        cache_key: str,
        params_hash: str,
        model: str | None = None,
    ) -> None:
        self.recorder = recorder
        self.cache = cache
        self.provider = provider
        self.endpoint = endpoint
        self.cache_key = cache_key
        self.params_hash = params_hash
        self.model = model
        self.operation_key: str | None = None
        self._dispatches = 0
        self._lock: AbstractAsyncContextManager[Any] | None = None

    async def __aenter__(self) -> CallOperation:
        make_key = getattr(self.recorder, "operation_key", None)
        if callable(make_key):
            self.operation_key = make_key(self.cache_key)
        lock = getattr(self.cache, "lock", None)
        if callable(lock):
            self._lock = lock(self.cache_key)
            await self._lock.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._lock is not None:
            await self._lock.__aexit__(*exc)

    async def lookup(self) -> Any | None:
        """Settle attempts a crashed worker left for this operation, then return the
        cached value (None on a miss). Under the lock, so a concurrent miss on the same
        key waits here and then finds the value the first caller paid for."""
        reconcile = getattr(self.recorder, "reconcile", None)
        if callable(reconcile) and self.operation_key is not None:
            await reconcile(self.operation_key)
        if self.cache is None:
            return None
        return await self.cache.get(self.cache_key)

    def new_record(self, **fields: Any) -> CallRecord:
        record = CallRecord(
            provider=self.provider,
            endpoint=self.endpoint,
            params_hash=self.params_hash,
            cache_key=self.cache_key,
            model=self.model,
            operation_key=self.operation_key,
            dispatch_index=self._dispatches,
            attempts=self._dispatches + 1,
            **fields,
        )
        self._dispatches += 1
        return record

    async def cache_hit(self, **fields: Any) -> CallRecord:
        record = CallRecord(
            provider=self.provider,
            endpoint=self.endpoint,
            params_hash=self.params_hash,
            cache_key=self.cache_key,
            model=self.model,
            operation_key=self.operation_key,
            status="cache_hit",
            from_cache=True,
            finished_at=utcnow(),
            usage_known=True,
            **fields,
        )
        await report(self.recorder, record)
        return record

    async def start(self, record: CallRecord) -> None:
        """Persist the attempt before the request leaves."""
        before = getattr(self.recorder, "before_dispatch", None)
        if callable(before):
            await before(record.model_copy(deep=True))
        else:
            await report(self.recorder, record)

    async def finish(self, record: CallRecord, *, cache_value: Any | None = None) -> None:
        """Persist the dispatch's final usage, and its cache entry, together."""
        if record.finished_at is None:
            record.finished_at = utcnow()
        cache = self.cache if cache_value is not None else None
        finish = getattr(self.recorder, "finish", None)
        if callable(finish):
            await finish(record.model_copy(deep=True), cache=cache, cache_value=cache_value)
            return
        if cache is not None:
            await cache.set(self.cache_key, cache_value)
        await report(self.recorder, record)
