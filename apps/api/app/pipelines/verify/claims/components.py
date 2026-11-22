"""Claim components, named per `app.rules.policy.COMPONENT_RULES`.

`extract_claims` returns loosely named parts ("year", "city", "organisation"). The
status rules need the policy's names and typed values ("incorporation_year": 2014).
A small structured LLM call maps each claim onto those names; code then keeps a
component only when its name is in the rule table and its value can be read from
the claim's own words (the same span check the rules apply to evidence). When the
model is unavailable, a conservative alias table is used instead.

A component that cannot be read from the claim is dropped, never guessed. An
over-specific guess is worse than none: a generic phrase ("a national logistics
firm") mapped to `employer` would compare as a different employer and read as a
contradiction.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.enums import ClaimCategory, SourceReliability, ValueKind
from app.domain.types import ClaimComponent, Evidence, ExtractedFact, Source
from app.extraction.llm import StructuredLlm, run_structured
from app.rules import policy
from app.rules.compare import to_bool, to_month, to_number, to_stage, to_year
from app.rules.validation import validate_extraction

NORMALISE_PROMPT_VERSION = "2026-11-22.claims-components.2"

Op = Literal["eq", "gte", "lte"]

_DESCRIPTIONS: dict[str, str] = {
    "legal_name": "the company's registered legal name",
    "cin": "the corporate identity number",
    "incorporation_year": "year the company was incorporated or founded",
    "incorporation_date": "full date of incorporation (YYYY-MM-DD)",
    "registered_city": "city of the registered office",
    "hq_city": "city where the company is based or headquartered",
    "country": "country the company is based in",
    "operating_city": "a city where the company operates (not its HQ)",
    "employee_count": "number of employees",
    "headcount_growth_pct": "headcount growth in percent",
    "person_name": "the named person the claim is about",
    "role": "a role or function the person held, e.g. operations, CEO, CTO",
    "employer": "the NAME of a specific organisation the person worked at",
    "employer_industry": "the industry of a former employer when no name is given, e.g. "
    "logistics for 'a national logistics firm'",
    "start_year": "year the person started the role",
    "end_year": "year the person left the role",
    "raised": "true when the claim says money was raised",
    "round_year": "year of the funding round",
    "round_date": "month of the funding round (YYYY-MM)",
    "round_type": "a named round type only: seed, series_a, series_b, ... Words like "
    "'growth funding' are not a round type",
    "amount_usd": "amount raised in US dollars, as a number",
    "investor": "a named investor",
    "announced": "true when the claim is only that something was announced",
    "event": "what happened, in a few words, e.g. new facility, launch, expansion",
    "event_date": "month the event happened (YYYY-MM)",
    "stage": "lifecycle stage the claim asserts: planned, under_construction, operating, closed",
    "counterparty": "the named customer or partner",
    "relationship": "the kind of relationship, e.g. customer, partner, supplier",
    "since_year": "year the relationship started",
    "contract_value": "contract value as a number",
    "revenue": "revenue figure as a number",
    "profit": "profit figure as a number",
    "ebitda": "EBITDA figure as a number",
    "revenue_growth_pct": "revenue growth in percent",
    "fiscal_year": "the fiscal year a financial figure refers to",
    "has_debt": "true or false: whether the company says it has debt",
    "debt_amount": "amount of debt as a number",
    "security_registered": "true or false: whether security/charges are registered",
    "lender": "the named lender",
    "has_litigation": "true or false: whether the company says it is in litigation",
    "case_reference": "a court case reference",
    "certification": "a named certification or standard, e.g. ISO 9001:2015, ISO/IEC 27001, "
    "SOC 2 Type II, CMMI Level 3",
    "trademark": "the trademark or brand name the claim says is registered",
    "mark_owner": "the legal owner the claim names for the trademark",
    "customer_count": "number of customers or clients",
    "country_count": "number of countries the customers are in",
}


def _catalogue() -> str:
    by_check: dict[ClaimCategory, list[str]] = {}
    for name, rule in policy.COMPONENT_RULES.items():
        by_check.setdefault(rule.check, []).append(name)
    lines = []
    for check, names in by_check.items():
        lines.append(f"{check.value}:")
        for name in names:
            kind = policy.COMPONENT_RULES[name].kind.value
            lines.append(f"  - {name} ({kind}): {_DESCRIPTIONS.get(name, name)}")
    return "\n".join(lines)


NORMALISE_SYSTEM = (
    """\
You are an extraction step inside DealProof, an investment screening tool.
You only restate claims as structured parts. You never judge whether a claim is true.

For each numbered claim, list its checkable parts using ONLY these component names
(grouped by the check they belong to; a claim may use names from any group):

"""
    + _catalogue()
    + """

Rules:
- value must be copied from the claim's words. Exceptions: booleans are "true" or
  "false"; months are written YYYY-MM; stages use the words listed above; amounts
  may be written as plain numbers (12 crore -> keep the claim's wording).
- op is "eq" unless the claim says "more than"/"over"/"at least" (gte) or
  "fewer than"/"under"/"at most" (lte).
- Leave a part out when the claim does not state it. Never use a component for a
  vague description: "a national logistics firm" is employer_industry=logistics,
  not employer.
- "We have no debt" is has_debt=false. "We opened a facility" is event plus
  stage=operating. "We raised funding in 2025" is raised=true, round_year=2025.
"""
)


class ComponentDraft(BaseModel):
    name: str
    value: str
    op: Op = "eq"


class ClaimComponentsDraft(BaseModel):
    index: int
    components: list[ComponentDraft] = Field(default_factory=list)


class NormaliseDraft(BaseModel):
    claims: list[ClaimComponentsDraft] = Field(default_factory=list)


class NormalisedComponents(BaseModel):
    components: list[ClaimComponent] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)


# Loose names from `extract_claims`, by category. Only unambiguous ones: a
# generic "organisation" is not mapped to `employer` (see module docstring).
_ALIASES: dict[str, dict[str, str]] = {
    "identity_incorporation": {
        "year": "incorporation_year",
        "founded": "incorporation_year",
        "date": "incorporation_date",
        "city": "hq_city",
        "country": "country",
        "legal_name": "legal_name",
        "cin": "cin",
    },
    "location": {"city": "hq_city", "country": "country"},
    "team_size": {"count": "employee_count", "employees": "employee_count"},
    "leadership_history": {
        "person": "person_name",
        "name": "person_name",
        "role": "role",
        "title": "role",
        "start_year": "start_year",
        "end_year": "end_year",
    },
    "funding": {
        "year": "round_year",
        "date": "round_date",
        "round_type": "round_type",
        "investor": "investor",
    },
    "dated_event": {"event": "event", "date": "event_date", "stage": "stage"},
    "customer_partnership": {"customer": "counterparty", "partner": "counterparty"},
    "financials": {"revenue": "revenue", "year": "fiscal_year"},
    "debt_security": {"lender": "lender"},
    "litigation": {},
    "compliance": {"certification": "certification", "standard": "certification"},
    "intellectual_property": {"trademark": "trademark", "mark": "trademark", "owner": "mark_owner"},
    "other": {},
}

_CLAIM_SOURCE = Source(
    id="claim-text",
    provider="claim",
    label="claim text",
    retrieved_at=dt.datetime(2000, 1, 1),
    reliability=SourceReliability.SELLER_STATEMENT,
)


def typed_value(name: str, raw: str) -> Any:
    """Convert a string value to the type the rule table compares; None if it can't."""
    rule = policy.COMPONENT_RULES[name]
    text = raw.strip()
    if not text:
        return None
    kind = rule.kind
    if kind is ValueKind.YEAR:
        return to_year(text)
    if kind is ValueKind.MONTH:
        month = to_month(text)
        if month is not None:
            return f"{month[0]:04d}-{month[1]:02d}"
        return to_year(text)
    if kind is ValueKind.DATE:
        return text
    if kind in (ValueKind.COUNT, ValueKind.MONEY, ValueKind.PERCENT):
        number = to_number(text)
        if number is None:
            return None
        return int(number) if float(number).is_integer() else number
    if kind is ValueKind.BOOL:
        return to_bool(text)
    if kind is ValueKind.STAGE:
        return to_stage(text)
    return text


def readable_from(name: str, value: Any, claim_text: str) -> bool:
    """True when `value` can be read from the claim's own words (same check as evidence)."""
    rule = policy.COMPONENT_RULES[name]
    if rule.kind is ValueKind.BOOL:
        return isinstance(value, bool)
    evidence = Evidence(id="claim", source=_CLAIM_SOURCE, quote=claim_text)
    fact = ExtractedFact(id="claim", evidence=evidence, component=name, value=value)
    return validate_extraction(fact, claim_text).valid


def finalize_components(drafts: list[ComponentDraft], claim_text: str) -> NormalisedComponents:
    kept: dict[str, ClaimComponent] = {}
    dropped: list[str] = []
    for d in drafts:
        name = d.name.strip().lower()
        if name not in policy.COMPONENT_RULES:
            dropped.append(f"{name}: not a known component")
            continue
        value = typed_value(name, d.value)
        if value is None:
            dropped.append(f"{name}: value {d.value!r} has the wrong type")
            continue
        if not readable_from(name, value, claim_text):
            dropped.append(f"{name}: value {d.value!r} is not in the claim")
            continue
        if name in kept:
            continue  # first reading wins; one value per component
        kept[name] = ClaimComponent(name=name, value=value, op=d.op)
    return NormalisedComponents(components=list(kept.values()), dropped=dropped)


def from_aliases(category: str, raw: dict[str, str], claim_text: str) -> NormalisedComponents:
    aliases = _ALIASES.get(category, {})
    drafts = [
        ComponentDraft(name=aliases.get(k, k), value=v)
        for k, v in raw.items()
        if k in aliases or k in policy.COMPONENT_RULES
    ]
    return finalize_components(drafts, claim_text)


class ClaimToNormalise(BaseModel):
    text: str
    category: str
    raw_components: dict[str, str] = Field(default_factory=dict)


async def normalise_components(
    llm: StructuredLlm | None, claims: list[ClaimToNormalise]
) -> list[NormalisedComponents]:
    """One structured call for all claims; falls back to aliases per claim."""
    if not claims:
        return []
    fallback = [from_aliases(c.category, c.raw_components, c.text) for c in claims]
    if llm is None:
        return fallback
    lines = [f"{i}. [{c.category}] {c.text}" for i, c in enumerate(claims)]
    user = "Claims:\n<claims>\n" + "\n".join(lines) + "\n</claims>"
    draft, _ = await run_structured(llm, NORMALISE_SYSTEM, user, NormaliseDraft)
    by_index = {d.index: d for d in draft.claims}
    out: list[NormalisedComponents] = []
    for i, claim in enumerate(claims):
        d = by_index.get(i)
        if d is None or not d.components:
            out.append(fallback[i])
            continue
        result = finalize_components(d.components, claim.text)
        out.append(result if result.components else fallback[i])
    return out


# --- Storage shape of `claims.components` (JSONB) ----------------------------
# {"components": [{"name", "value", "op"}], "raw": {...}, "intake": {...}}. The
# evaluate reader (`app.pipelines.evaluate.inputs.claim_components`) reads the
# "components" list; "raw" keeps the extractor's loose names, "intake" marks text
# that could not be read.


def to_jsonb(
    components: list[ClaimComponent],
    *,
    raw: dict[str, str] | None = None,
    intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"components": [c.model_dump(mode="json") for c in components]}
    if raw:
        data["raw"] = raw
    if intake:
        data["intake"] = intake
    return data


def from_jsonb(data: dict[str, Any] | None) -> list[ClaimComponent]:
    data = data or {}
    items = data.get("components")
    if isinstance(items, list):
        return [
            ClaimComponent(name=c["name"], value=c.get("value"), op=c.get("op") or "eq")
            for c in items
            if isinstance(c, dict) and c.get("name") in policy.COMPONENT_RULES
        ]
    # A flat {name: value} mapping written by another step.
    return [ClaimComponent(name=k, value=v) for k, v in data.items() if k in policy.COMPONENT_RULES]


def public_components(data: dict[str, Any] | None) -> dict[str, Any]:
    """Components for API output, as {name: value}."""
    return {c.name: c.value for c in from_jsonb(data)}


def intake_meta(data: dict[str, Any] | None) -> dict[str, Any]:
    return dict((data or {}).get("intake") or {})
