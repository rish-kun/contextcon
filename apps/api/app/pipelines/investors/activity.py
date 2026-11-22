"""Investor search's live activity: comparables found, funding rounds read per company,
investors ranked. Public Crustdata records only. Fire-and-forget."""

from __future__ import annotations

from typing import Any

from app.jobs import StepContext
from app.jobs.activity import ITEMS_MAX, Subject, clean_text, render
from app.rules.investors import normalize_name


def investor_key(investor: dict[str, Any]) -> str:
    """The grouping key the ranking will use when it can tell already: the provider's
    investor id, else the normalised name (the rank event has the final keys)."""
    if investor.get("uuid"):
        return f"id:{investor['uuid']}"
    return f"name:{normalize_name(investor.get('name') or '')}"


async def comparables_found(ctx: StepContext, companies: list[dict[str, Any]]) -> None:
    items = [
        {
            "id": str(c["company_id"]),
            "stage": "found",
            "name": clean_text(c.get("name"), 80),
            "domain": c.get("domain"),
            "location": clean_text(c.get("headquarters") or c.get("country"), 80),
        }
        for c in companies
        if c.get("company_id") is not None
    ]
    if not items:
        return
    n = len(items)
    await ctx.activity.findings(
        lambda _batch: render("finding.found_companies", n=n),
        subject=Subject.COMPANY,
        items=items,
        counts={"found": n, "in_play": n, "dropped": 0, "enriched": 0, "scored": 0},
    )


async def rounds_read(ctx: StepContext, companies: list[dict[str, Any]]) -> None:
    """One `round` finding per company, with running totals."""
    rounds = dated = 0
    investors: set[str] = set()
    total = len(companies)
    for i, company in enumerate(companies, start=1):
        items = []
        for r in company.get("rounds") or []:
            people = [
                {"key": investor_key(inv), "name": clean_text(inv.get("name"), 80) or ""}
                for inv in r.get("investors") or []
                if inv.get("name")
            ]
            investors.update(p["key"] for p in people)
            rounds += 1
            dated += int(bool(r.get("date")))
            items.append(
                {
                    "id": f"{company['company_id']}:{r.get('index', len(items))}",
                    "stage": "found",
                    "company": clean_text(company.get("name"), 80),
                    "company_id": str(company["company_id"]),
                    "round": (r.get("round_type") or "").replace("_", " ").title() or None,
                    "date": r.get("date"),
                    "amount_usd": r.get("amount_usd"),
                    "investors": people,
                }
            )
        await ctx.activity.finding(
            render("finding.rounds_of", n=len(items), name=company.get("name") or "a company"),
            subject=Subject.ROUND,
            items=items[:ITEMS_MAX],
            counts={
                "companies": total,
                "rounds": rounds,
                "rounds_dated": dated,
                "investors": len(investors),
            },
            progress=(i, total),
        )


async def ranked(ctx: StepContext, ranking: Any) -> None:
    items = []
    for rank, inv in enumerate(ranking.investors, start=1):
        dates = [r.date for r in inv.comparable_rounds if getattr(r, "date", None)]
        items.append(
            {
                "id": inv.key,
                "stage": "ranked",
                "name": clean_text(inv.name, 80) or inv.key,
                "rank": rank,
                "comparable_rounds": inv.comparable_count,
                "last_round_date": max(dates).isoformat() if dates else None,
            }
        )
    n = len(items)
    await ctx.activity.findings(
        lambda _batch: render("finding.ranked_investors", n=n),
        subject=Subject.INVESTOR,
        items=items,
        counts={"investors": n, "ranked": n, "not_ranked": len(ranking.excluded_records)},
    )
