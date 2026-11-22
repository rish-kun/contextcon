"""The single Anthropic client. Every LLM call in DealProof goes through here.

Uses the official ``anthropic`` SDK against the Messages API directly with
``ANTHROPIC_API_KEY`` (not Vertex, not Bedrock). Model, max tokens, effort and
temperature come from settings. Each call returns a `CallRecord` with tokens and
the USD cost computed from a configurable per-model price table.

The LLM only extracts and drafts; rules decide. Structured extraction uses the
SDK's structured outputs (``messages.parse`` with a Pydantic model), so the reply
is schema-valid JSON.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn, TypeVar

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError

from app.clients.base import (
    CallRecord,
    CallRecorder,
    ResponseCache,
    make_cache_key,
    report,
    stable_hash,
    utcnow,
)
from app.settings import Settings, get_settings

PROVIDER = "anthropic"
ENDPOINT = "/v1/messages"

T = TypeVar("T", bound=BaseModel)


class ModelPrice(BaseModel):
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float
    # Some models charge more once the prompt passes a size threshold.
    long_context_threshold: int | None = None
    long_input_per_mtok: float | None = None
    long_output_per_mtok: float | None = None
    # Multipliers on the input price for prompt-cache writes (5-minute TTL) and reads.
    cache_write_multiplier: float = Field(default=1.25)
    cache_read_multiplier: float = Field(default=0.1)


# First-party API list prices (USD / MTok), as of 2026-11.
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-haiku-5-5": ModelPrice(
        input_per_mtok=0.10,
        output_per_mtok=0.50,
        long_context_threshold=100_000,
        long_input_per_mtok=0.50,
        long_output_per_mtok=2.50,
    ),
    "claude-sonnet-5-5": ModelPrice(input_per_mtok=2.00, output_per_mtok=10.00),
    "claude-opus-5-5": ModelPrice(input_per_mtok=4.00, output_per_mtok=20.00),
}


def compute_cost_usd(
    price: ModelPrice,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    prompt_tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    input_rate = price.input_per_mtok
    output_rate = price.output_per_mtok
    if price.long_context_threshold is not None and prompt_tokens > price.long_context_threshold:
        input_rate = price.long_input_per_mtok or input_rate
        output_rate = price.long_output_per_mtok or output_rate
    total = (
        input_tokens * input_rate
        + cache_creation_input_tokens * input_rate * price.cache_write_multiplier
        + cache_read_input_tokens * input_rate * price.cache_read_multiplier
        + output_tokens * output_rate
    )
    return round(total / 1_000_000, 8)


class LLMError(Exception):
    def __init__(self, message: str, *, record: CallRecord) -> None:
        super().__init__(message)
        self.record = record


class LLMRefusal(LLMError):
    """The model declined the request (stop_reason "refusal")."""


class LLMTruncated(LLMError):
    """The reply hit max_tokens before finishing."""


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-haiku-5-5",
        max_tokens: int = 4096,
        temperature: float | None = None,
        effort: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        prices: dict[str, ModelPrice] | None = None,
        recorder: CallRecorder | None = None,
        cache: ResponseCache | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("Anthropic API key is empty; set ANTHROPIC_API_KEY.")
            client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)
        self._client = client
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.effort = effort
        self.prices = {**DEFAULT_PRICES, **(prices or {})}
        self.recorder = recorder
        self.cache = cache

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kwargs: Any) -> LLMClient:
        s = settings or get_settings()
        overrides = {name: ModelPrice(**values) for name, values in s.anthropic_prices.items()}
        options: dict[str, Any] = {
            "api_key": s.anthropic_api_key.get_secret_value(),
            "model": s.anthropic_model,
            "max_tokens": s.anthropic_max_tokens,
            "temperature": s.anthropic_temperature,
            "effort": s.anthropic_effort,
            "timeout": s.anthropic_timeout_seconds,
            "max_retries": s.anthropic_max_retries,
            "prices": overrides,
        }
        return cls(**{**options, **kwargs})

    async def aclose(self) -> None:
        await self._client.close()

    async def extract_structured(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int | None = None,
        use_cache: bool = True,
    ) -> tuple[T, CallRecord]:
        """Extract a `schema` instance from `user` text, following `system`."""
        params = self._params(system, user, max_tokens)
        key_params = {**params, "schema": schema.model_json_schema()}
        record, cached = await self._begin("messages.parse", key_params, use_cache)
        if cached is not None:
            return schema.model_validate(cached["output"]), record

        try:
            response = await self._client.messages.parse(output_format=schema, **params)
        except anthropic.APIError as exc:
            await self._fail_from_exception(record, exc)

        self._apply_usage(record, response)
        await self._check_stop_reason(record, response)
        parsed = response.parsed_output
        if parsed is None:
            await self._fail(record, f"no structured output (stop_reason={response.stop_reason})")
        try:
            instance = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
        except ValidationError as exc:
            await self._fail(record, f"output failed validation: {exc.error_count()} errors")

        await self._succeed(record, {"output": instance.model_dump(mode="json")}, use_cache)
        return instance, record

    async def draft_text(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        use_cache: bool = True,
    ) -> tuple[str, CallRecord]:
        """Free-text drafting (memo prose, seller email)."""
        params = self._params(system, user, max_tokens)
        record, cached = await self._begin("messages.create", params, use_cache)
        if cached is not None:
            return cached["output"], record

        try:
            response = await self._client.messages.create(**params)
        except anthropic.APIError as exc:
            await self._fail_from_exception(record, exc)

        self._apply_usage(record, response)
        await self._check_stop_reason(record, response)
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            await self._fail(record, f"empty reply (stop_reason={response.stop_reason})")

        await self._succeed(record, {"output": text}, use_cache)
        return text, record

    # --- Internals ---------------------------------------------------------------

    def _params(self, system: str, user: str, max_tokens: int | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        if self.temperature is not None:
            # Not a typed SDK parameter on this API version; sent only when configured.
            params["extra_body"] = {"temperature": self.temperature}
        return params

    async def _begin(
        self, endpoint_kind: str, params: dict[str, Any], use_cache: bool
    ) -> tuple[CallRecord, dict[str, Any] | None]:
        key = make_cache_key(PROVIDER, f"{ENDPOINT}#{endpoint_kind}", params)
        record = CallRecord(
            provider=PROVIDER,
            endpoint=ENDPOINT,
            params_hash=stable_hash(params),
            cache_key=key,
            model=self.model,
        )
        if use_cache and self.cache is not None:
            cached = await self.cache.get(key)
            if cached is not None:
                record.status = "cache_hit"
                record.from_cache = True
                record.finished_at = utcnow()
                record.provider_request_id = cached.get("provider_request_id")
                record.input_tokens = 0
                record.output_tokens = 0
                record.cost_usd = 0.0
                record.usage_known = True
                await report(self.recorder, record)
                return record, cached
        record.attempts = 1
        await report(self.recorder, record)
        return record, None

    def _apply_usage(self, record: CallRecord, response: Any) -> None:
        record.http_status = 200
        record.provider_request_id = getattr(response, "_request_id", None)
        record.model = getattr(response, "model", None) or self.model
        usage = response.usage
        record.input_tokens = usage.input_tokens
        record.output_tokens = usage.output_tokens
        record.cache_creation_input_tokens = usage.cache_creation_input_tokens or 0
        record.cache_read_input_tokens = usage.cache_read_input_tokens or 0
        price = self.prices.get(self.model)
        if price is None:
            record.cost_usd = None
            record.usage_known = False
            return
        record.cost_usd = compute_cost_usd(
            price,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cache_creation_input_tokens=record.cache_creation_input_tokens,
            cache_read_input_tokens=record.cache_read_input_tokens,
        )
        record.usage_known = True

    async def _succeed(self, record: CallRecord, payload: dict[str, Any], use_cache: bool) -> None:
        record.status = "succeeded"
        record.finished_at = utcnow()
        if use_cache and self.cache is not None:
            await self.cache.set(
                record.cache_key, {**payload, "provider_request_id": record.provider_request_id}
            )
        await report(self.recorder, record)

    async def _check_stop_reason(self, record: CallRecord, response: Any) -> None:
        if response.stop_reason == "refusal":
            await self._fail(record, "model refused the request", LLMRefusal)
        if response.stop_reason == "max_tokens":
            await self._fail(record, "reply hit max_tokens before finishing", LLMTruncated)

    async def _fail(
        self, record: CallRecord, message: str, error_class: type[LLMError] = LLMError
    ) -> NoReturn:
        record.status = "failed"
        record.finished_at = utcnow()
        record.error = message
        await report(self.recorder, record)
        raise error_class(message, record=record)

    async def _fail_from_exception(self, record: CallRecord, exc: anthropic.APIError) -> NoReturn:
        if isinstance(exc, anthropic.APIStatusError):
            record.http_status = exc.status_code
            record.provider_request_id = exc.request_id
            # Error responses are not billed.
            record.input_tokens = record.output_tokens = 0
            record.cost_usd = 0.0
            record.usage_known = True
            message = f"HTTP {exc.status_code}: {_short(exc)}"
        else:
            # Timeout or connection error: the request may have been processed.
            record.usage_known = False
            message = f"{type(exc).__name__}: {_short(exc)}"
        record.status = "failed"
        record.finished_at = utcnow()
        record.error = message
        await report(self.recorder, record)
        raise LLMError(message, record=record) from exc


def _short(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and "message" in error:
            return str(error["message"])[:300]
        return json.dumps(body)[:300]
    return str(exc)[:300]
