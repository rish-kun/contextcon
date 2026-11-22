"""The narrow LLM surface that extraction and drafting depend on.

The real client is `app.clients.llm.LLMClient` (async), whose
`extract_structured(system, user, schema) -> (instance, CallRecord)` and
`draft_text(system, user) -> (text, CallRecord)` satisfy the Protocols below.
Coding against the Protocols keeps these modules testable with a scripted
double, sync or async.

No sampling parameters are sent from here. Claude Haiku 5.5 rejects a
non-default `temperature` with a 400. Repeatability comes from the client's
request-hash cache and from the rules engine making every decision. The
verbatim-span checks in this package are what keep the model's output honest.
"""

from __future__ import annotations

import inspect
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class StructuredLlm(Protocol):
    """Returns `(instance, call_record)`. May be sync or async."""

    def extract_structured(self, system: str, user: str, schema: type[Any]) -> Any: ...


@runtime_checkable
class DraftingLlm(Protocol):
    """Returns `(text, call_record)`. May be sync or async."""

    def draft_text(self, system: str, user: str) -> Any: ...


class LlmOutputError(RuntimeError):
    """The model's output could not be used (wrong type or unparseable)."""


def _split_record(result: Any) -> tuple[Any, Any]:
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], result[1]
    return result, None


async def run_structured[T: BaseModel](
    llm: StructuredLlm, system: str, user: str, schema: type[T]
) -> tuple[T, Any]:
    """Call `extract_structured` and return a validated `schema` instance plus its record."""
    result = llm.extract_structured(system, user, schema)
    if inspect.isawaitable(result):
        result = await result
    instance, record = _split_record(result)
    if isinstance(instance, schema):
        return instance, record
    try:
        if isinstance(instance, str | bytes):
            return schema.model_validate_json(instance), record
        if isinstance(instance, BaseModel):
            return schema.model_validate(instance.model_dump()), record
        return schema.model_validate(instance), record
    except Exception as exc:  # pydantic.ValidationError and friends
        raise LlmOutputError(f"output did not match {schema.__name__}: {exc}") from exc


async def run_draft(llm: DraftingLlm, system: str, user: str) -> tuple[str, Any]:
    """Call `draft_text` and return the text plus its record."""
    result = llm.draft_text(system, user)
    if inspect.isawaitable(result):
        result = await result
    text, record = _split_record(result)
    if not isinstance(text, str):
        raise LlmOutputError(f"draft_text returned {type(text).__name__}, expected str")
    return text, record
