"""Shared plumbing for external API clients: call records, recorder hook, cache.

Every external call (Crustdata, Anthropic) produces a `CallRecord`. A client
reports it to an optional async `recorder` twice:

1. before the request, with ``status="started"`` (the attempt record), and
2. after it, with the final status (``succeeded`` / ``failed``) and the usage
   that is known (credits, tokens, USD).

A cache hit is reported once, with ``status="cache_hit"`` and zero usage.

Both reports carry the same ``call_id``, so a DB layer can upsert on it. If a
worker dies mid-call, the ``started`` row stays behind with unknown usage and can
be reconciled later (for Crustdata, via the account usage endpoints).

The DB-backed recorder and cache arrive in a later checkpoint; the in-memory
versions here are for tests and local runs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

Provider = Literal["crustdata", "anthropic"]
CallStatus = Literal["started", "succeeded", "failed", "cache_hit"]


def utcnow() -> datetime:
    return datetime.now(UTC)


def stable_hash(value: Any) -> str:
    """SHA-256 of a canonical JSON encoding (sorted keys, no whitespace)."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def make_cache_key(provider: str, endpoint: str, params: Any) -> str:
    return stable_hash({"provider": provider, "endpoint": endpoint, "params": params})


class CallRecord(BaseModel):
    """What one external call did and what it cost."""

    call_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    provider: Provider
    endpoint: str
    params_hash: str
    cache_key: str
    status: CallStatus = "started"
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    http_status: int | None = None
    # HTTP attempts made by this client (Anthropic retries happen inside the SDK
    # and are not visible here, so LLM records always show 1).
    attempts: int = 0
    provider_request_id: str | None = None
    from_cache: bool = False

    # Crustdata: credits from the X-Credits-Used header. None when not reported.
    credits_used: float | None = None
    # Anthropic: tokens and computed USD.
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cost_usd: float | None = None
    # False when the call may have been billed but its usage is not known
    # (no credits header, a timeout after the request was sent, an unpriced model).
    usage_known: bool = False

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
    """Process-local cache. Values are deep-copied in and out."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        value = self._data.get(key)
        return copy.deepcopy(value) if value is not None else None

    async def set(self, key: str, value: Any) -> None:
        self._data[key] = copy.deepcopy(value)

    def __len__(self) -> int:
        return len(self._data)


async def report(recorder: CallRecorder | None, record: CallRecord) -> None:
    if recorder is not None:
        await recorder(record.model_copy(deep=True))
