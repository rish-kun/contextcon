"""A scripted stand-in for `app/clients/llm.py`. No network."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Call:
    kind: str
    system: str
    user: str
    schema: Any = None


@dataclass
class FakeLlm:
    """Returns queued outputs in order. Structured outputs may be dicts, models or JSON."""

    structured: list[Any] = field(default_factory=list)
    drafts: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    is_async: bool = True

    def _respond(self, value: Any) -> Any:
        record = {"n": len(self.calls)}
        if not self.is_async:
            return value, record

        async def _coro() -> Any:
            return value, record

        return _coro()

    def extract_structured(self, system: str, user: str, schema: type[Any]) -> Any:
        self.calls.append(Call("extract", system, user, schema))
        if not self.structured:
            raise AssertionError("FakeLlm: no structured output queued")
        return self._respond(self.structured.pop(0))

    def draft_text(self, system: str, user: str) -> Any:
        self.calls.append(Call("draft", system, user))
        if not self.drafts:
            raise AssertionError("FakeLlm: no draft queued")
        return self._respond(self.drafts.pop(0))
