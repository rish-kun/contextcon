"""Shortlist text: why this company is on the shortlist, from criteria results only.

The criteria results come from the rules engine (pass / fail / unknown per
criterion). The model turns them into two to four sentences, each citing the
criterion ids it talks about, and the citation validator checks them. The
deterministic fallback lists the results directly.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.drafting._loop import draft_until_valid
from app.drafting.citations import check_citations, require_citations, valid_citation_id
from app.drafting.prompts import PROMPT_VERSION, SHORTLIST_WHY
from app.extraction.llm import DraftingLlm


class CriterionResult(BaseModel):
    id: str
    label: str
    kind: Literal["must", "preference"]
    result: Literal["pass", "fail", "unknown"]
    detail: str = ""  # rules-engine summary of the evidence, e.g. "HQ Pune, India"

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not valid_citation_id(v):
            raise ValueError(f"invalid criterion id {v!r}")
        return v


class ShortlistWhy(BaseModel):
    text: str
    citations_used: list[str] = Field(default_factory=list)
    used_fallback: bool = False
    rejected_attempts: list[list[str]] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


# Words that would turn an explanation into a judgement the rules did not make.
_JUDGEMENT = re.compile(
    r"\b(score|scored|rank(?:ed|ing)?|recommend\w*|invest(?:ment)? opportunity|returns?|"
    r"guarantee\w*|will (?:grow|succeed)|strong buy|best)\b",
    re.I,
)


def result_sources(company_name: str, results: list[CriterionResult]) -> dict[str, str]:
    return {r.id: f"{company_name} {r.label} {r.result} {r.detail}" for r in results}


def validate_why(text: str, company_name: str, results: list[CriterionResult]) -> list[str]:
    issues = check_citations(text, result_sources(company_name, results)).issues
    issues += [f'uses judgement word "{m}"' for m in sorted(set(_JUDGEMENT.findall(text)))]
    return issues


def fallback_why(results: list[CriterionResult]) -> str:
    met = [r for r in results if r.result == "pass"]
    unmet = [r for r in results if r.result == "fail"]
    unknown = [r for r in results if r.result == "unknown"]

    def ids(rs: list[CriterionResult]) -> str:
        return "".join(f"[{r.id}]" for r in rs)

    def labels(rs: list[CriterionResult]) -> str:
        return "; ".join(r.label for r in rs)

    out = []
    if met:
        out.append(f"Meets: {labels(met)} {ids(met)}.")
    if unmet:
        out.append(f"Does not meet: {labels(unmet)} {ids(unmet)}.")
    if unknown:
        out.append(f"Not yet known: {labels(unknown)} {ids(unknown)}.")
    return " ".join(out)


async def draft_shortlist_why(
    llm: DraftingLlm,
    company_name: str,
    results: list[CriterionResult],
    *,
    max_attempts: int = 2,
) -> ShortlistWhy:
    if not results:
        raise ValueError("no criteria results to explain")
    sources = result_sources(company_name, results)
    payload = {
        "company": company_name,
        "criteria_results": [r.model_dump() for r in results],
    }
    attempts = await draft_until_valid(
        llm,
        SHORTLIST_WHY.system,
        json.dumps(payload, ensure_ascii=False, indent=1),
        lambda text: validate_why(text, company_name, results),
        max_attempts=max_attempts,
    )
    used_fallback = attempts.text is None
    text = fallback_why(results) if used_fallback else attempts.text
    report = require_citations(text, sources)
    return ShortlistWhy(
        text=text,
        citations_used=report.citations_used,
        used_fallback=used_fallback,
        rejected_attempts=attempts.issues,
        calls=attempts.calls,
    )
