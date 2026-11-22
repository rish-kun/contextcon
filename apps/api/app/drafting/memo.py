"""Memo prose that restates accepted facts, every sentence cited.

The model drafts; `check_citations` rejects any uncited sentence, unknown id,
stray bracket or invented number. After one corrective retry, the section
falls back to a deterministic restatement of the facts, which always passes.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.drafting._loop import draft_until_valid
from app.drafting.citations import (
    check_citations,
    cite_each_sentence,
    require_citations,
    valid_citation_id,
)
from app.drafting.prompts import MEMO_SECTION, PROMPT_VERSION
from app.extraction.llm import DraftingLlm


class AcceptedFact(BaseModel):
    citation_id: str
    statement: str
    source_label: str | None = None
    as_of: str | None = None

    @field_validator("citation_id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not valid_citation_id(v):
            raise ValueError(f"invalid citation id {v!r}")
        return v


class MemoSectionRequest(BaseModel):
    section: str
    facts: list[AcceptedFact]
    guidance: str = ""


class MemoSection(BaseModel):
    section: str
    text: str
    citations_used: list[str] = Field(default_factory=list)
    used_fallback: bool = False
    rejected_attempts: list[list[str]] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


def fact_sources(facts: list[AcceptedFact]) -> dict[str, str]:
    """Citation id → the text a sentence citing it may restate."""
    out: dict[str, str] = {}
    for f in facts:
        extra = " ".join(x for x in (f.source_label, f.as_of) if x)
        out[f.citation_id] = f"{f.statement} {extra}".strip()
    return out


def fallback_section(facts: list[AcceptedFact]) -> str:
    return " ".join(cite_each_sentence(f.statement, f.citation_id) for f in facts)


def validate_memo_text(text: str, facts: list[AcceptedFact]) -> list[str]:
    return check_citations(text, fact_sources(facts)).issues


async def draft_memo_section(
    llm: DraftingLlm, request: MemoSectionRequest, *, max_attempts: int = 2
) -> MemoSection:
    if not request.facts:
        return MemoSection(section=request.section, text="")
    sources = fact_sources(request.facts)
    payload = [
        {
            "id": f.citation_id,
            "fact": f.statement,
            **({"source": f.source_label} if f.source_label else {}),
            **({"as_of": f.as_of} if f.as_of else {}),
        }
        for f in request.facts
    ]
    user = (
        f"Section: {request.section}\n"
        + (f"Guidance: {request.guidance}\n" if request.guidance else "")
        + f"Accepted facts:\n{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )
    attempts = await draft_until_valid(
        llm,
        MEMO_SECTION.system,
        user,
        lambda text: check_citations(text, sources).issues,
        max_attempts=max_attempts,
    )
    used_fallback = attempts.text is None
    text = fallback_section(request.facts) if used_fallback else attempts.text
    report = require_citations(text, sources)  # never returns uncited text
    return MemoSection(
        section=request.section,
        text=text,
        citations_used=report.citations_used,
        used_fallback=used_fallback,
        rejected_attempts=attempts.issues,
        calls=attempts.calls,
    )
