"""Investor discovery steps (design §6.2, plan CP-18).

    investors.spec         profile → comparable-company search (LLM, no credits)
    investors.comparables  company_search: comparable companies that have raised money
    investors.enrich       company_enrich (one call, ≤25 ids, within budget): dated rounds
    investors.rank         keep dated, named rounds → rank_investors → investor_entries

Only company endpoints are called; person and contact endpoints never are. Every paid
call goes through `ctx.recorder` / `ctx.cache`, so its cost lands on the investor run
and a re-run replays from the cache.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections import Counter
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import delete

from app.clients.crustdata import MAX_ENRICH_IDS, CrustdataClient
from app.db.models import Evidence, InvestorEntry, InvestorRun, Source
from app.domain.enums import Compatibility, FundingKind
from app.domain.types import RankedInvestor, SearchScope
from app.extraction.investors import BusinessProfile, extract_investor_spec
from app.extraction.llm import StructuredLlm
from app.jobs import BudgetExceeded, StepContext, StepSpec, step_handler
from app.pipelines.investors.ingest import (
    ScrubbingCache,
    compact_company,
    funding_records,
    has_dated_rounds,
)
from app.pipelines.investors.profile import KIND_LABELS, SearchPlan, build_plan
from app.rules import policy
from app.rules.compare import normalize_text
from app.rules.investors import funding_kind, rank_investors
from app.settings import get_settings

log = logging.getLogger(__name__)

SPEC, COMPARABLES, ENRICH, RANK = (
    "investors.spec",
    "investors.comparables",
    "investors.enrich",
    "investors.rank",
)

DEFAULT_SEARCH_LIMIT = 40
DEFAULT_ENRICH_LIMIT = MAX_ENRICH_IDS
MIN_COMPARABLES = 8
# company_search: 0.03 base + 0.2 for filtering on the funding group, per result.
SEARCH_CREDITS_PER_RESULT = Decimal("0.23")
ENRICH_CREDITS_PER_MATCH = Decimal("2")
SEARCH_FIELDS = ("crustdata_company_id", "basic_info", "locations")
ENRICH_FIELDS = ("basic_info", "funding", "locations", "taxonomy")
SOURCE_CLASS = "data_provider"

_NS = uuid.UUID("5b0c8f4e-6f1d-4a57-9d43-2f1b8e7c9a10")


def stable_id(*parts: object) -> uuid.UUID:
    """Deterministic row id, so a re-run upserts instead of duplicating."""
    return uuid.uuid5(_NS, ":".join(str(p) for p in parts))


# --- Clients (swappable in tests) ------------------------------------------------


class ClientFactory(Protocol):
    def crustdata(self, *, recorder: Any, cache: Any) -> CrustdataClient: ...

    def llm(self, ctx: StepContext) -> StructuredLlm | None: ...


class SettingsClients:
    def crustdata(self, *, recorder: Any, cache: Any) -> CrustdataClient:
        return CrustdataClient.from_settings(recorder=recorder, cache=cache)

    def llm(self, ctx: StepContext) -> StructuredLlm | None:
        if not get_settings().anthropic_api_key.get_secret_value():
            return None
        from app.clients.llm import LLMClient

        return LLMClient.from_settings(recorder=ctx.recorder, cache=ctx.cache)


clients: ClientFactory = SettingsClients()


def _crustdata(ctx: StepContext) -> CrustdataClient:
    cache = ScrubbingCache(ctx.cache) if ctx.cache is not None else None
    return clients.crustdata(recorder=ctx.recorder, cache=cache)


def step_specs(*, search_limit: int | None = None, enrich_limit: int | None = None) -> list:
    limits = {
        "search_limit": search_limit or DEFAULT_SEARCH_LIMIT,
        "enrich_limit": min(enrich_limit or DEFAULT_ENRICH_LIMIT, MAX_ENRICH_IDS),
    }
    return [
        StepSpec(SPEC, SPEC, label="Read the business profile", uses_budget=False),
        StepSpec(
            COMPARABLES,
            COMPARABLES,
            label="Find comparable companies that raised money",
            input=limits,
            depends_on=[SPEC],
        ),
        StepSpec(
            ENRICH,
            ENRICH,
            label="Read dated funding rounds",
            input=limits,
            depends_on=[COMPARABLES],
        ),
        StepSpec(
            RANK,
            RANK,
            label="Group investors and rank by comparable rounds",
            depends_on=[SPEC, COMPARABLES, ENRICH],
            uses_budget=False,
            tolerate_failed_deps=True,
        ),
    ]


# --- Helpers ------------------------------------------------------------------------


async def _investor_run(ctx: StepContext) -> InvestorRun:
    if ctx.run.investor_run_id is None:
        raise RuntimeError("investor step outside an investor run")
    row = await ctx.session.get(InvestorRun, ctx.run.investor_run_id)
    if row is None:
        raise RuntimeError("investor run not found")
    return row


def _profile(row: InvestorRun) -> dict[str, Any]:
    keys = ("sector", "location", "stage", "size", "funding_sought")
    return {k: str((row.profile or {}).get(k) or "") for k in keys}


def _output(ctx: StepContext, key: str) -> dict[str, Any] | None:
    dep = ctx.dependencies.get(key) or {}
    return dep.get("output") if dep.get("state") == "done" else None


def plan_from(data: dict[str, Any]) -> SearchPlan:
    kind = data.get("kind_sought")
    return SearchPlan(**{**data, "kind_sought": FundingKind(kind) if kind else None})


def plan_to_json(plan: SearchPlan) -> dict[str, Any]:
    return {
        "query": plan.query,
        "country": plan.country,
        "employee_bands": plan.employee_bands,
        "round_types": plan.round_types,
        "sector_keywords": plan.sector_keywords,
        "kind_sought": plan.kind_sought.value if plan.kind_sought else None,
    }


def _matches_sector(company: dict[str, Any], keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = normalize_text(
        " ".join(
            [company.get("description") or "", " ".join(company.get("markets") or [])]
            + company.get("sectors", [])
        )
    )
    return any(normalize_text(k) in text for k in keywords)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- Steps ------------------------------------------------------------------------


@step_handler(SPEC)
async def spec_step(ctx: StepContext) -> dict[str, Any]:
    """Profile → comparable-company criteria. Falls back to the form fields alone when
    the model is unavailable, and says so."""
    row = await _investor_run(ctx)
    profile = _profile(row)
    spec: dict[str, Any] = {}
    source, error = "profile_only", None
    llm = clients.llm(ctx)
    if llm is not None:
        try:
            extracted = await extract_investor_spec(llm, BusinessProfile(**profile))
            spec = extracted.model_dump(mode="json", exclude={"calls"})
            source = "model"
        except Exception as exc:  # noqa: BLE001 - the form fields still define the search
            error = type(exc).__name__
            log.warning("investor spec extraction failed (%s); using the form fields", error)
        finally:
            close = getattr(llm, "aclose", None)
            if close is not None:
                await close()
    plan = build_plan(profile, spec)
    ctx.result = f"Comparables: {plan.query} ({plan.describe()})"
    return {"spec": spec, "spec_source": source, "spec_error": error, "plan": plan_to_json(plan)}


@step_handler(COMPARABLES)
async def comparables_step(ctx: StepContext) -> dict[str, Any]:
    spec_out = _output(ctx, SPEC)
    if spec_out is None:
        raise RuntimeError("spec step has no output")
    plan = plan_from(spec_out["plan"])
    limit = int(ctx.input.get("search_limit") or DEFAULT_SEARCH_LIMIT)
    await ctx.require_budget(SEARCH_CREDITS_PER_RESULT * limit)
    await ctx.set_detail(f"Searching: {plan.query}")

    searches: list[dict[str, Any]] = []
    found: dict[int, dict[str, Any]] = {}
    searched_at = _utcnow()
    client = _crustdata(ctx)
    try:
        for with_size in (True, False):
            if not with_size and (not plan.employee_bands or len(found) >= MIN_COMPARABLES):
                break
            want = limit - len(found)
            if want <= 0:
                break
            if not with_size:
                await ctx.require_budget(SEARCH_CREDITS_PER_RESULT * want)
            result, _ = await client.search_companies(
                filters=plan.filters(with_size=with_size),
                query=plan.query or None,
                limit=want,
                fields=list(SEARCH_FIELDS),
                fallback_to_filters=True,
            )
            kept = 0
            for raw in result.companies:
                company = compact_company(raw)
                cid = company["company_id"]
                if cid is None or cid in found:
                    continue
                info = raw.basic_info
                company["description"] = info.description if info else None
                company["markets"] = (info.markets or []) if info else []
                # Without natural-language ranking only the filters constrain the
                # search, so check the sector words against what the company does.
                if not result.natural_language and not _matches_sector(
                    company, plan.sector_keywords
                ):
                    continue
                company["needs_enrich"] = not has_dated_rounds(raw)
                found[cid] = company
                kept += 1
            searches.append(
                {
                    "scope": plan.describe(with_size=with_size),
                    "natural_language": result.natural_language,
                    "returned": len(result.companies),
                    "kept": kept,
                }
            )
    finally:
        await client.aclose()

    companies = list(found.values())
    for c in companies:
        c.pop("description", None)
        c.pop("markets", None)
        if c["needs_enrich"]:
            c["rounds"] = []
    widened = len(searches) > 1
    ctx.result = f"{len(companies)} comparable companies found" + (
        " (widened beyond the size band)" if widened else ""
    )
    return {
        "companies": companies,
        "searches": searches,
        "searched_at": searched_at.isoformat(),
        "natural_language": any(s["natural_language"] for s in searches),
    }


async def _store_rounds(
    ctx: StepContext,
    company: dict[str, Any],
    *,
    endpoint: str,
    request: dict[str, Any],
    retrieved_at: dt.datetime,
) -> None:
    """One source per company record; one evidence row per funding round."""
    cid = company["company_id"]
    source_id = stable_id(ctx.run.id, "source", endpoint, cid)
    if await ctx.session.get(Source, source_id) is None:
        ctx.session.add(
            Source(
                id=source_id,
                workspace_id=ctx.run.workspace_id,
                run_id=ctx.run.id,
                provider="crustdata",
                endpoint_or_url=endpoint,
                request=request,
                retrieved_at=retrieved_at,
                source_class=SOURCE_CLASS,
                title=f"{company['name']}: funding rounds",
                publisher="Crustdata",
            )
        )
    for r in company["rounds"]:
        origin = f"crustdata:{endpoint.strip('/')}:{cid}:funding.milestones[{r['index']}]"
        evidence_id = stable_id(ctx.run.id, "evidence", origin)
        if await ctx.session.get(Evidence, evidence_id) is None:
            ctx.session.add(
                Evidence(
                    id=evidence_id,
                    source_id=source_id,
                    entity_ref=f"crustdata_company:{cid}",
                    identity_confidence=1.0,
                    field_path=f"funding.milestones[{r['index']}]",
                    value={k: v for k, v in r.items() if k != "index"},
                    as_of=dt.date.fromisoformat(r["date"]) if r["date"] else None,
                    origin_key=origin,
                )
            )
        r["evidence_id"] = str(evidence_id)
        r["source_id"] = str(source_id)
        r["retrieved_at"] = retrieved_at.isoformat()


@step_handler(ENRICH)
async def enrich_step(ctx: StepContext) -> dict[str, Any]:
    comps = _output(ctx, COMPARABLES)
    if comps is None:
        raise RuntimeError("comparables step has no output")
    limit = min(int(ctx.input.get("enrich_limit") or DEFAULT_ENRICH_LIMIT), MAX_ENRICH_IDS)
    companies = comps["companies"]
    searched_at = dt.datetime.fromisoformat(comps["searched_at"])
    ready = [c for c in companies if not c.get("needs_enrich", True)]
    need = [c for c in companies if c.get("needs_enrich", True)][:limit]
    beyond_limit = sum(1 for c in companies if c.get("needs_enrich", True)) - len(need)

    remaining = await ctx.budget_remaining()
    affordable = len(need) if remaining is None else int(remaining // ENRICH_CREDITS_PER_MATCH)
    take = need[: max(0, affordable)]
    if need and not take:
        raise BudgetExceeded()
    budget_short = len(need) - len(take)

    out: list[dict[str, Any]] = []
    for c in ready:
        await _store_rounds(
            ctx,
            c,
            endpoint="/company/search",
            request={"crustdata_company_id": c["company_id"]},
            retrieved_at=searched_at,
        )
        out.append(c)

    if take:
        ids = [int(c["company_id"]) for c in take]
        await ctx.set_detail(f"Reading funding rounds of {len(ids)} companies")
        client = _crustdata(ctx)
        try:
            results, record = await client.enrich_company(ids, fields=ENRICH_FIELDS)
        finally:
            await client.aclose()
        retrieved_at = record.finished_at or record.started_at
        wanted = set(ids)
        for result in results:
            for match in result.matches:
                company = compact_company(match.company_data)
                cid = company["company_id"]
                # Identity guard: a record attaches only by the Crustdata id we asked for.
                if cid not in wanted:
                    continue
                wanted.discard(cid)
                await _store_rounds(
                    ctx,
                    company,
                    endpoint="/company/enrich",
                    request={"crustdata_company_ids": [cid], "fields": list(ENRICH_FIELDS)},
                    retrieved_at=retrieved_at,
                )
                out.append(company)

    rounds = sum(len(c["rounds"]) for c in out)
    ctx.result = f"{rounds} funding rounds read from {len(out)} companies"
    if budget_short:
        ctx.result += f"; {budget_short} not read: budget reached"
    return {
        "companies": out,
        "enriched": len(take),
        "not_read_budget": budget_short,
        "not_read_limit": beyond_limit,
    }


def _compatibility_text(inv: RankedInvestor, sought: FundingKind | None) -> str:
    if sought is None:
        return "Funding kind sought not stated; compatibility unknown"
    label = KIND_LABELS[sought]
    if inv.compatibility == Compatibility.COMPATIBLE:
        matching = [r for r in inv.comparable_rounds if funding_kind(r.round_type) == sought]
        if matching:
            latest = max(r.date for r in matching)
            n = len(matching)
            return f"{n} {label} round{'s' if n != 1 else ''} in the record, latest {latest:%Y-%m}"
        return f"Has made {label} investments in the record"
    if inv.compatibility == Compatibility.INCOMPATIBLE:
        kinds = Counter(
            KIND_LABELS[k]
            for k in (funding_kind(r.round_type) for r in inv.comparable_rounds)
            if k is not None
        )
        seen = ", ".join(f"{k} ({n})" for k, n in sorted(kinds.items())) or "other kinds"
        return f"No {label} round found in the record; rounds found: {seen}"
    return f"Compatibility with {label} unknown: round types not recorded"


@step_handler(RANK)
async def rank_step(ctx: StepContext) -> dict[str, Any]:
    row = await _investor_run(ctx)
    spec_out = _output(ctx, SPEC) or {}
    comps = _output(ctx, COMPARABLES)
    enrich = _output(ctx, ENRICH)
    plan = plan_from(spec_out["plan"]) if spec_out.get("plan") else None
    sought = plan.kind_sought if plan else None
    companies = (enrich or {}).get("companies", [])

    notes: list[str] = []
    for key, label in ((COMPARABLES, "comparable search"), (ENRICH, "funding rounds")):
        dep = ctx.dependencies.get(key) or {}
        if dep.get("state") == "skipped_budget":
            notes.append(f"{label} not run: budget reached")
        elif dep.get("state") == "failed":
            notes.append(f"{label} failed")
    if enrich and enrich.get("not_read_budget"):
        notes.append(f"{enrich['not_read_budget']} comparable companies not read: budget reached")

    today = _utcnow().date()
    searched_at = (dt.datetime.fromisoformat(comps["searched_at"]) if comps else _utcnow()).date()
    examined = len(companies)
    scope = SearchScope(
        as_of=today, lookback_years=policy.INVESTOR_LOOKBACK_YEARS, companies_examined=examined
    )
    records = funding_records(companies)
    ranking = rank_investors(records, scope, sought)
    excluded = Counter(e.reason for e in ranking.excluded_records)

    scope_bits = [plan.describe()] if plan else []
    scope_bits.append(f"rounds dated {today.year - scope.lookback_years} to {today.isoformat()}")
    scope_note = (
        f"searched {searched_at.isoformat()} across {examined} comparable "
        f"compan{'ies' if examined != 1 else 'y'} ({'; '.join(scope_bits)})"
    )
    if notes:
        scope_note += "; " + "; ".join(notes)

    evidence_sources = {
        r["evidence_id"]: r["source_id"]
        for c in companies
        for r in c["rounds"]
        if r.get("evidence_id")
    }
    entry_ids = {inv.key: stable_id(ctx.run.id, "entry", inv.key) for inv in ranking.investors}
    await ctx.session.execute(delete(InvestorEntry).where(InvestorEntry.investor_run_id == row.id))
    extras: dict[str, dict[str, Any]] = {}
    for rank, inv in enumerate(ranking.investors, start=1):
        compat_text = _compatibility_text(inv, sought)
        unknowns = list(inv.unknowns)
        if inv.compatibility == Compatibility.UNKNOWN:
            unknowns.append(compat_text)
        unknowns.append(
            f"Investments outside the {examined} comparable companies examined are not counted"
        )
        dupes = [str(entry_ids[k]) for k in inv.possible_duplicates if k in entry_ids]
        ctx.session.add(
            InvestorEntry(
                id=entry_ids[inv.key],
                investor_run_id=row.id,
                investor_key=inv.key,
                investor_name=inv.name,
                investor_uuid=inv.investor_id,
                score=inv.score,
                rank=rank,
                comparable_rounds=[
                    {
                        "company_id": int(r.company_id),
                        "company_name": r.company_name,
                        "round_type": r.round_type,
                        "date": r.date.isoformat(),
                        "amount_usd": r.amount_usd,
                        "evidence_id": r.evidence_id,
                        "source_id": evidence_sources.get(r.evidence_id),
                    }
                    for r in inv.comparable_rounds
                ],
                last_sector_investment=(
                    inv.latest_sector_investment.date if inv.latest_sector_investment else None
                ),
                why=inv.why,
                possible_duplicate_of=dupes[0] if dupes else None,
                unknowns=unknowns,
            )
        )
        extras[inv.key] = {
            "compatibility": inv.compatibility.value,
            "compatibility_text": compat_text,
            "possible_duplicates": dupes,
        }

    row.profile = {
        **(row.profile or {}),
        "search": {
            "searched_at": (comps["searched_at"] if comps else _utcnow().isoformat()),
            "scope_note": scope_note,
            "comparables_considered": examined,
            "comparables_found": len(comps["companies"]) if comps else 0,
            "rounds_read": sum(len(c["rounds"]) for c in companies),
            "rounds_excluded": len(ranking.excluded_records),
            "excluded_reasons": dict(excluded),
            "funding_kind_sought": sought.value if sought else None,
            "natural_language": bool(comps and comps.get("natural_language")),
            "notes": notes,
            "entries": extras,
        },
    }
    row.status = "ready"
    usable = len(records) - len(ranking.excluded_records)
    ctx.result = (
        f"{len(ranking.investors)} investors ranked from {usable} dated, named investments;"
        f" {len(ranking.excluded_records)} excluded"
    )
    return {
        "investors": len(ranking.investors),
        "excluded": dict(excluded),
        "scope_note": scope_note,
    }


def budget_estimate(search_limit: int, enrich_limit: int) -> float:
    """Upper bound of credits a run with these limits can spend."""
    return float(
        SEARCH_CREDITS_PER_RESULT * search_limit
        + ENRICH_CREDITS_PER_MATCH * min(enrich_limit, MAX_ENRICH_IDS)
    )


__all__ = [
    "COMPARABLES",
    "ENRICH",
    "RANK",
    "SPEC",
    "ClientFactory",
    "SettingsClients",
    "budget_estimate",
    "clients",
    "step_specs",
]
