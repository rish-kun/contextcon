import pytest

from app.clients.base import (
    CallRecord,
    InMemoryCache,
    InMemoryRecorder,
    make_cache_key,
    stable_hash,
)

pytestmark = pytest.mark.anyio


def test_stable_hash_ignores_key_order() -> None:
    assert stable_hash({"a": 1, "b": [1, 2]}) == stable_hash({"b": [1, 2], "a": 1})
    assert stable_hash({"a": 1}) != stable_hash({"a": 2})


def test_cache_key_depends_on_provider_endpoint_and_params() -> None:
    base = make_cache_key("crustdata", "/company/identify", {"domains": ["a.com"]})
    assert base == make_cache_key("crustdata", "/company/identify", {"domains": ["a.com"]})
    assert base != make_cache_key("crustdata", "/company/enrich", {"domains": ["a.com"]})
    assert base != make_cache_key("anthropic", "/company/identify", {"domains": ["a.com"]})
    assert base != make_cache_key("crustdata", "/company/identify", {"domains": ["b.com"]})


async def test_in_memory_cache_returns_copies() -> None:
    cache = InMemoryCache()
    value = {"body": {"n": 1}}
    await cache.set("k", value)
    value["body"]["n"] = 2
    got = await cache.get("k")
    assert got == {"body": {"n": 1}}
    got["body"]["n"] = 3
    assert await cache.get("k") == {"body": {"n": 1}}
    assert await cache.get("missing") is None


async def test_in_memory_recorder_keeps_snapshots_and_final_state() -> None:
    recorder = InMemoryRecorder()
    record = CallRecord(provider="crustdata", endpoint="/x", params_hash="h", cache_key="k")
    await recorder(record)
    record.status = "succeeded"
    await recorder(record)
    assert [r.status for r in recorder.records] == ["started", "succeeded"]
    assert [r.status for r in recorder.final()] == ["succeeded"]
