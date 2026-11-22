"""Evidence-span validation: an extracted value must be readable from its quote.

This is the guard against values coming from a model's memory rather than the
record (PRD principle 1). A fact that fails here is rejected and can never drive
a claim status.
"""

from __future__ import annotations

from app.domain.enums import ValueKind
from app.domain.types import ExtractedFact, ExtractionCheck
from app.rules import policy
from app.rules.compare import (
    contains_phrase,
    normalize_text,
    parse_dates,
    parse_months,
    parse_numbers,
    parse_years,
    to_date,
    to_month,
    to_number,
    to_stage,
    to_year,
)

_NUMBER_REL_TOLERANCE = 0.005


def _ok(reason: str = "value appears in the span") -> ExtractionCheck:
    return ExtractionCheck(valid=True, reason=reason)


def _bad(reason: str) -> ExtractionCheck:
    return ExtractionCheck(valid=False, reason=reason)


def span_for(fact: ExtractedFact) -> str | None:
    """The text a fact must be derivable from: its quote, else its structured field."""
    ev = fact.evidence
    if ev.quote and ev.quote.strip():
        return ev.quote
    if ev.field_path and ev.field_value is not None:
        return str(ev.field_value)
    return None


def validate_extraction(fact: ExtractedFact, span: str | None) -> ExtractionCheck:
    """Reject a decisive value (year, month, date, number, city, name, role,
    stage) that does not appear in, or cannot be derived from, the span."""
    if fact.value is None:
        return _bad("no value extracted")
    if span is None or not span.strip():
        return _bad("no quoted span or field to check the value against")

    rule = policy.COMPONENT_RULES.get(fact.component)
    kind = rule.kind if rule else ValueKind.TEXT
    value = fact.value

    if kind is ValueKind.YEAR:
        y = to_year(value)
        if y is None:
            return _bad(f"{value!r} is not a year")
        return _ok() if y in parse_years(span) else _bad(f"year {y} is not in the span")

    if kind is ValueKind.MONTH:
        m = to_month(value)
        if m is None:
            y = to_year(value)
            if y is not None and y in parse_years(span):
                return _ok("year appears in the span")
            return _bad(f"{value!r} is not a month or year found in the span")
        return _ok() if m in parse_months(span) else _bad(f"{m[0]}-{m[1]:02d} is not in the span")

    if kind is ValueKind.DATE:
        d = to_date(value)
        if d is None:
            return _bad(f"{value!r} is not a date")
        return _ok() if d in parse_dates(span) else _bad(f"date {d.isoformat()} is not in the span")

    if kind in (ValueKind.COUNT, ValueKind.MONEY, ValueKind.PERCENT):
        n = to_number(value)
        if n is None:
            return _bad(f"{value!r} is not a number")
        for candidate in parse_numbers(span):
            if abs(candidate - n) <= _NUMBER_REL_TOLERANCE * max(abs(n), 1.0):
                return _ok()
        return _bad(f"number {value} is not in the span")

    if kind is ValueKind.STAGE:
        stage = to_stage(value)
        if stage is None:
            return _bad(f"{value!r} is not a known stage")
        text = f" {normalize_text(span)} "
        cues = policy.STAGE_CUES.get(stage, ())
        if any(f" {normalize_text(cue)}" in text for cue in cues):
            return _ok("stage wording appears in the span")
        return _bad(f"nothing in the span says the stage is {stage}")

    if kind is ValueKind.BOOL:
        # Yes/no readings are not decisive values on their own; the components
        # they combine with (year, amount, lender) are checked separately.
        return _ok("non-decisive value")

    # TEXT, TEXT_CONTAINS, ENUM: names, cities, roles.
    if contains_phrase(span, value):
        return _ok()
    return _bad(f"{value!r} is not in the span")


def screen_fact(fact: ExtractedFact, entity_ids: list[str]) -> ExtractionCheck:
    """Identity guard plus span validation."""
    if entity_ids and fact.evidence.entity_id not in entity_ids:
        return _bad(
            f"evidence is attached to {fact.evidence.entity_id or 'no entity'}, "
            "not to the entity this claim is about"
        )
    return validate_extraction(fact, span_for(fact))
