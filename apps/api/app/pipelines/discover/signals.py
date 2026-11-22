"""Derived Discover signals for criteria with no provider field.

- Activity / sector (`industry_activity`): matched against the company's own
  description, industries and categories. Pass on clear textual evidence (quoted);
  fail only when a long description never mentions the activity; else unknown.
- Recent expansion (`growth_signal`): a SIGNAL from the headcount series (growth
  over ~12 months), open roles and dated postings. Never confirmed expansion.

Every derived result is an estimate, so a derived fail never excludes a company.
Thresholds live in `app.rules.policy` (POLICY.md section 1).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import CriterionOperator
from app.domain.types import Criterion
from app.rules import policy

DERIVED_DIMENSIONS = frozenset({"industry_activity", "growth_signal"})

_STOP = frozenset(
    "and or the of for in to a an with that which who companies company firms businesses "
    "providers provider solutions based serve serving offer offering build building".split()
)
_TYPE_WORDS = frozenset({"software", "saas", "platform", "platforms", "technology", "tech", "app"})
_TYPE_SYNONYMS = (
    r"software|saas|platforms?|cloud|apps?|applications?|technology|tech|erp|wms|tms|systems?"
)
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "supply chain": ("logistics", "scm"),
    "logistics": ("supply chain",),
    "warehousing": ("fulfilment", "fulfillment"),
}


def signal_key(criterion_id: str) -> str:
    return f"signal:{criterion_id}"


def signal_criterion(c: Criterion) -> Criterion:
    """An unmapped activity or growth criterion reads its derived signal."""
    if not c.field.startswith("evidence:") or c.dimension not in DERIVED_DIMENSIONS:
        return c
    return c.model_copy(
        update={"field": signal_key(c.id), "operator": CriterionOperator.IS_TRUE, "value": True}
    )


@dataclass
class Derived:
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)

    @property
    def sourced(self) -> int:
        return sum(1 for f in self.facts.values() if f.get("evidence_id"))


# --- Activity --------------------------------------------------------------------


def _stem(word: str) -> str:
    return word if len(word) <= 5 else word[: max(5, len(word) - 3)]


def _term_pattern(term: str) -> str:
    return r"\b" + r"[\s\-]+".join(_stem(w) + r"[a-z]*" for w in term.split()) + r"\b"


def activity_terms(text: str) -> tuple[list[str], bool]:
    """(domain terms, whether the phrase names a product type such as software)."""
    words = re.findall(r"[a-z0-9&]+", text.lower().replace("-", " "))
    terms: list[str] = []
    run: list[str] = []
    has_type = False
    for w in [*words, ""]:
        if w in _TYPE_WORDS:
            has_type = True
        if w and w not in _STOP and w not in _TYPE_WORDS and len(w) > 2:
            run.append(w)
            continue
        if run:
            t = " ".join(run)
            if t not in terms:
                terms.append(t)
            run = []
    return terms, has_type


def _sentence(text: str, start: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(". ", start), text.find("\n", start)) if i >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 if left >= 0 else 0 : right + 1].strip()


_TEXT_KEYS = (
    "description",
    "basic_info.industries",
    "taxonomy.professional_network_industry",
    "taxonomy.categories",
)


def _texts(facts: dict[str, dict[str, Any]]) -> list[tuple[str, str, dict[str, Any]]]:
    out = []
    for key in _TEXT_KEYS:
        f = facts.get(key)
        if not f or f.get("value") in (None, "", []):
            continue
        v = f["value"]
        out.append((key, ", ".join(map(str, v)) if isinstance(v, list) else str(v), f))
    return out


def assess_activity(
    criterion: dict[str, Any], facts: dict[str, dict[str, Any]]
) -> tuple[bool | None, str, list[str]]:
    phrase = " ".join(
        str(v)
        for v in [criterion.get("label"), *_as_list(criterion.get("value"))]
        if v not in (None, "")
    )
    terms, has_type = activity_terms(phrase)
    texts = _texts(facts)
    searched = "searched: Crustdata description, industries and categories"
    if not terms or not texts:
        return None, f"Unknown; {searched} (no record)", []
    domain_hit: tuple[str, str, dict[str, Any], int] | None = None
    for term in terms:
        for alt in (term, *_SYNONYMS.get(term, ())):
            pat = re.compile(_term_pattern(alt), re.IGNORECASE)
            for key, text, f in texts:
                m = pat.search(text)
                if m and domain_hit is None:
                    domain_hit = (key, text, f, m.start())
    type_hit = None
    if has_type:
        tp = re.compile(rf"\b(?:{_TYPE_SYNONYMS})\b", re.IGNORECASE)
        type_hit = next(((k, t, f) for k, t, f in texts if tp.search(t)), None)
    if domain_hit and (not has_type or type_hit):
        key, text, f, start = domain_hit
        quote = _sentence(text, start) if key == "description" else text
        ids = [f["evidence_id"]]
        if type_hit and type_hit[2]["evidence_id"] not in ids:
            ids.append(type_hit[2]["evidence_id"])
        label = "description" if key == "description" else key.split(".")[-1]
        return True, f'Text match in the Crustdata {label}: "{quote[:240]}"', ids
    desc = facts.get("description")
    words = len(str(desc["value"]).split()) if desc else 0
    if domain_hit is None and words >= policy.ACTIVITY_CONTRADICTION_MIN_WORDS:
        return (
            False,
            f"The Crustdata description ({words} words) never mentions "
            f"{' or '.join(terms)}; text match, an estimate",
            [desc["evidence_id"]],
        )
    if domain_hit is not None:
        return None, f"Unknown; mentions {terms[0]} but not the product type; {searched}", []
    return None, f"Unknown; {searched}: too little text to judge", []


def _as_list(v: Any) -> list[Any]:
    return list(v) if isinstance(v, list | tuple) else [v]


# --- Expansion -------------------------------------------------------------------


def _growth(facts: dict[str, dict[str, Any]]) -> tuple[float, str, dict[str, Any]] | None:
    series = facts.get("headcount.timeseries")
    if series and isinstance(series.get("value"), list) and len(series["value"]) >= 2:
        pts = [
            (dt.date.fromisoformat(p["date"][:10]), p["employee_count"])
            for p in series["value"]
            if p.get("date") and p.get("employee_count")
        ]
        if pts:
            last_d, last_n = max(pts)
            target = last_d - dt.timedelta(days=policy.EXPANSION_GROWTH_WINDOW_DAYS)
            near = min(pts, key=lambda p: abs((p[0] - target).days))
            ok = abs((near[0] - target).days) <= policy.EXPANSION_WINDOW_TOLERANCE_DAYS
            if ok and near[1] and near[0] < last_d:
                g = 100 * (last_n - near[1]) / near[1]
                text = f"headcount {near[1]} → {last_n} ({g:+.0f}%) {near[0]} to {last_d}"
                return g, text, series
    yoy = facts.get("headcount.growth_percent.12m")
    if yoy is not None:
        try:
            g = float(yoy["value"])
        except (TypeError, ValueError):
            return None
        return g, f"headcount growth over 12 months {g:+.0f}%", yoy
    return None


def assess_expansion(
    facts: dict[str, dict[str, Any]],
    postings: list[dict[str, Any]],
    *,
    enriched: bool,
    today: dt.date | None = None,
) -> tuple[bool | None, str, list[str]]:
    today = today or dt.date.today()
    positive: list[str] = []
    negative: list[str] = []
    ids: list[str] = []
    growth = _growth(facts)
    if growth is not None:
        g, text, f = growth
        ids.append(f["evidence_id"])
        (positive if g >= policy.EXPANSION_MIN_HEADCOUNT_GROWTH_PCT else negative).append(text)
    roles_known = False
    openings = facts.get("hiring.openings_count")
    cutoff = today - dt.timedelta(days=policy.EXPANSION_POSTING_WINDOW_DAYS)
    recent = [
        p
        for p in postings
        if (p.get("value") or {}).get("date_added")
        and p["value"]["date_added"] >= cutoff.isoformat()
    ]
    n_roles = None
    if openings is not None:
        try:
            n_roles = int(openings["value"])
            roles_known = True
            ids.append(openings["evidence_id"])
        except (TypeError, ValueError):
            pass
    if len(recent) > (n_roles or 0):
        n_roles = len(recent)
        roles_known = True
        ids += [p["evidence_id"] for p in recent]
    if roles_known:
        text = f"{n_roles} open roles"
        (positive if n_roles >= policy.EXPANSION_MIN_OPEN_ROLES else negative).append(text)
    label = "Signal from profile headcount and job postings, not confirmed expansion"
    if positive:
        return True, f"{label}: " + "; ".join(positive), ids
    if growth is not None and roles_known:
        return False, f"{label}: " + "; ".join(negative) + " (below the thresholds)", ids
    missing = [
        n
        for n, ok in (("headcount series", growth is not None), ("open roles", roles_known))
        if not ok
    ]
    if not enriched:
        return None, "Unknown; not enriched, so headcount and hiring were not checked", []
    return (
        None,
        "Unknown; searched Crustdata headcount and job postings: no " + ", ".join(missing),
        [],
    )


# --- Derive ----------------------------------------------------------------------


def derive(
    criteria: list[dict[str, Any]],
    rule_criteria: list[Criterion],
    facts: dict[str, dict[str, Any]],
    *,
    postings: list[dict[str, Any]] | None = None,
    enriched: bool = False,
    today: dt.date | None = None,
) -> Derived:
    out = Derived()
    stored = {c["id"]: c for c in criteria}
    for rc in rule_criteria:
        if not rc.field.startswith("signal:"):
            continue
        if rc.dimension == "industry_activity":
            result, reason, ids = assess_activity(stored.get(rc.id, {}), facts)
        else:
            result, reason, ids = assess_expansion(
                facts, postings or [], enriched=enriched, today=today
            )
        ids = [i for i in dict.fromkeys(ids) if i]
        out.reasons[rc.id] = reason
        out.evidence[rc.id] = ids
        if result is not None:
            out.facts[rc.field] = {
                "value": result,
                "evidence_id": ids[0] if ids else None,
                "as_of": None,
                "is_estimate": True,
                "estimate_kind": "signal",
            }
    return out


def sourced_signals(
    facts: dict[str, dict[str, Any]],
    rounds: list[dict[str, Any]],
    postings: list[dict[str, Any]],
    derived: Derived,
) -> int:
    """Tie-break count: sourced signal fields, dated rounds, dated postings, derived."""
    n = sum(1 for k in policy.DISCOVER_SIGNAL_KEYS if (facts.get(k) or {}).get("evidence_id"))
    n += int(bool(rounds)) + int(any((p.get("value") or {}).get("date_added") for p in postings))
    return n + derived.sourced
