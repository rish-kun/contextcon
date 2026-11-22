"""Shortlist cards in the API contract's shape (`ShortlistCardOut`), built from
sourced facts only. Headcount and growth are estimates; hiring is a signal."""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.api.schemas.theses import ShortlistCardOut
from app.domain.enums import CriterionResult
from app.domain.types import CandidateAssessment, Criterion
from app.pipelines.discover.records import ESTIMATE_BASIS, SIGNAL_BASIS

NOT_CHECKED_BUDGET = "budget reached"


def _fact(f: dict[str, Any] | None, value: Any = None) -> dict[str, Any] | None:
    if f is None:
        return None
    out = {
        "value": f["value"] if value is None else value,
        "source": f["source"],
        "evidence_id": f["evidence_id"],
        "as_of": f.get("as_of"),
        "is_estimate": bool(f.get("is_estimate")),
        "estimate_kind": f.get("estimate_kind") if f.get("is_estimate") else None,
        "estimate_basis": None,
    }
    if f.get("is_estimate"):
        out["estimate_basis"] = (
            SIGNAL_BASIS if f.get("estimate_kind") == "signal" else ESTIMATE_BASIS
        )
    return out


def _location(facts: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    hq, country = facts.get("locations.headquarters"), facts.get("locations.country")
    if hq is None and country is None:
        return None
    if hq is None:
        return _fact(country, str(country["value"]))
    text = str(hq["value"])
    if (
        country is not None
        and country["source"]["source_id"] == hq["source"]["source_id"]
        and str(country["value"]).casefold() not in text.casefold()
    ):
        text = f"{text}, {country['value']}"  # same source row, so one citation holds
    return _fact(hq, text)


def _business(facts: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key in ("description", "taxonomy.professional_network_industry"):
        if key in facts:
            return _fact(facts[key], str(facts[key]["value"]))
    if "basic_info.industries" in facts:
        return _fact(
            facts["basic_info.industries"], ", ".join(facts["basic_info.industries"]["value"])
        )
    return None


def _number(f: dict[str, Any] | None, cast: type) -> dict[str, Any] | None:
    if f is None:
        return None
    try:
        return _fact(f, cast(f["value"]))
    except (TypeError, ValueError):
        return None


def _series(f: dict[str, Any] | None) -> dict[str, Any] | None:
    """The provider's dated headcount points. Always an estimate; never interpolated."""
    if f is None or not isinstance(f.get("value"), list) or len(f["value"]) < 2:
        return None
    return {"points": f["value"], "source": f["source"], "estimate_basis": ESTIMATE_BASIS}


def met_reasons(criteria: list[Criterion], assessment: CandidateAssessment) -> list[dict[str, Any]]:
    """Deterministic reasons: the criteria met, each with its evidence."""
    labels = {c.id: c.label for c in criteria}
    return [
        {
            "text": f"Meets: {labels[e.criterion_id]}",
            "criterion_id": e.criterion_id,
            "evidence_ids": list(e.evidence_ids),
        }
        for e in assessment.fit.evaluations
        if e.result is CriterionResult.PASS
    ]


def unknowns(
    criteria: list[Criterion],
    assessment: CandidateAssessment,
    facts: dict[str, dict[str, Any]],
    *,
    enriched: bool,
    not_enriched_reason: str | None,
    rounds: list[dict[str, Any]],
    hiring_note: str | None,
) -> list[str]:
    by_id = {c.id: c for c in criteria}
    out: list[str] = []
    for e in assessment.fit.evaluations:
        if e.result is not CriterionResult.UNKNOWN:
            continue
        c = by_id[e.criterion_id]
        if c.field.startswith("evidence:"):
            out.append(f"{c.label}: not checked in discovery; assessed from evidence in a case")
        else:
            out.append(f"{c.label}: not known ({e.reason})")
    if not enriched:
        reason = not_enriched_reason or "not enriched"
        out.append(f"Funding, headcount and hiring: not checked ({reason})")
    else:
        if "headcount.total" not in facts:
            out.append("Headcount: no estimate recorded by Crustdata")
        if not rounds:
            out.append("Funding history: no dated funding rounds recorded by Crustdata")
        if hiring_note:
            out.append(f"Hiring postings: {hiring_note}")
    return out


def build_card(
    facts: dict[str, dict[str, Any]],
    *,
    rounds: list[dict[str, Any]],
    postings: list[dict[str, Any]],
    reasons: list[dict[str, Any]],
    unknown_items: list[str],
) -> dict[str, Any]:
    retrieved = [
        f["source"]["retrieved_at"]
        for f in [*facts.values(), *rounds, *postings]
        if f.get("source")
    ]
    last_updated = max(retrieved) if retrieved else dt.datetime.now(dt.UTC).isoformat()
    openings = _number(facts.get("hiring.openings_count"), int)
    titles = _fact(facts.get("hiring.recent_titles"))
    hiring = None
    if openings or titles or postings:
        hiring = {
            "openings": openings,
            "recent_titles": titles,
            "postings": [
                {
                    "title": p["value"]["title"],
                    "date_added": p["value"].get("date_added"),
                    "url": p["value"].get("url"),
                    "location": p["value"].get("location"),
                    "source": p["source"],
                }
                for p in postings
            ],
        }
    card = {
        "business": _business(facts),
        "location": _location(facts),
        "headcount": _number(facts.get("headcount.total"), int),
        "headcount_growth_yoy_pct": _number(facts.get("headcount.growth_percent.12m"), float),
        "headcount_series": _series(facts.get("headcount.timeseries")),
        "total_funding_usd": _number(facts.get("funding.total_investment_usd"), float),
        "funding_rounds": [
            {
                "round_type": r["value"].get("round_type"),
                "date": r["value"].get("date"),
                "amount_usd": r["value"].get("amount_usd"),
                "investors": r["value"].get("investors") or [],
                "source": r["source"],
                "evidence_id": r["evidence_id"],
            }
            for r in rounds
        ],
        "hiring": hiring,
        "reasons": reasons,
        "unknowns": unknown_items,
        "last_updated": last_updated,
    }
    # Validate against the contract so a stored card always renders.
    return ShortlistCardOut.model_validate(card).model_dump(mode="json")
