"""Discover's live activity: candidates found, dropped, enriched, scored and explained.

Item ids are the candidate row ids (`candidate_id`), which are derived from the
discovery run and the Crustdata company id, so every stage, and the shortlist the
client loads afterwards, names the same row. Public Crustdata fields and the user's
own criteria only. Fire-and-forget: the emitter never raises.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.jobs import StepContext
from app.jobs.activity import ITEMS_MAX, Subject, _round_words, clean_text, render
from app.pipelines.discover import records

_NS = uuid.UUID("6f1d0a52-4f0e-4b8e-9a35-1c0de5c0ffee")


def candidate_id(discovery_run_id: uuid.UUID | str, crustdata_company_id: Any) -> uuid.UUID:
    """The candidate row id for a company in a discovery run (stable across stages)."""
    return uuid.uuid5(_NS, f"{discovery_run_id}:{crustdata_company_id}")


def _headcount(company: dict[str, Any]) -> int | None:
    value = (company.get("headcount") or {}).get("total")
    if value is None:
        value = (company.get("basic_info") or {}).get("employee_count")
    return value if isinstance(value, int) else None


def _location(company: dict[str, Any]) -> str | None:
    loc = company.get("locations") or {}
    return clean_text(loc.get("headquarters") or loc.get("country"), 80)


def found_item(dr_id: uuid.UUID, company: dict[str, Any]) -> dict[str, Any]:
    cid = records.company_id(company)
    headcount = _headcount(company)
    return {
        "id": str(candidate_id(dr_id, cid)),
        "stage": "found",
        "name": clean_text(records.company_name(company), 80),
        "domain": records.company_domain(company),
        "location": _location(company),
        "headcount": headcount,
        "headcount_is_estimate": True if headcount is not None else None,
    }


def counts(
    found: int, dropped: int = 0, enriched: int = 0, scored: int = 0, in_play: int | None = None
) -> dict[str, int]:
    return {
        "found": found,
        "in_play": found - dropped if in_play is None else in_play,
        "dropped": dropped,
        "enriched": enriched,
        "scored": scored,
    }


async def found(
    ctx: StepContext, dr_id: uuid.UUID, companies: list[dict[str, Any]], pass_: str, total: int
) -> None:
    items = [found_item(dr_id, c) for c in companies if records.company_id(c) is not None]
    if not items:
        return
    await ctx.activity.findings(
        lambda batch: render("finding.found_companies", n=len(batch)),
        subject=Subject.COMPANY,
        items=items,
        counts=counts(total),
        detail=render("finding.pass", pass_=pass_),
    )


async def dropped(ctx: StepContext, dr_id: uuid.UUID, gate: dict[str, Any]) -> None:
    candidates = gate["candidates"]
    names = {c["crustdata_company_id"]: c["name"] for c in candidates}
    items = [
        {
            "id": str(candidate_id(dr_id, d["crustdata_company_id"])),
            "stage": "dropped",
            "name": clean_text(d["name"], 80),
            "reason": clean_text(f"Duplicate of {names.get(d['same_as'], 'another result')}", 120),
        }
        for d in gate["duplicates"]
    ]
    excluded = [c for c in candidates if c["excluded"]]
    items += [
        {
            "id": str(candidate_id(dr_id, c["crustdata_company_id"])),
            "stage": "dropped",
            "name": clean_text(c["name"], 80),
            "reason": clean_text(
                "Failed must-have: " + "; ".join(c["exclusion_reasons"] or ["a criterion"]), 120
            ),
        }
        for c in excluded
    ]
    total = len(candidates) + len(gate["duplicates"])
    n = len(items)
    await ctx.activity.finding(
        render("finding.dropped_companies", n=n),
        subject=Subject.COMPANY,
        items=items[:ITEMS_MAX],
        counts=counts(total, dropped=n),
        detail=render("finding.dropped_detail", n=len(gate["duplicates"]), m=len(excluded)),
    )


def _mark(value: Any) -> str:
    return "found" if value else "none"


async def enriched(
    ctx: StepContext,
    dr_id: uuid.UUID,
    gate: dict[str, Any],
    enriched_by_id: dict[str, dict[str, Any]],
    jobs: dict[str, Any],
    jobs_not_checked: dict[str, str],
) -> None:
    names = {str(c["crustdata_company_id"]): c["name"] for c in gate.get("candidates") or []}
    total = len(gate.get("candidates") or []) + len(gate.get("duplicates") or [])
    dropped_n = total - len(gate.get("survivors") or [])
    events = []
    for i, (cid, data) in enumerate(enriched_by_id.items(), start=1):
        funding = data.get("funding") or {}
        hiring = (
            "not_checked"
            if cid in jobs_not_checked
            else _mark((jobs.get(cid) or {}).get("listings"))
        )
        highlight = clean_text(_round_words(data), 100)
        name = names.get(cid) or (data.get("basic_info") or {}).get("name")
        events.append(
            (
                render("finding.enriched_company", name=name or "a company"),
                {
                    "id": str(candidate_id(dr_id, cid)),
                    "stage": "enriched",
                    "name": clean_text(name, 80),
                    "marks": {
                        "funding": _mark(funding.get("milestones") or funding.get("investors")),
                        "headcount": _mark((data.get("headcount") or {}).get("timeseries")),
                        "hiring": hiring,
                    },
                    "highlight": highlight,
                },
                counts(total, dropped=dropped_n, enriched=i),
            )
        )
    for label, item, c in events:
        await ctx.activity.finding(label, subject=Subject.COMPANY, items=[item], counts=c)


async def scored(
    ctx: StepContext, dr_id: uuid.UUID, ranked: list[Any], found_n: int, dropped_n: int
) -> None:
    items = [
        {
            "id": str(candidate_id(dr_id, a.entity_id)),
            "stage": "scored",
            "name": clean_text(a.name, 80),
            "fit": a.fit.fit,
            "assessable": round(a.fit.assessable_pct / 100, 3),
            "rank": rank,
        }
        for rank, a in enumerate(ranked, start=1)
    ]
    if not items:
        return
    await ctx.activity.findings(
        lambda _batch: render("finding.ranked_companies", n=len(items)),
        subject=Subject.COMPANY,
        items=items,
        counts=counts(found_n, dropped=dropped_n, enriched=len(items), scored=len(items)),
    )
