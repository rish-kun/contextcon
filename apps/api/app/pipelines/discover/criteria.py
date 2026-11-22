"""Criteria: extraction → stored rows → rules criteria and Crustdata filters.

Stored shape (`criteria` table): `operator` uses the contract vocabulary
(eq, in, gte, lte, between, contains_any, is_true) and `crustdata_filter` is either
null (assessed from evidence) or `{"field", "type", "value"}` with Crustdata's
operator names (`=`, `in`, `=>`, `=<`, `(.)`; `between` is expanded to `=>` and `=<`
when the query is built).

Hard provider filters
---------------------
A must-have becomes a *hard* provider filter only when its field is reliably
populated (`RELIABLE_FILTER_FIELDS`). Every other mapped must-have is sent
unknown-inclusive: `(field matches) OR (field is null)`, so a company whose field is
empty is not silently dropped. Crustdata treats the empty string as null for
`is_null` (checked live 2026-11-22: for companies in India, `basic_info.company_type`
is empty on about 1.38M of 3.3M rows, which is why ownership is not a hard filter).
Preferences never filter the search; they only score.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import CriterionKind, CriterionOperator
from app.domain.types import Criterion as RuleCriterion
from app.extraction.criteria import CATEGORICAL_FIELDS, CRUSTDATA_FIELDS
from app.extraction.criteria import Criterion as ExtractedCriterion
from app.rules import policy

# Fields populated on nearly every Crustdata company row: safe as hard filters.
RELIABLE_FILTER_FIELDS = frozenset(
    {
        "locations.country",
        "headcount.largest_headcount_country",
        "basic_info.industries",
        "taxonomy.professional_network_industry",
    }
)

# Values that must be the exact stored string; resolved through the free
# `/company/search/autocomplete` endpoint before filtering or comparing.
RESOLVE_FIELDS = CATEGORICAL_FIELDS | {"locations.country", "headcount.largest_headcount_country"}
# For these, a suggestion must share the value's prefix ("Indian" → "India", never
# "British Indian Ocean Territory"). Industry fields also accept a whole-word match.
PREFIX_ONLY_FIELDS = frozenset(
    {
        "locations.country",
        "headcount.largest_headcount_country",
        "basic_info.company_type",
        "funding.last_round_type",
    }
)

# Extraction operator → contract operator. Negations have no rules operator, so a
# negated criterion is kept for the user but assessed from evidence (unknown).
_EXTRACTION_OPS: dict[str, str] = {
    "equals": "eq",
    "in": "in",
    "gte": "gte",
    "lte": "lte",
    "between": "between",
    "contains": "contains_any",
    "exists": "is_true",
}
_FILTER_TYPES: dict[str, str] = {
    "eq": "=",
    "in": "in",
    "gte": "=>",
    "lte": "=<",
    "between": "between",
    "contains_any": "(.)",
}


def evidence_field(dimension: str) -> str:
    """Field key for a criterion with no provider mapping: never populated, so the
    rules return `unknown` ("assessed from evidence")."""
    return f"evidence:{dimension}"


def policy_weight(kind: str) -> int:
    return policy.CRITERION_WEIGHTS[CriterionKind(kind)]


def make_filter(field_name: str | None, operator: str, value: Any) -> dict[str, Any] | None:
    """The stored provider filter for a criterion, or None when it cannot be mapped."""
    if not field_name or field_name not in CRUSTDATA_FIELDS:
        return None
    ftype = _FILTER_TYPES.get(operator)
    if ftype is None or value is None or value == "" or value == []:
        return None
    if operator == "between" and not (isinstance(value, list) and len(value) == 2):
        return None
    return {"field": field_name, "type": ftype, "value": value}


def from_extraction(c: ExtractedCriterion) -> dict[str, Any]:
    """Column values for one extracted criterion."""
    operator = _EXTRACTION_OPS.get(c.operator)
    negated = operator is None
    operator = operator or ("in" if isinstance(c.value, list) else "eq")
    filt = None if negated else make_filter(c.crustdata_field, operator, c.value)
    return {
        "label": c.label,
        "kind": c.kind,
        "dimension": c.dimension,
        "operator": operator,
        "value": c.value,
        "crustdata_filter": filt,
        "weight": float(policy_weight(c.kind)),
    }


def snapshot_row(row: Any) -> dict[str, Any]:
    """A plain dict of a `criteria` row, frozen into the discovery run."""
    return {
        "id": str(row.id),
        "label": row.label,
        "kind": row.kind,
        "dimension": row.dimension,
        "operator": row.operator,
        "value": row.value,
        "crustdata_filter": row.crustdata_filter,
        "weight": int(row.weight) if row.weight is not None else policy_weight(row.kind),
    }


# --- Value resolution ----------------------------------------------------------


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().casefold()


def match_suggestions(value: str, suggestions: Iterable[str], *, prefix_only: bool) -> list[str]:
    v = _norm(value)
    out: list[str] = []
    for s in suggestions:
        n = _norm(s)
        if not n:
            continue
        ok = n == v or n.startswith(v) or (v.startswith(n) and len(n) >= 4)
        if not ok and not prefix_only:
            ok = re.search(rf"\b{re.escape(v)}\b", n) is not None
        if ok and s not in out:
            out.append(s)
    return out


@dataclass
class Resolution:
    """Outcome of resolving one criterion's values to stored provider values."""

    status: str  # "not_needed" | "resolved" | "unresolved"
    values: list[Any] | None = None
    unmatched: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {"status": self.status, "values": self.values, "unmatched": self.unmatched}

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> Resolution:
        if not data:
            return cls("not_needed")
        return cls(data["status"], data.get("values"), list(data.get("unmatched") or []))


def needs_resolution(c: Mapping[str, Any]) -> bool:
    f = c.get("crustdata_filter")
    return bool(f) and f["field"] in RESOLVE_FIELDS and f["type"] in ("=", "in")


def as_values(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple) else [value]


# --- Rules criteria and provider filters ----------------------------------------


def rule_criterion(c: Mapping[str, Any], resolution: Resolution | None = None) -> RuleCriterion:
    """The rules engine's view of a stored criterion.

    A criterion whose provider value could not be resolved is assessed from evidence,
    so a guessed value can never produce a verified fail.
    """
    filt = c.get("crustdata_filter")
    operator = c["operator"]
    value = c["value"]
    field_name = evidence_field(c["dimension"])
    if needs_resolution(c) and (resolution is None or resolution.status == "not_needed"):
        resolution = Resolution("unresolved")  # never compare a value that was not resolved
    if filt and not (resolution and resolution.status == "unresolved"):
        field_name = filt["field"]
        if resolution and resolution.status == "resolved":
            value = resolution.values
            operator = "in"
    return RuleCriterion(
        id=c["id"],
        label=c["label"],
        kind=CriterionKind(c["kind"]),
        field=field_name,
        operator=CriterionOperator(operator),
        value=value,
        weight=c.get("weight"),
        dimension=c["dimension"],
    )


def _conditions(filt: Mapping[str, Any], values: list[Any] | None) -> dict[str, Any]:
    fname, ftype, value = filt["field"], filt["type"], filt["value"]
    if values is not None:
        return {"field": fname, "type": "in", "value": values}
    if ftype == "between":
        lo, hi = value
        return {
            "op": "and",
            "conditions": [
                {"field": fname, "type": "=>", "value": lo},
                {"field": fname, "type": "=<", "value": hi},
            ],
        }
    if ftype == "(.)" and isinstance(value, list):
        return {
            "op": "or",
            "conditions": [{"field": fname, "type": "(.)", "value": v} for v in value],
        }
    if ftype == "=" and isinstance(value, list):
        return {"field": fname, "type": "in", "value": value}
    return {"field": fname, "type": ftype, "value": value}


@dataclass
class SearchFilters:
    hard: list[dict[str, Any]] = field(default_factory=list)
    # (strict condition, unknown-inclusive condition) per unreliable must-have
    soft: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # labels not sent to the provider

    def combine(self, *, soft: str = "inclusive") -> dict[str, Any] | None:
        """`soft` = "inclusive" (field matches or is empty), "strict" or "drop"."""
        conditions = list(self.hard)
        if soft == "inclusive":
            conditions += [inc for _, inc in self.soft]
        elif soft == "strict":
            conditions += [strict for strict, _ in self.soft]
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"op": "and", "conditions": conditions}

    @property
    def fields(self) -> set[str]:
        out: set[str] = set()

        def walk(node: Mapping[str, Any]) -> None:
            if "conditions" in node:
                for child in node["conditions"]:
                    walk(child)
            elif "field" in node:
                out.add(node["field"])

        for cond in self.hard:
            walk(cond)
        for strict, _ in self.soft:
            walk(strict)
        return out


def build_filters(
    criteria: Iterable[Mapping[str, Any]], resolutions: Mapping[str, Resolution]
) -> SearchFilters:
    out = SearchFilters()
    for c in criteria:
        filt = c.get("crustdata_filter")
        if c["kind"] != "must" or not filt:
            continue
        res = resolutions.get(c["id"]) or Resolution("not_needed")
        if res.status == "unresolved":
            out.skipped.append(c["label"])
            continue
        cond = _conditions(filt, res.values if res.status == "resolved" else None)
        if filt["field"] in RELIABLE_FILTER_FIELDS:
            out.hard.append(cond)
        else:
            inclusive = {
                "op": "or",
                "conditions": [cond, {"field": filt["field"], "type": "is_null"}],
            }
            out.soft.append((cond, inclusive))
    return out


_STOPWORDS = frozenset(
    "and the for with that which who companies company firms businesses provide "
    "providers provider build building serve serving offer offering their them from "
    "into than this other based".split()
)


def activity_keywords(text: str, limit: int = 4) -> list[str]:
    """Plain words from the activity query, for resolving industry values when
    natural-language search is unavailable."""
    words: list[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text):
        lw = w.lower().strip("-")
        if lw in _STOPWORDS or lw in words:
            continue
        words.append(lw)
        if len(words) >= limit:
            break
    return words
