import json

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.clients.base import InMemoryCache, InMemoryRecorder
from app.clients.llm import (
    DEFAULT_PRICES,
    LLMClient,
    LLMError,
    LLMRefusal,
    LLMTruncated,
    ModelPrice,
    compute_cost_usd,
)
from app.settings import Settings

pytestmark = pytest.mark.anyio


class Founding(BaseModel):
    founded_year: int | None
    city: str | None


def message(
    content: list[dict],
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 1000,
    output_tokens: int = 200,
    model: str = "claude-haiku-5-5",
) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


class Harness:
    def __init__(self, responses: list[httpx2.Response], *, cache: bool = False, **kw) -> None:
        self.requests: list[httpx2.Request] = []
        queue = list(responses)

        def handler(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return queue.pop(0)

        sdk = AsyncAnthropic(
            api_key="test-key",
            base_url="https://anthropic.test",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        self.recorder = InMemoryRecorder()
        self.cache = InMemoryCache() if cache else None
        self.client = LLMClient(
            client=sdk, effort="low", recorder=self.recorder, cache=self.cache, **kw
        )

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


def ok(payload: dict) -> httpx2.Response:
    return httpx2.Response(200, json=payload, headers={"request-id": "req_abc"})


FOUNDING_JSON = json.dumps({"founded_year": 2014, "city": "Pune"})


async def test_extract_structured_parses_and_records_usage() -> None:
    h = Harness(
        [
            ok(
                message(
                    [
                        {"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": FOUNDING_JSON},
                    ]
                )
            )
        ]
    )
    result, record = await h.client.extract_structured(
        "Extract facts.", "Incorporated in 2014, based in Pune.", Founding
    )
    assert result == Founding(founded_year=2014, city="Pune")

    request = h.requests[0]
    assert request.url.path == "/v1/messages"
    # SDK 2.x sends the API key as a bearer token.
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["anthropic-version"]
    body = h.body()
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 4096
    assert body["system"] == "Extract facts."
    assert body["messages"] == [{"role": "user", "content": "Incorporated in 2014, based in Pune."}]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert set(body["output_config"]["format"]["schema"]["properties"]) == {"founded_year", "city"}
    assert "temperature" not in body

    assert record.status == "succeeded"
    assert record.provider == "anthropic"
    assert record.model == "claude-haiku-5-5"
    assert record.input_tokens == 1000
    assert record.output_tokens == 200
    # 1000 * $0.10/M + 200 * $0.50/M
    assert record.cost_usd == pytest.approx(0.0002)
    assert record.usage_known is True
    assert record.provider_request_id == "req_abc"
    assert [r.status for r in h.recorder.records] == ["started", "succeeded"]


async def test_extract_structured_cache_hit_skips_network() -> None:
    h = Harness([ok(message([{"type": "text", "text": FOUNDING_JSON}]))], cache=True)
    first, _ = await h.client.extract_structured("s", "u", Founding)
    second, record = await h.client.extract_structured("s", "u", Founding)
    assert len(h.requests) == 1
    assert second == first
    assert record.status == "cache_hit"
    assert record.cost_usd == 0
    assert record.provider_request_id == "req_abc"


async def test_extract_structured_refusal_raises_with_billed_usage() -> None:
    h = Harness([ok(message([], stop_reason="refusal", input_tokens=50, output_tokens=0))])
    with pytest.raises(LLMRefusal) as info:
        await h.client.extract_structured("s", "u", Founding)
    record = info.value.record
    assert record.status == "failed"
    assert record.input_tokens == 50
    assert record.cost_usd == pytest.approx(50 * 0.10 / 1_000_000)
    assert h.recorder.final()[0].status == "failed"


async def test_api_error_is_recorded() -> None:
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}
    h = Harness([httpx2.Response(400, json=error, headers={"request-id": "req_err"})])
    with pytest.raises(LLMError) as info:
        await h.client.draft_text("s", "u")
    record = info.value.record
    assert record.http_status == 400
    assert record.provider_request_id == "req_err"
    assert record.cost_usd == 0
    assert "bad" in record.error


async def test_draft_text_joins_text_blocks_and_sends_temperature_when_set() -> None:
    h = Harness(
        [ok(message([{"type": "text", "text": "Dear "}, {"type": "text", "text": "seller"}]))],
        temperature=0.0,
    )
    text, record = await h.client.draft_text("Write politely.", "Request documents.")
    assert text == "Dear seller"
    assert h.body()["temperature"] == 0.0
    assert "format" not in h.body()["output_config"]
    assert record.status == "succeeded"


async def test_unpriced_model_marks_cost_unknown() -> None:
    h = Harness([ok(message([{"type": "text", "text": "hi"}]))], model="claude-new-model")
    _, record = await h.client.draft_text("s", "u")
    assert record.cost_usd is None
    assert record.usage_known is False


def test_cost_uses_long_context_tier_and_cache_multipliers() -> None:
    haiku = DEFAULT_PRICES["claude-haiku-5-5"]
    short = compute_cost_usd(haiku, input_tokens=100_000, output_tokens=100_000)
    assert short == pytest.approx(100_000 * 0.10 / 1e6 + 100_000 * 0.50 / 1e6)
    long = compute_cost_usd(haiku, input_tokens=200_000, output_tokens=10_000)
    assert long == pytest.approx(200_000 * 0.50 / 1e6 + 10_000 * 2.50 / 1e6)
    cached = compute_cost_usd(
        ModelPrice(input_per_mtok=1.0, output_per_mtok=1.0),
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    assert cached == pytest.approx(1.25 + 0.1)


def test_from_settings_applies_model_and_price_overrides() -> None:
    settings = Settings(
        _env_file=None,
        anthropic_api_key="k",
        anthropic_model="claude-sonnet-5-5",
        anthropic_max_tokens=1000,
        anthropic_effort="medium",
        anthropic_prices={"claude-sonnet-5-5": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}},
    )
    client = LLMClient.from_settings(settings)
    assert client.model == "claude-sonnet-5-5"
    assert client.max_tokens == 1000
    assert client.effort == "medium"
    assert client.temperature is None
    assert client.prices["claude-sonnet-5-5"].output_per_mtok == 2.0
    assert client.prices["claude-haiku-5-5"] == DEFAULT_PRICES["claude-haiku-5-5"]


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        LLMClient(api_key="")


def test_from_settings_lets_kwargs_override_settings() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="k")
    assert LLMClient.from_settings(settings, model="claude-opus-5-5").model == "claude-opus-5-5"


async def test_truncated_reply_raises() -> None:
    h = Harness([ok(message([{"type": "text", "text": "Dear sel"}], stop_reason="max_tokens"))])
    with pytest.raises(LLMTruncated) as info:
        await h.client.draft_text("s", "u")
    assert isinstance(info.value, LLMError)
    assert info.value.record.output_tokens == 200


async def test_no_sampling_params_sent_by_default() -> None:
    h = Harness([ok(message([{"type": "text", "text": "hi"}]))])
    await h.client.draft_text("s", "u")
    body = h.body()
    for key in ("temperature", "top_p", "top_k"):
        assert key not in body
