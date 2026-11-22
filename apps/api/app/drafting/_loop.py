"""Draft → validate → one retry with the validator's complaints → caller's fallback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.extraction.llm import DraftingLlm, LlmOutputError, run_draft


@dataclass
class DraftAttempts:
    text: str | None  # the first draft that passed, or None
    issues: list[list[str]] = field(default_factory=list)  # issues per rejected attempt
    calls: list[Any] = field(default_factory=list)


async def draft_until_valid(
    llm: DraftingLlm,
    system: str,
    user: str,
    validate: Callable[[str], list[str]],
    *,
    max_attempts: int = 2,
) -> DraftAttempts:
    result = DraftAttempts(text=None)
    prompt = user
    for _ in range(max_attempts):
        try:
            text, record = await run_draft(llm, system, prompt)
        except LlmOutputError as exc:
            result.issues.append([str(exc)])
            continue
        if record is not None:
            result.calls.append(record)
        issues = validate(text)
        if not issues:
            result.text = text.strip()
            return result
        result.issues.append(issues)
        listed = "\n".join(f"- {i}" for i in issues[:20])
        prompt = (
            f"{user}\n\nYour previous draft was rejected for these reasons:\n{listed}\n"
            "Write the whole draft again and fix every one of them."
        )
    return result
