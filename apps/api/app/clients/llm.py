"""The single Anthropic client. Every LLM call in DealProof goes through here.

Uses the official ``anthropic`` SDK against the Messages API directly with
``ANTHROPIC_API_KEY`` (not Vertex, not Bedrock). Model, max tokens and effort come
from settings. No sampling parameters (``temperature``, ``top_p``, ``top_k``) are ever
sent: the default model rejects them, and there is no code path that adds them.

Each HTTP dispatch is recorded on its own (`app.clients.base`). The SDK's internal
retries are disabled (``max_retries=0``) and this client retries 429 / 5xx / 529 and
connection failures itself, so every dispatch, retried or not, has its own attempt
record, request id and usage. Cost is computed from the model the API says it ran
(``response.model``), through an explicit alias table; a model with no price is
recorded as unknown cost, never as zero.

Caching: prompts usually carry confidential case text, so calls use the case-scoped,
expiring cache by default (`confidential_cache`), and skip caching when there is
none. Shared (workspace) caching is opt-in with ``public=True``, for requests built
only from public data.

The LLM only extracts and drafts; rules decide. Structured extraction uses the
SDK's structured outputs (``messages.parse`` with a Pydantic model), so the reply
is schema-valid JSON.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError

from app.clients.base import (
    CallOperation,
    CallRecord,
    CallRecorder,
    ResponseCache,
    confidential_cache,
    make_cache_key,
    safe_error_code,
    stable_hash,
)
from app.settings import Settings, get_settings

PROVIDER = "anthropic"
ENDPOINT = "/v1/messages"
DEFAULT_BASE_URL = "https://api.anthropic.com"

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

# Model names the API may return mapped to the priced name. Only exact, known
# aliases belong here (add dated snapshot ids once the API is seen returning them,
# or set ANTHROPIC_MODEL_ALIASES); anything unmatched is recorded as unknown cost.
DEFAULT_MODEL_ALIASES: dict[str, str] = {}

# Statuses Anthropic does not bill and that are worth another try.
RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


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


class _Rejected(Exception):
    """A 200 reply that cannot be used: (error code, error class)."""

    def __init__(self, code: str, error_class: type[LLMError] = LLMError) -> None:
        super().__init__(code)
        self.code = code
        self.error_class = error_class


def _message(record: CallRecord) -> str:
    parts = ["anthropic"]
    if record.http_status:
        parts.append(f"HTTP {record.http_status}")
    if record.error:
        parts.append(record.error)
    if record.provider_request_id:
        parts.append(f"request_id={record.provider_request_id}")
    return " ".join(parts)


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "claude-haiku-5-5",
        max_tokens: int = 4096,
        effort: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        backoff_max: float = 8.0,
        prices: dict[str, ModelPrice] | None = None,
        model_aliases: dict[str, str] | None = None,
        recorder: CallRecorder | None = None,
        cache: ResponseCache | None = None,
        client: AsyncAnthropic | None = None,
        http_client: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("Anthropic API key is empty; set ANTHROPIC_API_KEY.")
            # Everything explicit: the SDK would otherwise read ANTHROPIC_BASE_URL and
            # ANTHROPIC_AUTH_TOKEN from the environment (agent shells set both, for a
            # local proxy), sending app calls to the wrong endpoint with the wrong
            # credential.
            options: dict[str, Any] = {}
            if http_client is not None:
                options["http_client"] = http_client
            client = AsyncAnthropic(
                api_key=api_key,
                auth_token=None,
                base_url=base_url,
                timeout=timeout,
                max_retries=0,
                **options,
            )
            client.auth_token = None
        # Retries happen here, one recorded dispatch each, never inside the SDK.
        with_options = getattr(client, "with_options", None)
        self._client = with_options(max_retries=0) if callable(with_options) else client
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.prices = {**DEFAULT_PRICES, **(prices or {})}
        self.model_aliases = {**DEFAULT_MODEL_ALIASES, **(model_aliases or {})}
        self.recorder = recorder
        self.cache = cache
        self._sleep = sleep

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kwargs: Any) -> LLMClient:
        s = settings or get_settings()
        overrides = {name: ModelPrice(**values) for name, values in s.anthropic_prices.items()}
        options: dict[str, Any] = {
            "api_key": s.anthropic_api_key.get_secret_value(),
            "base_url": s.anthropic_base_url_override,
            "model": s.anthropic_model,
            "max_tokens": s.anthropic_max_tokens,
            "effort": s.anthropic_effort,
            "timeout": s.anthropic_timeout_seconds,
            "max_retries": s.anthropic_max_retries,
            "prices": overrides,
            "model_aliases": s.anthropic_model_aliases,
        }
        return cls(**{**options, **kwargs})

    async def aclose(self) -> None:
        await self._client.close()

    def price_for(self, model: str | None) -> ModelPrice | None:
        """The price of the model the API ran: exact name, then a known alias."""
        if not model:
            return None
        if model in self.prices:
            return self.prices[model]
        alias = self.model_aliases.get(model)
        return self.prices.get(alias) if alias else None

    async def extract_structured(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int | None = None,
        use_cache: bool = True,
        public: bool = False,
    ) -> tuple[T, CallRecord]:
        """Extract a `schema` instance from `user` text, following `system`.

        ``public=True`` allows the shared workspace cache; only for prompts built from
        public data. Otherwise the reply is cached per case, with an expiry, or not
        at all."""
        params = self._params(system, user, max_tokens)
        key_params = {**params, "schema": schema.model_json_schema()}

        def use(response: Any) -> dict[str, Any]:
            parsed = response.parsed_output
            if parsed is None:
                raise _Rejected("no_output")
            try:
                instance = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
            except ValidationError:
                raise _Rejected("invalid_output") from None
            return {"output": instance.model_dump(mode="json")}

        payload, record = await self._call(
            "messages.parse",
            key_params,
            lambda: self._client.messages.parse(output_format=schema, **params),
            use,
            use_cache=use_cache,
            public=public,
        )
        return schema.model_validate(payload["output"]), record

    async def draft_text(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        use_cache: bool = True,
        public: bool = False,
    ) -> tuple[str, CallRecord]:
        """Free-text drafting (memo prose, seller email)."""
        params = self._params(system, user, max_tokens)

        def use(response: Any) -> dict[str, Any]:
            text = "".join(block.text for block in response.content if block.type == "text")
            if not text.strip():
                raise _Rejected("empty_reply")
            return {"output": text}

        payload, record = await self._call(
            "messages.create",
            params,
            lambda: self._client.messages.create(**params),
            use,
            use_cache=use_cache,
            public=public,
        )
        return payload["output"], record

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
        return params

    def _retry_delay(self, attempt: int) -> float:
        delay = self.backoff_base * (2**attempt)
        return min(delay + random.uniform(0, self.backoff_base), self.backoff_max)

    async def _call(
        self,
        endpoint_kind: str,
        key_params: dict[str, Any],
        send: Callable[[], Awaitable[Any]],
        use: Callable[[Any], dict[str, Any]],
        *,
        use_cache: bool,
        public: bool,
    ) -> tuple[dict[str, Any], CallRecord]:
        cache: Any = None
        if use_cache:
            cache = self.cache if public else confidential_cache(self.cache)
        async with CallOperation(
            self.recorder,
            cache,
            provider=PROVIDER,
            endpoint=ENDPOINT,
            cache_key=make_cache_key(PROVIDER, f"{ENDPOINT}#{endpoint_kind}", key_params),
            params_hash=stable_hash(key_params),
            model=self.model,
        ) as op:
            cached = await op.lookup()
            if cached is not None:
                record = await op.cache_hit(
                    provider_request_id=cached.get("provider_request_id"),
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                )
                if cached.get("model"):
                    record.model = cached["model"]
                return cached, record

            attempt = 0
            while True:
                record = op.new_record()
                await op.start(record)
                try:
                    response = await send()
                except anthropic.APIStatusError as exc:
                    # Error responses are not billed.
                    record.status = "failed"
                    record.http_status = exc.status_code
                    record.provider_request_id = exc.request_id
                    record.input_tokens = record.output_tokens = 0
                    record.cost_usd = 0.0
                    record.usage_known = True
                    record.error = _status_error_code(exc)
                    await op.finish(record)
                    if exc.status_code in RETRYABLE_STATUSES and attempt < self.max_retries:
                        await self._sleep(self._retry_delay(attempt))
                        attempt += 1
                        continue
                    raise LLMError(_message(record), record=record) from None
                except anthropic.APIConnectionError as exc:
                    # The request may have been processed: cost unknown.
                    timed_out = isinstance(exc, anthropic.APITimeoutError)
                    record.status = "failed"
                    record.usage_known = False
                    record.error = "timeout" if timed_out else "network_error"
                    await op.finish(record)
                    # A timeout already waited the full budget; a dropped connection
                    # is worth one more try (recorded as its own dispatch).
                    if not timed_out and attempt < self.max_retries:
                        await self._sleep(self._retry_delay(attempt))
                        attempt += 1
                        continue
                    raise LLMError(_message(record), record=record) from None
                except Exception:
                    # A reply that could not be decoded: it may have been billed.
                    record.status = "failed"
                    record.usage_known = False
                    record.error = "decode_error"
                    await op.finish(record)
                    raise LLMError(_message(record), record=record) from None

                self._apply_usage(record, response)
                try:
                    if response.stop_reason == "refusal":
                        raise _Rejected("refusal", LLMRefusal)
                    if response.stop_reason == "max_tokens":
                        raise _Rejected("max_tokens", LLMTruncated)
                    payload = use(response)
                except _Rejected as rejected:
                    record.status = "failed"
                    record.error = rejected.code
                    await op.finish(record)
                    raise rejected.error_class(_message(record), record=record) from None

                record.status = "succeeded"
                await op.finish(
                    record,
                    cache_value={
                        **payload,
                        "provider_request_id": record.provider_request_id,
                        "model": record.model,
                    },
                )
                return payload, record

    def _apply_usage(self, record: CallRecord, response: Any) -> None:
        record.http_status = 200
        record.provider_request_id = getattr(response, "_request_id", None)
        record.model = getattr(response, "model", None) or None
        usage = response.usage
        record.input_tokens = usage.input_tokens
        record.output_tokens = usage.output_tokens
        record.cache_creation_input_tokens = usage.cache_creation_input_tokens or 0
        record.cache_read_input_tokens = usage.cache_read_input_tokens or 0
        price = self.price_for(record.model)
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


def _status_error_code(exc: anthropic.APIStatusError) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return safe_error_code(error.get("type")) or "http_error"
    return "http_error"
