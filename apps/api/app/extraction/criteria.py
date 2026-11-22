"""Thesis → screening criteria.

The model proposes criteria; code keeps only those whose `thesis_quote` is in
the thesis (so it cannot invent a requirement), checks each Crustdata field
against a closed list and the criterion's dimension, and assigns weights from
the scoring policy. The model never sets a weight.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.extraction.llm import StructuredLlm, run_structured
from app.extraction.prompts import CRITERIA, PROMPT_VERSION
from app.extraction.spans import neutralize_tags, normalize, span_in

Dimension = Literal[
    "geography",
    "ownership",
    "industry_activity",
    "customer_type",
    "size",
    "growth_signal",
    "funding_stage",
    "founded_year",
    "other",
]
Operator = Literal[
    "equals", "not_equals", "in", "not_in", "gte", "lte", "between", "contains", "exists"
]
CriterionKind = Literal["must", "preference"]

# Fields verified against Crustdata `company_search` (get_schema, 2026-11-22),
# with the dimensions each one may test. Anything else maps to evidence.
CRUSTDATA_FIELDS: dict[str, frozenset[str]] = {
    "locations.country": frozenset({"geography"}),
    "locations.headquarters": frozenset({"geography"}),
    "headcount.largest_headcount_country": frozenset({"geography"}),
    "basic_info.company_type": frozenset({"ownership"}),
    "revenue.acquisition_status": frozenset({"ownership"}),
    "basic_info.industries": frozenset({"industry_activity"}),
    "taxonomy.professional_network_industry": frozenset({"industry_activity"}),
    "taxonomy.categories": frozenset({"industry_activity"}),
    "headcount.total": frozenset({"size"}),
    "basic_info.employee_count_range": frozenset({"size"}),
    "revenue.estimated.lower_bound_usd": frozenset({"size"}),
    "headcount.growth_percent.6m": frozenset({"growth_signal"}),
    "headcount.growth_percent.12m": frozenset({"growth_signal"}),
    "funding.last_round_type": frozenset({"funding_stage"}),
    "funding.total_investment_usd": frozenset({"funding_stage"}),
    "funding.last_fundraise_date": frozenset({"funding_stage", "growth_signal"}),
    "basic_info.year_founded": frozenset({"founded_year"}),
}

# Categorical columns: the stored value must be resolved through the free
# `/company/search/autocomplete` endpoint before filtering, or the filter
# silently matches nothing.
CATEGORICAL_FIELDS = frozenset(
    {
        "basic_info.industries",
        "taxonomy.professional_network_industry",
        "basic_info.company_type",
        "funding.last_round_type",
    }
)

# Scoring policy (plan builder call 20). Owned by the rules engine; repeated
# here only to label criteria at extraction time.
MUST_WEIGHT = 2
PREFERENCE_WEIGHT = 1

CriterionValue = str | float | list[str] | None


class CriterionDraft(BaseModel):
    """What the model returns for one criterion."""

    label: str
    kind: CriterionKind
    dimension: Dimension
    operator: Operator
    value: CriterionValue = None
    crustdata_field: str | None = None
    thesis_quote: str


class CriteriaDraft(BaseModel):
    criteria: list[CriterionDraft]
    activity_query: str


class Criterion(BaseModel):
    """A criterion ready for the editor and the search step."""

    label: str
    kind: CriterionKind
    dimension: Dimension
    operator: Operator
    value: CriterionValue = None
    weight: int
    assessment: Literal["crustdata_filter", "assessed_from_evidence"]
    crustdata_field: str | None = None
    needs_value_resolution: bool = False
    thesis_quote: str


class DroppedItem(BaseModel):
    label: str
    reason: str


class CriteriaExtraction(BaseModel):
    criteria: list[Criterion]
    activity_query: str
    dropped: list[DroppedItem] = Field(default_factory=list)
    # Criteria code added back after the model left them out (labels).
    restored: list[str] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


def finalize_criteria(
    drafts: list[CriterionDraft], source_text: str
) -> tuple[list[Criterion], list[DroppedItem]]:
    """Apply the code-side rules to model-proposed criteria."""
    kept: list[Criterion] = []
    dropped: list[DroppedItem] = []
    seen: set[tuple[str, str]] = set()
    for d in drafts:
        if not span_in(d.thesis_quote, source_text):
            dropped.append(DroppedItem(label=d.label, reason="quote not found in source text"))
            continue
        key = (d.dimension, d.label.strip().casefold())
        if key in seen:
            dropped.append(DroppedItem(label=d.label, reason="duplicate"))
            continue
        seen.add(key)

        field = (d.crustdata_field or "").strip() or None
        if field is not None and d.dimension not in CRUSTDATA_FIELDS.get(field, frozenset()):
            field = None  # unknown field, or a field that does not test this dimension
        if d.dimension == "customer_type":
            field = None  # no Crustdata column encodes customer type

        kept.append(
            Criterion(
                label=d.label.strip(),
                kind=d.kind,
                dimension=d.dimension,
                operator=d.operator,
                value=d.value,
                weight=MUST_WEIGHT if d.kind == "must" else PREFERENCE_WEIGHT,
                assessment="crustdata_filter" if field else "assessed_from_evidence",
                crustdata_field=field,
                needs_value_resolution=field in CATEGORICAL_FIELDS,
                thesis_quote=d.thesis_quote,
            )
        )
    return kept, dropped


# --- Activity criterion post-check -------------------------------------------------
#
# The thesis's activity ("warehousing and supply-chain software") is the core of a
# screen, and the model does not always return it as a criterion. When it is missing,
# code restores it from the model's activity query: the longest run of thesis words
# that the activity query also uses, outside the spans other criteria already quote.
# The quote is a verbatim thesis span, so grounding is unchanged.

_TOKEN = re.compile(r"[a-z0-9][a-z0-9&'\-]*")
_CONNECTORS = frozenset({"and", "or", "&", "of", "for", "in", "to"})
_GENERIC = frozenset(
    "companies company firms businesses players startups start-ups that which who "
    "the a an with serve serving offer offering provide providing build building".split()
)


def _stem(word: str) -> str:
    return word[:5]


def _content_stems(word: str) -> set[str]:
    parts = [p for p in word.split("-") if len(p) >= 3 and p not in _GENERIC]
    return {_stem(p) for p in parts}


def _covered(text: str, quotes: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for q in quotes:
        n = normalize(q).strip(" \"'.")
        start = text.find(n) if n else -1
        while start >= 0:
            spans.append((start, start + len(n)))
            start = text.find(n, start + 1)
    return spans


def activity_span(thesis: str, activity_query: str, quoted: list[str]) -> str | None:
    """The verbatim thesis span that states the activity, or None."""
    text = normalize(thesis)
    wanted: set[str] = set()
    for w in _TOKEN.findall(normalize(activity_query)):
        wanted |= _content_stems(w)
    if not wanted:
        return None
    covered = _covered(text, quoted)
    tokens = [
        (m.group(), m.start(), m.end())
        for m in _TOKEN.finditer(text)
        if not any(a < m.end() and m.start() < b for a, b in covered) or m.group() in _CONNECTORS
    ]
    best: tuple[int, int, int] | None = None  # (matches, start, end)
    run: list[tuple[str, int, int]] = []

    def close() -> None:
        nonlocal best
        while run and (run[-1][0] in _CONNECTORS or not (_content_stems(run[-1][0]) & wanted)):
            run.pop()
        while run and (run[0][0] in _CONNECTORS or not (_content_stems(run[0][0]) & wanted)):
            run.pop(0)
        if run:
            hits = sum(1 for t, _, _ in run if _content_stems(t) & wanted)
            if best is None or hits > best[0]:
                best = (hits, run[0][1], run[-1][2])
        run.clear()

    prev_end = None
    for tok, start, end in tokens:
        gap = text[prev_end:start] if prev_end is not None else " "
        adjacent = prev_end is None or gap.strip(" ,") == ""
        if not adjacent or not (tok in _CONNECTORS or _content_stems(tok) & wanted):
            close()
        if tok in _CONNECTORS or _content_stems(tok) & wanted:
            run.append((tok, start, end))
        prev_end = end
    close()
    if best is None:
        return None
    span = text[best[1] : best[2]]
    # Prefer the thesis's own casing for display; grounding is the same either way.
    pattern = r"\s+".join(re.escape(part) for part in span.split())
    m = re.search(pattern, thesis, flags=re.IGNORECASE)
    return m.group() if m else span


def ensure_activity_criterion(
    criteria: list[Criterion], thesis: str, activity_query: str
) -> Criterion | None:
    """Restore the activity criterion when the model left it out. Returns the added
    criterion (already appended), or None when nothing was needed or found."""
    if any(c.dimension == "industry_activity" for c in criteria):
        return None
    if not activity_query.strip():
        return None
    quote = activity_span(thesis, activity_query, [c.thesis_quote for c in criteria])
    if quote is None or not span_in(quote, thesis):
        return None
    restored = Criterion(
        label=quote[:1].upper() + quote[1:],
        kind="must",
        dimension="industry_activity",
        operator="contains",
        value=quote,
        weight=MUST_WEIGHT,
        assessment="assessed_from_evidence",
        thesis_quote=quote,
    )
    criteria.append(restored)
    return restored


async def extract_criteria(llm: StructuredLlm, thesis: str) -> CriteriaExtraction:
    thesis = thesis.strip()
    if not thesis:
        raise ValueError("thesis is empty")
    draft, record = await run_structured(
        llm,
        CRITERIA.system,
        f"Investment thesis:\n<thesis>\n{neutralize_tags(thesis)}\n</thesis>",
        CriteriaDraft,
    )
    criteria, dropped = finalize_criteria(draft.criteria, thesis)
    restored = ensure_activity_criterion(criteria, thesis, draft.activity_query)
    query = draft.activity_query.strip() or thesis
    return CriteriaExtraction(
        criteria=criteria,
        activity_query=query,
        dropped=dropped,
        restored=[restored.label] if restored else [],
        calls=[record] if record is not None else [],
    )
