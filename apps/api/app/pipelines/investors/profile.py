"""Business profile → comparable-company search filters and the funding kind sought.

Deterministic: the profile form is structured, so country, headcount band and stage
come from the form fields themselves. The model-extracted spec only supplies the
natural-language activity query and, when the text leaves it open, the instrument.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import FundingKind

# Crustdata stores `funding.last_round_type` as lowercase snake_case round names.
STAGE_ORDER: tuple[str, ...] = (
    "pre_seed",
    "seed",
    "series_a",
    "series_b",
    "series_c",
    "series_d",
    "series_e",
    "series_f",
)

# `basic_info.employee_count_range` bands (professional-network convention).
EMPLOYEE_BANDS: tuple[tuple[int, float, str], ...] = (
    (1, 10, "1-10"),
    (11, 50, "11-50"),
    (51, 200, "51-200"),
    (201, 500, "201-500"),
    (501, 1000, "501-1000"),
    (1001, 5000, "1001-5000"),
    (5001, 10000, "5001-10000"),
    (10001, math.inf, "10001+"),
)

_COUNTRY_ALIASES = {
    "in": "India",
    "ind": "India",
    "india": "India",
    "bharat": "India",
    "us": "United States",
    "usa": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "uae": "United Arab Emirates",
    "singapore": "Singapore",
}

_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "company",
        "companies",
        "operator",
        "operators",
        "business",
        "services",
        "service",
        "provider",
        "providers",
        "indian",
        "based",
        "b2b",
        "b2c",
        "stage",
    }
)


def normalize_stage(text: str) -> str | None:
    """ "Series A stage" → "series_a"; "pre-seed" → "pre_seed". None if no stage named."""
    t = text.casefold()
    m = re.search(r"series[\s_-]*([a-j])\b", t)
    if m:
        return f"series_{m.group(1)}"
    if re.search(r"pre[\s_-]*seed", t):
        return "pre_seed"
    if re.search(r"\bseed\b", t):
        return "seed"
    return None


def stage_window(stage: str | None) -> list[str]:
    """The stage and its neighbours, e.g. series_a → [seed, series_a, series_b]."""
    if stage not in STAGE_ORDER:
        return []
    i = STAGE_ORDER.index(stage)
    return list(STAGE_ORDER[max(0, i - 1) : i + 2])


def headcount_range(size: str) -> tuple[int, int] | None:
    """Comparable headcount: ×0.5 of the smallest to ×2 of the largest number given."""
    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", size)]
    numbers = [n for n in numbers if n > 0]
    if not numbers:
        return None
    return max(1, math.floor(min(numbers) * 0.5)), math.ceil(max(numbers) * 2)


def employee_bands(size: str) -> list[str]:
    span = headcount_range(size)
    if span is None:
        return []
    lo, hi = span
    return [label for b_lo, b_hi, label in EMPLOYEE_BANDS if b_lo <= hi and b_hi >= lo]


def country_of(location: str) -> str | None:
    """The country named in a location ("Pune, India" → "India")."""
    parts = [p.strip() for p in re.split(r"[,/|]", location) if p.strip()]
    for part in reversed(parts):
        key = re.sub(r"[^a-z ]+", "", part.casefold()).strip()
        if key in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[key]
    return parts[-1].title() if parts else None


def sought_kind(funding_sought: str, stage: str | None = None) -> FundingKind | None:
    """Funding kind sought, from the form text. Plain "equity" falls back to the stage."""
    t = funding_sought.casefold()
    if "grant" in t:
        return FundingKind.GRANT
    if re.search(r"\b(debt|loan|credit|lending|venture debt)\b", t):
        return FundingKind.DEBT
    if re.search(r"\b(growth|private equity|pe|buyout|pre[\s-]?ipo)\b", t):
        return FundingKind.GROWTH_EQUITY
    if re.search(r"\b(venture|vc|seed|angel|series)\b", t):
        return FundingKind.VENTURE_EQUITY
    if "equity" in t and stage in STAGE_ORDER:
        return FundingKind.VENTURE_EQUITY
    return None


KIND_LABELS = {
    FundingKind.VENTURE_EQUITY: "venture equity",
    FundingKind.GROWTH_EQUITY: "growth equity",
    FundingKind.DEBT: "debt",
    FundingKind.GRANT: "grants",
}

# Extra round types searched for when the kind sought is not a venture series.
_KIND_ROUND_TYPES = {
    FundingKind.GROWTH_EQUITY: ["private_equity"],
    FundingKind.DEBT: ["debt_financing"],
    FundingKind.GRANT: ["grant"],
}


def sector_keywords(sector: str) -> list[str]:
    words = re.findall(r"[a-z][a-z-]+", sector.casefold())
    return [w for w in words if len(w) > 3 and w not in _STOPWORDS]


@dataclass
class SearchPlan:
    """What the comparables step sends to `company_search`, and how to describe it."""

    query: str
    country: str | None
    employee_bands: list[str] = field(default_factory=list)
    round_types: list[str] = field(default_factory=list)
    sector_keywords: list[str] = field(default_factory=list)
    kind_sought: FundingKind | None = None

    def filters(self, *, with_size: bool = True) -> dict[str, Any] | None:
        conditions: list[dict[str, Any]] = []
        if self.country:
            conditions.append({"field": "locations.country", "type": "=", "value": self.country})
        if with_size and self.employee_bands:
            conditions.append(
                {
                    "field": "basic_info.employee_count_range",
                    "type": "in",
                    "value": self.employee_bands,
                }
            )
        if self.round_types:
            conditions.append(
                {"field": "funding.last_round_type", "type": "in", "value": self.round_types}
            )
        else:
            # Comparables must have raised money: a recorded round of any kind.
            conditions.append({"field": "funding.last_round_type", "type": "is_not_null"})
        if len(conditions) == 1:
            return conditions[0]
        return {"op": "and", "conditions": conditions}

    def describe(self, *, with_size: bool = True) -> str:
        parts = []
        if self.country:
            parts.append(self.country)
        if with_size and self.employee_bands:
            parts.append(f"{', '.join(self.employee_bands)} employees")
        if self.round_types:
            parts.append(f"last round {', '.join(self.round_types)}")
        return "; ".join(parts) or "no structured filters"


def build_plan(profile: dict[str, Any], spec: dict[str, Any] | None = None) -> SearchPlan:
    spec = spec or {}
    stage = normalize_stage(profile.get("stage", "")) or normalize_stage(
        profile.get("funding_sought", "")
    )
    kind = sought_kind(profile.get("funding_sought", ""), stage)
    if kind is None:
        instrument = (spec.get("funding_sought") or {}).get("instrument")
        kind = {"debt": FundingKind.DEBT, "grant": FundingKind.GRANT}.get(instrument or "")
    round_types = stage_window(stage)
    if round_types and kind in _KIND_ROUND_TYPES:
        round_types += [r for r in _KIND_ROUND_TYPES[kind] if r not in round_types]
    country = country_of(profile.get("location", ""))
    if country is None:
        for c in spec.get("comparable_criteria") or []:
            if c.get("crustdata_field") == "locations.country" and isinstance(c.get("value"), str):
                country = c["value"]
                break
    query = (spec.get("activity_query") or "").strip() or profile.get("sector", "")
    return SearchPlan(
        query=query,
        country=country,
        employee_bands=employee_bands(profile.get("size", "")),
        round_types=round_types,
        sector_keywords=sector_keywords(profile.get("sector", "")),
        kind_sought=kind,
    )
