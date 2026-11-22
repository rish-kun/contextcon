"""Evidence-span validation: an extracted value must be readable from its quote.

This is the guard against values coming from a model's memory rather than the
record (PRD principle 1). A fact that fails here is rejected and can never drive
a claim status.

Validation is exact. It reads the span with the same typed parsers the rules
use (sign, scale, percent, currency, date precision, polarity) but applies no
comparison tolerance: tolerances belong to comparing a fact with a claim
(``compare``), never to deciding whether a value was read correctly.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.domain.enums import ValueKind
from app.domain.types import Evidence, ExtractedFact, ExtractionCheck
from app.rules import policy
from app.rules.compare import (
    Quantity,
    contains_phrase,
    currency_code,
    normalize_text,
    parse_dates,
    parse_months,
    parse_quantities,
    parse_years,
    same_number,
    to_bool,
    to_date,
    to_month,
    to_quantity,
    to_stage,
    to_year,
)


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


def _is_structured(fact: ExtractedFact, span: str) -> bool:
    ev = fact.evidence
    has_quote = bool(ev.quote and ev.quote.strip())
    return not has_quote and ev.field_path is not None and span == str(ev.field_value)


# --- Polarity and stage wording -------------------------------------------------

NEGATION_WORDS = frozenset(
    {"no", "not", "never", "without", "nil", "none", "zero", "free", "nothing", "neither", "nor"}
)
FUTURE_WORDS = (
    "will",
    "plan",
    "planned",
    "plans",
    "planning",
    "expected",
    "expects",
    "expect",
    "to be",
    "set to",
    "upcoming",
    "proposed",
    "scheduled",
    "intends",
    "intend",
    "aims",
    "aim to",
    "yet to",
)


def is_negated(text: str) -> bool:
    """True when the text states the negative ("no debt", "has not raised")."""
    if "n't" in text.casefold() or "n’t" in text.casefold():
        return True
    return any(tok in NEGATION_WORDS for tok in normalize_text(text).split())


def _cue_positions(tokens: list[str], cue: str) -> list[int]:
    """Indexes where a cue starts; the last cue word may be a prefix ("plan" → "plans")."""
    words = normalize_text(cue).split()
    if not words:
        return []
    hits = []
    for i in range(len(tokens) - len(words) + 1):
        head = tokens[i : i + len(words) - 1]
        last = tokens[i + len(words) - 1]
        if head == words[:-1] and last.startswith(words[-1]):
            hits.append(i)
    return hits


def stage_stated(span: str, stage: str) -> bool:
    """Does the span say the stage is ``stage``? Negated cues ("has not
    opened") do not count, and an operating cue next to future wording ("will
    be operational") is ambiguous and does not count either."""
    tokens = normalize_text(span).split()
    cues = policy.STAGE_CUES.get(stage, ())
    for cue in cues:
        for i in _cue_positions(tokens, cue):
            window = tokens[max(0, i - 3) : i]
            if any(w in NEGATION_WORDS or w == "yet" for w in window):
                continue
            if stage == "operating" and any(_cue_positions(tokens, f) for f in FUTURE_WORDS):
                return False
            return True
    return False


# --- Kinds ----------------------------------------------------------------------


def infer_kind(name: str, value: Any = None) -> ValueKind:
    """Value kind for a component name, including free-form names from the
    claim extractor ("year", "count", "amount", "stage")."""
    rule = policy.COMPONENT_RULES.get(name)
    if rule is not None:
        return rule.kind
    n = name.strip().casefold()
    if isinstance(value, bool) or (
        isinstance(value, str) and normalize_text(value) in {"true", "false", "yes", "no"}
    ):
        return ValueKind.BOOL
    if n == "stage" or n.endswith("_stage"):
        return ValueKind.STAGE
    if n in {"round_type", "round", "funding_type"}:
        return ValueKind.ROUND_TYPE
    if "year" in n:
        return ValueKind.YEAR
    if "date" in n or "month" in n or n in {"when", "period"}:
        if isinstance(value, date | datetime) or (isinstance(value, str) and parse_dates(value)):
            return ValueKind.DATE
        if to_month(value) is not None:
            return ValueKind.MONTH
        return ValueKind.YEAR
    if any(w in n for w in ("pct", "percent", "growth", "margin", "rate", "share")):
        return ValueKind.PERCENT
    if any(
        w in n
        for w in (
            "amount",
            "revenue",
            "profit",
            "ebitda",
            "valuation",
            "debt",
            "turnover",
            "money",
            "value",
            "price",
            "cost",
            "loss",
            "income",
            "sales",
        )
    ):
        return ValueKind.MONEY
    if any(
        w in n
        for w in ("count", "employees", "headcount", "staff", "people", "number", "sites", "size")
    ):
        return ValueKind.COUNT
    return ValueKind.TEXT


def _value_currency(value: Any, component: str | None) -> str | None:
    if isinstance(value, str):
        q = to_quantity(value)
        if q is not None and q.currency:
            return q.currency
    if component:
        tail = component.rsplit("_", 1)[-1]
        return currency_code(tail) if tail != component else None
    return None


def _number_in_span(
    kind: ValueKind,
    value: Any,
    span: str,
    *,
    structured: bool,
    component: str | None,
) -> ExtractionCheck:
    q = to_quantity(value)
    if q is None:
        return _bad(f"{value!r} is not a number")
    want_currency = _value_currency(value, component) if kind is ValueKind.MONEY else None
    candidates: list[Quantity] = parse_quantities(span)
    for c in candidates:
        if not same_number(c.value, q.value):
            continue
        if kind is ValueKind.PERCENT:
            if not c.percent and not structured:
                continue
        elif c.percent:
            continue  # a percentage is not a count or an amount
        if kind is ValueKind.COUNT and c.currency:
            continue
        if want_currency and c.currency and c.currency != want_currency:
            continue
        return _ok()
    near = [
        c
        for c in candidates
        if same_number(abs(c.value), abs(q.value))
        or same_number(c.written, abs(q.value))
        or same_number(c.written, q.written)
    ]
    if near:
        return _bad(
            f"number {value} is not in the span as stated (sign, scale, unit or currency differs)"
        )
    return _bad(f"number {value} is not in the span")


def value_in_span(
    kind: ValueKind,
    value: Any,
    span: str | None,
    *,
    structured: bool = False,
    component: str | None = None,
) -> ExtractionCheck:
    """Is ``value`` stated by ``span`` exactly, read as ``kind``?

    ``structured`` marks a span that is a provider field value rather than
    prose: the field itself defines the unit, so a bare 18.2 may be a percent.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return _bad("no value extracted")
    if span is None or not span.strip():
        return _bad("no quoted span or field to check the value against")

    if kind is ValueKind.YEAR:
        y = to_year(value)
        if y is None:
            return _bad(f"{value!r} is not a year")
        return _ok() if y in parse_years(span) else _bad(f"year {y} is not in the span")

    if kind in (ValueKind.MONTH, ValueKind.DATE):
        # The value may not be more precise than the span: a day or month the
        # source does not state is invented.
        d = to_date(value)
        if d is not None:
            if d in parse_dates(span):
                return _ok()
            return _bad(f"date {d.isoformat()} is not in the span")
        m = to_month(value)
        if m is not None:
            if m in parse_months(span):
                return _ok()
            return _bad(f"{m[0]}-{m[1]:02d} is not in the span")
        y = to_year(value)
        if y is not None and _is_bare_year(value):
            if y in parse_years(span):
                return _ok("year appears in the span")
            return _bad(f"year {y} is not in the span")
        return _bad(f"{value!r} is not a date found in the span")

    if kind in (ValueKind.COUNT, ValueKind.MONEY, ValueKind.PERCENT):
        return _number_in_span(kind, value, span, structured=structured, component=component)

    if kind is ValueKind.STAGE:
        stage = to_stage(value)
        if stage is None:
            return _bad(f"{value!r} is not a known stage")
        if structured and to_stage(span) == stage:
            return _ok()
        if stage_stated(span, stage):
            return _ok("stage wording appears in the span")
        return _bad(f"nothing in the span says the stage is {stage}")

    if kind is ValueKind.BOOL:
        b = to_bool(value)
        if b is None:
            return _bad(f"{value!r} is not a yes/no value")
        literal = to_bool(span)
        if literal is not None:
            return _ok() if literal == b else _bad(f"the field says {literal}, not {b}")
        negated = is_negated(span)
        if b and negated:
            return _bad("the span states the negative")
        if not b and not negated:
            return _bad("the span does not state the negative")
        return _ok("polarity matches the span")

    # TEXT, TEXT_CONTAINS, ENUM, ROUND_TYPE: names, cities, roles.
    if contains_phrase(span, value):
        return _ok()
    return _bad(f"{value!r} is not in the span")


_BARE_YEAR = re.compile(r"^\s*(?:19|20)\d{2}\s*$")


def _is_bare_year(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 1900 <= value <= 2099
    return isinstance(value, str) and bool(_BARE_YEAR.match(value))


def validate_extraction(fact: ExtractedFact, span: str | None) -> ExtractionCheck:
    """Reject a decisive value (year, month, date, number, city, name, role,
    stage, yes/no) that does not appear in, or cannot be derived exactly from,
    the span."""
    if fact.value is None:
        return _bad("no value extracted")
    if span is None or not span.strip():
        return _bad("no quoted span or field to check the value against")
    kind = infer_kind(fact.component, fact.value)
    return value_in_span(
        kind,
        fact.value,
        span,
        structured=_is_structured(fact, span),
        component=fact.component,
    )


# --- Identity guard ---------------------------------------------------------------


def entity_binding_corroborated(evidence: Evidence) -> bool:
    """The evidence is attached to its entity on a corroborating identifier
    (domain, Crustdata id, registry id, ...), not on a matching name alone."""
    return evidence.entity_id is not None and any(
        b in policy.CORROBORATING_IDENTIFIERS for b in evidence.identity_basis
    )


def screen_evidence(evidence: Evidence, entity_ids: list[str]) -> ExtractionCheck:
    """Identity guard for one piece of evidence."""
    if not entity_ids:
        return _bad("no corroborated entity for this question, so no evidence can be attached")
    if evidence.entity_id not in entity_ids:
        return _bad(
            f"evidence is attached to {evidence.entity_id or 'no entity'}, "
            "not to the entity this claim is about"
        )
    if not entity_binding_corroborated(evidence):
        basis = ", ".join(evidence.identity_basis) or "nothing"
        return _bad(
            f"evidence is attached on {basis}; a matching name alone is not a "
            "corroborating identifier"
        )
    return _ok("attached on a corroborating identifier")


def screen_fact(fact: ExtractedFact, entity_ids: list[str]) -> ExtractionCheck:
    """Identity guard plus span validation. Claims, fit and the financial
    assessment all screen evidence through this one function."""
    identity = screen_evidence(fact.evidence, entity_ids)
    if not identity.valid:
        return identity
    return validate_extraction(fact, span_for(fact))
