"""Evidence text → structured facts for one claim.

The model reports what a piece of evidence says about a claim. Code keeps a
fact only when its `span` is found verbatim in the evidence, keeps the entity
name only when that name is written in the evidence, and keeps the effective
date only when its source span is in the evidence and it parses as an ISO date.
The model never says whether the claim is true; the rules engine does that.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.extraction.claims import ClaimCategory
from app.extraction.criteria import DroppedItem
from app.extraction.llm import StructuredLlm, run_structured
from app.extraction.prompts import FACTS, PROMPT_VERSION
from app.extraction.spans import normalize, span_in

_ISO_DATE = re.compile(r"^\d{4}(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?$")
_YEAR = re.compile(r"^(19|20)\d{2}$")


class ClaimRef(BaseModel):
    """The claim the evidence is being read for."""

    id: str | None = None
    text: str
    category: ClaimCategory
    components: dict[str, str] = Field(default_factory=dict)


class FactDraft(BaseModel):
    name: str
    value: str
    span: str


class EvidenceFactsDraft(BaseModel):
    speaks_to_claim: bool
    entity_name: str | None = None
    effective_date: str | None = None
    effective_date_span: str | None = None
    facts: list[FactDraft] = Field(default_factory=list)


class Fact(BaseModel):
    name: str
    value: str
    span: str


class EvidenceFacts(BaseModel):
    claim_id: str | None = None
    # True only when the model said the evidence speaks to the claim AND at
    # least one fact survived span verification. Otherwise the evidence is
    # treated as silent.
    speaks_to_claim: bool
    entity_name: str | None = None
    effective_date: str | None = None
    effective_date_span: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    dropped: list[DroppedItem] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


def _value_consistent(fact: FactDraft) -> bool:
    """A four-digit year must appear in its own span; other values are trusted to the span."""
    value = fact.value.strip()
    if _YEAR.match(value):
        return value in fact.span
    return bool(value)


def finalize_facts(draft: EvidenceFactsDraft, evidence: str) -> EvidenceFacts:
    facts: list[Fact] = []
    dropped: list[DroppedItem] = []
    for f in draft.facts:
        label = f"{f.name}={f.value}"
        if not span_in(f.span, evidence):
            dropped.append(DroppedItem(label=label, reason="span not found in evidence"))
        elif not _value_consistent(f):
            dropped.append(DroppedItem(label=label, reason="value not in its span"))
        else:
            facts.append(Fact(name=f.name.strip().lower(), value=f.value.strip(), span=f.span))

    entity = draft.entity_name.strip() if draft.entity_name else None
    if entity and normalize(entity) not in normalize(evidence):
        entity = None

    date = (draft.effective_date or "").strip() or None
    date_span = draft.effective_date_span
    if date is None or not _ISO_DATE.match(date) or not span_in(date_span, evidence):
        date, date_span = None, None
    elif date[:4] not in date_span:  # the year must be written in the span it came from
        date, date_span = None, None

    return EvidenceFacts(
        speaks_to_claim=draft.speaks_to_claim and bool(facts),
        entity_name=entity,
        effective_date=date,
        effective_date_span=date_span,
        facts=facts,
        dropped=dropped,
    )


async def extract_facts(
    llm: StructuredLlm,
    claim: ClaimRef,
    evidence_text: str,
    *,
    source_label: str = "evidence",
) -> EvidenceFacts:
    """Extract facts relevant to `claim` from one evidence text (already HTML-stripped)."""
    claim_block = json.dumps(
        {"claim": claim.text, "category": claim.category, "components": claim.components},
        ensure_ascii=False,
        sort_keys=True,
    )
    user = (
        f"Claim:\n<claim>\n{claim_block}\n</claim>\n\n"
        f"Evidence ({source_label}):\n<evidence>\n{evidence_text}\n</evidence>"
    )
    draft, record = await run_structured(llm, FACTS.system, user, EvidenceFactsDraft)
    result = finalize_facts(draft, evidence_text)
    result.claim_id = claim.id
    result.calls = [record] if record is not None else []
    return result
