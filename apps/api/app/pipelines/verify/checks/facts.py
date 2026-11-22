"""Evidence → facts the rules can use.

Two kinds of evidence:

- Structured fields (a provider's headcount, funding round, HQ): turned into facts by
  code. The field's own text is stored as the span, so the value is checked against
  it like any quote.
- Text (a registry page, a news article, a career record): `extract_facts` reads it
  for the claim, keeping only facts whose span is verbatim in the text. Each fact's
  value is then validated against its span (`validate_extraction`); a rejected fact
  is kept for the audit trail but cannot drive a status. A text that yields no fact
  is a source that was read and is silent.

Every fact becomes its own evidence row (see `sources.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.db.models import Source as SourceRow
from app.domain.types import Claim, ExtractedFact
from app.extraction import ClaimRef, extract_facts
from app.extraction.llm import StructuredLlm
from app.pipelines.verify.checks import activity as check_activity
from app.pipelines.verify.checks.sources import EvidenceStore, domain_evidence
from app.pipelines.verify.claims.components import typed_value
from app.rules import policy
from app.rules.compare import compare, contains_phrase, to_date, to_month, to_year
from app.rules.validation import span_for, validate_extraction

# Loose names a model may use for a component, by claim category.
_FACT_ALIASES: dict[str, dict[str, str]] = {
    "identity_incorporation": {
        "year": "incorporation_year",
        "founded_year": "incorporation_year",
        "date": "incorporation_date",
        "city": "hq_city",
        "registered_office_city": "registered_city",
        "name": "legal_name",
        "company_name": "legal_name",
    },
    "location": {"city": "hq_city", "headquarters": "hq_city"},
    "team_size": {"count": "employee_count", "employees": "employee_count"},
    "leadership_history": {
        "name": "person_name",
        "person": "person_name",
        "title": "role",
        "company": "employer",
        "organisation": "employer",
        "organization": "employer",
        "industry": "employer_industry",
    },
    "funding": {
        "year": "round_year",
        "date": "round_date",
        "amount": "amount_usd",
        "round": "round_type",
    },
    "dated_event": {"date": "event_date", "month": "event_date"},
    "debt_security": {"charge": "security_registered", "charge_holder": "lender"},
}


def component_for(name: str, category: str) -> str | None:
    key = name.strip().lower()
    if key in policy.COMPONENT_RULES:
        return key
    mapped = _FACT_ALIASES.get(category, {}).get(key)
    return mapped if mapped in policy.COMPONENT_RULES else None


def iso_date(value: str | None) -> date | None:
    """An effective date written as YYYY, YYYY-MM or YYYY-MM-DD (first day if partial)."""
    if not value:
        return None
    d = to_date(value)
    if d is not None:
        return d
    month = to_month(value)
    if month is not None:
        return date(month[0], month[1], 1)
    year = to_year(value)
    return date(year, 1, 1) if year else None


@dataclass
class TextUnit:
    """One readable text from one source, attached to one entity."""

    source: SourceRow
    text: str
    entity_ref: str
    as_of: date | None = None
    label: str = "evidence"
    # Lines of a career record: (line text, at the confirmed company?). Used to keep
    # only the positions a leadership claim is about.
    career_lines: list[tuple[str, bool]] | None = None


@dataclass
class FactBatch:
    facts: list[ExtractedFact] = field(default_factory=list)
    rejected: int = 0
    dropped: int = 0
    llm_calls: int = 0


def claim_ref(claim: Claim, category: str) -> ClaimRef:
    return ClaimRef(
        id=claim.id,
        text=claim.text,
        category=category,  # type: ignore[arg-type]
        components={c.name: str(c.value) for c in claim.components},
    )


async def facts_from_text(
    store: EvidenceStore,
    llm: StructuredLlm,
    claim: Claim,
    unit: TextUnit,
    *,
    delete_after: Any = None,
) -> FactBatch:
    category = claim.category.value
    with check_activity.reading(unit.source):
        result = await extract_facts(
            llm, claim_ref(claim, category), unit.text, source_label=unit.label
        )
    batch = FactBatch(llm_calls=1, dropped=len(result.dropped))
    if not result.facts:
        return batch
    as_of = iso_date(result.effective_date) or unit.as_of
    drafts: list[tuple[str, Any, str]] = []
    for f in result.facts:
        component = component_for(f.name, category)
        if component is None:
            batch.dropped += 1
            continue
        value = typed_value(component, f.value)
        if value is None:
            batch.dropped += 1
            continue
        drafts.append((component, value, f.span))
    if unit.career_lines is not None:
        drafts = career_relevant(claim, drafts, unit.career_lines)

    for i, (component, value, span) in enumerate(drafts):
        row = await store.evidence(
            unit.source,
            entity_ref=unit.entity_ref,
            component=component,
            span=span,
            value=value,
            as_of=as_of,
            delete_after=delete_after,
        )
        fact = ExtractedFact(
            id=f"{row.id}:{component}:{i}",
            evidence=domain_evidence(row, unit.source, store.company_id),
            component=component,
            value=value,
        )
        if not validate_extraction(fact, span_for(fact)).valid:
            batch.rejected += 1  # kept: the rules show it as rejected, never decisive
        else:
            await check_activity.fact_found(fact)
        batch.facts.append(fact)
    return batch


async def fact_from_field(
    store: EvidenceStore,
    source: SourceRow,
    *,
    entity_ref: str,
    component: str,
    value: Any,
    field_path: str,
    span: str | None = None,
    as_of: date | None = None,
) -> ExtractedFact:
    """A fact read by code from a structured field."""
    row = await store.evidence(
        source,
        entity_ref=entity_ref,
        component=component,
        field_path=field_path,
        span=span,
        value=value,
        as_of=as_of,
    )
    fact = ExtractedFact(
        id=f"{row.id}:{component}",
        evidence=domain_evidence(row, source, store.company_id),
        component=component,
        value=value,
    )
    await check_activity.fact_found(fact)
    return fact


# A career record lists many positions. A claim about one employer or role is not
# contradicted by the others: they are silent about it. So only positions that match
# the claim's employer, role or industry are kept, with their years.
_ANCHORS = ("employer", "role", "employer_industry", "person_name")


def _line_of(span: str, lines: list[tuple[str, bool]]) -> int | None:
    for i, (line, _) in enumerate(lines):
        if contains_phrase(line, span) or span.strip() in line:
            return i
    return None


def career_relevant(
    claim: Claim, drafts: list[tuple[str, Any, str]], lines: list[tuple[str, bool]]
) -> list[tuple[str, Any, str]]:
    claimed = {c.name: c for c in claim.components}
    kept: list[tuple[str, Any, str]] = []
    anchor_lines: set[int] = set()
    for component, value, span in drafts:
        if component not in _ANCHORS:
            continue
        comp = claimed.get(component)
        if comp is None:
            continue
        rule = policy.COMPONENT_RULES[component]
        if compare(rule.kind, comp.value, comp.op, value) == "match":
            kept.append((component, value, span))
            if component != "person_name":
                line = _line_of(span, lines)
                if line is not None:
                    anchor_lines.add(line)
    has_position_anchor = any(c in claimed for c in ("employer", "role", "employer_industry"))
    if not has_position_anchor:
        # A claim about years alone ("joined in 2016") is about the confirmed company.
        anchor_lines = {i for i, (_, at_company) in enumerate(lines) if at_company}
    for component, value, span in drafts:
        if component in ("start_year", "end_year"):
            line = _line_of(span, lines)
            if line is not None and line in anchor_lines:
                kept.append((component, value, span))
    return kept
