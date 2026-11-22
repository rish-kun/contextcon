"""Discover run: thesis criteria → Crustdata search → gate → enrich → rank → explain.

Steps (job runner; each idempotent, paid calls cached and metered to the discovery run):

1. `discover.search`  resolve categorical values (free autocomplete), then search with
   natural-language ranking plus must-have filters: hard filters only for reliably
   populated fields, unknown-inclusive (`matches OR is null`) for the rest. Falls back
   to filters only on `SemanticSearchUnavailable`; if the provider rejects the
   unknown-inclusive form, runs the strict query plus a bounded supplemental search
   without those filters. Widens once (dropping the unknown-inclusive filters) when
   fewer than 15 companies come back.
2. `discover.gate`    dedupe by Crustdata id, then domain; write evidence for every
   search field; `rules.assess_candidate`. Only a verified fail excludes.
3. `discover.enrich`  the top 15 by preliminary fit in ONE `company_enrich` call, plus
   a bounded `job_search` per enriched company for dated postings.
4. `discover.score`   re-gate on the enriched records, rank with `rules.shortlist`, and
   persist candidates, per-criterion results, cards and unknowns. Runs even when
   enrichment was skipped for budget, so the shortlist says "Not checked".
5. `discover.explain` "why on the shortlist" via `draft_shortlist_why` (citation-checked,
   deterministic fallback).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from app.clients.crustdata import COMPANY_ENRICH, CrustdataError, SemanticSearchUnavailable
from app.clients.llm import LLMError
from app.db.models import Candidate, CandidateCriterionResult, Criterion, DiscoveryRun, Thesis
from app.drafting.citations import split_sentences
from app.drafting.shortlist import CriterionResult as WhyCriterion
from app.drafting.shortlist import draft_shortlist_why, fallback_why
from app.extraction.llm import LlmOutputError
from app.jobs import BudgetExceeded, StepContext, StepSpec, step_handler
from app.pipelines.discover import cards, records
from app.pipelines.discover.clients import autocomplete, factories
from app.pipelines.discover.criteria import (
    PREFIX_ONLY_FIELDS,
    Resolution,
    SearchFilters,
    activity_keywords,
    as_values,
    build_filters,
    match_suggestions,
    needs_resolution,
    rule_criterion,
)
from app.rules import assess_candidate, shortlist

SEARCH_LIMIT = 50
WIDEN_BELOW = 15
WIDEN_LIMIT = 25
SUPPLEMENT_LIMIT = 15
ENRICH_TOP = 15
JOBS_PER_COMPANY = 5
LLM_CONCURRENCY = 4
JOB_CONCURRENCY = 5

SEARCH_FIELDS = ["crustdata_company_id", "basic_info", "locations", "taxonomy"]
ENRICH_FIELDS = [
    "basic_info",
    "headcount",
    "funding",
    "hiring",
    "locations",
    "taxonomy",
    "updated_at",
]
JOB_FIELDS = ["job_details", "location", "metadata"]

# Credit estimates checked against the budget before each call (Crustdata pricing on
# this key, 2026-11-22). The ledger records the provider's actual charge afterwards.
PRICE_SEARCH_BASE = 0.03
PRICE_TAXONOMY = 0.1
PRICE_PREMIUM = 0.2
PRICE_ENRICH = 2.0
PRICE_JOB = 0.03

S_SEARCH, S_GATE, S_ENRICH, S_SCORE, S_EXPLAIN = "search", "gate", "enrich", "score", "explain"


def step_specs(discovery_run_id: uuid.UUID) -> list[StepSpec]:
    inp = {"discovery_run_id": str(discovery_run_id)}
    return [
        StepSpec(S_SEARCH, "discover.search", label="Search companies", input=inp),
        StepSpec(
            S_GATE,
            "discover.gate",
            label="Remove duplicates and must-have failures",
            input=inp,
            depends_on=[S_SEARCH],
            uses_budget=False,
        ),
        StepSpec(
            S_ENRICH,
            "discover.enrich",
            label="Enrich the top 15: funding, headcount, hiring",
            input=inp,
            depends_on=[S_GATE],
        ),
        StepSpec(
            S_SCORE,
            "discover.score",
            label="Re-check must-haves and rank by fit",
            input=inp,
            depends_on=[S_SEARCH, S_GATE, S_ENRICH],
            uses_budget=False,
            tolerate_failed_deps=True,
        ),
        StepSpec(
            S_EXPLAIN,
            "discover.explain",
            label="Explain why each company is on the shortlist",
            input=inp,
            depends_on=[S_SCORE],
            uses_budget=False,
        ),
    ]


# --- Shared helpers ------------------------------------------------------------------


async def _discovery_run(ctx: StepContext) -> DiscoveryRun:
    dr_id = uuid.UUID(ctx.input["discovery_run_id"])
    dr = await ctx.session.get(DiscoveryRun, dr_id)
    if dr is None or dr.workspace_id != ctx.run.workspace_id or ctx.run.discovery_run_id != dr_id:
        raise LookupError("discovery run not found for this run")
    return dr


def _snapshot(dr: DiscoveryRun) -> tuple[list[dict[str, Any]], str]:
    snap = dr.criteria_snapshot or {}
    if isinstance(snap, list):  # tolerate a bare list
        return snap, ""
    return list(snap.get("criteria") or []), str(snap.get("activity_query") or "")


def _dep_output(ctx: StepContext, key: str) -> dict[str, Any] | None:
    dep = ctx.dependencies.get(key) or {}
    return dep.get("output") if dep.get("state") == "done" else None


def _rule_criteria(criteria: list[dict[str, Any]], resolutions: dict[str, Any]) -> list[Any]:
    return [rule_criterion(c, Resolution.from_json(resolutions.get(c["id"]))) for c in criteria]


async def _fmt_credits(ctx: StepContext) -> str:
    remaining = await ctx.budget_remaining()
    return "" if remaining is None else f"; {remaining:.2f} credits left"


# --- 1. Search ---------------------------------------------------------------------------


# Autocomplete is free but rate-limited; user-edited criteria must not fan it out.
MAX_AUTOCOMPLETE_CALLS = 30


class _Calls:
    def __init__(self, limit: int = MAX_AUTOCOMPLETE_CALLS) -> None:
        self.left = limit

    def take(self) -> bool:
        if self.left <= 0:
            return False
        self.left -= 1
        return True


async def resolve_values(
    client: Any, criteria: list[dict[str, Any]], calls: _Calls | None = None
) -> dict[str, Resolution]:
    calls = calls or _Calls()
    out: dict[str, Resolution] = {}
    for c in criteria:
        if not needs_resolution(c):
            continue
        field = c["crustdata_filter"]["field"]
        prefix_only = field in PREFIX_ONLY_FIELDS
        resolved: list[str] = []
        unmatched: list[str] = []
        for raw in as_values(c["value"]):
            value = str(raw).strip()
            queries = [value] + ([value[:5]] if len(value) > 5 else [])
            found: list[str] = []
            for q in queries:
                if not calls.take():
                    break
                found = match_suggestions(
                    value, await autocomplete(client, field, q), prefix_only=prefix_only
                )
                if found:
                    break
            if found:
                resolved += [v for v in found if v not in resolved]
            else:
                unmatched.append(value)
        if resolved:
            out[c["id"]] = Resolution("resolved", resolved, unmatched)
        else:
            out[c["id"]] = Resolution("unresolved", None, unmatched)
    return out


async def industries_from_activity(
    client: Any, activity: str, criteria: list[dict[str, Any]], calls: _Calls | None = None
) -> dict[str, Any] | None:
    """Filter-only fallback: industry values for the activity words (free autocomplete)."""
    text = " ".join(
        [
            str(v)
            for c in criteria
            if c["dimension"] == "industry_activity"
            for v in as_values(c["value"])
            if v
        ]
        + [activity]
    )
    words = activity_keywords(text, limit=6)
    calls = calls or _Calls()
    values: list[str] = []
    for w in words:
        if not calls.take():
            break
        for s in match_suggestions(
            w, await autocomplete(client, "basic_info.industries", w), prefix_only=False
        ):
            if s not in values:
                values.append(s)
    if not values:
        return None
    return {"field": "basic_info.industries", "type": "in", "value": values}


def _and(*conds: dict[str, Any] | None) -> dict[str, Any] | None:
    present = [c for c in conds if c]
    if not present:
        return None
    return present[0] if len(present) == 1 else {"op": "and", "conditions": present}


class _Searcher:
    def __init__(
        self,
        ctx: StepContext,
        paid: Any,
        free: Any,
        filters: SearchFilters,
        activity: str,
        criteria: list[dict[str, Any]],
    ) -> None:
        self.ctx, self.paid, self.free = ctx, paid, free
        self.filters, self.activity, self.criteria = filters, activity, criteria
        self.natural_language = bool(activity)
        self.industry_filter: dict[str, Any] | None = None
        self.items: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self.notes: list[str] = []

    def price(self) -> float:
        fields = set(self.filters.fields)
        if self.industry_filter:
            fields.add("basic_info.industries")
        price = PRICE_SEARCH_BASE + PRICE_TAXONOMY
        if any(f.startswith("taxonomy.") for f in fields):
            price += PRICE_TAXONOMY
        if any(f.split(".")[0] in {"headcount", "funding", "hiring"} for f in fields):
            price += PRICE_PREMIUM
        return price

    async def search(self, label: str, filters: dict[str, Any] | None, limit: int) -> int:
        while True:
            query = self.activity if self.natural_language else None
            combined = filters if self.natural_language else _and(filters, self.industry_filter)
            if combined is None and not query:
                raise ValueError("nothing to search with: no filters and no activity query")
            await self.ctx.require_budget(round(limit * self.price(), 4))
            await self.ctx.set_detail(f"Searching ({label}){await _fmt_credits(self.ctx)}")
            try:
                result, record = await self.paid.search_companies(
                    filters=combined, query=query, limit=limit, fields=SEARCH_FIELDS
                )
            except SemanticSearchUnavailable:
                self.natural_language = False
                self.notes.append(
                    "Natural-language search is not enabled for this account; "
                    "searched with filters only."
                )
                self.industry_filter = await industries_from_activity(
                    self.free, self.activity, self.criteria
                )
                continue
            body: dict[str, Any] = {"limit": limit, "fields": SEARCH_FIELDS}
            if combined is not None:
                body["filters"] = combined
            if query:
                body["search"] = {"query": query, "mode": "hybrid"}
            source = await records.add_source(
                self.ctx.session,
                workspace_id=self.ctx.run.workspace_id,
                run_id=self.ctx.run.id,
                endpoint="/company/search",
                request=body,
                record=record,
                cache=self.ctx.cache,
            )
            rows = [c.model_dump(mode="json", exclude_none=True) for c in result.companies]
            for i, company in enumerate(rows):
                self.items.append(
                    {
                        "company": {k: company.get(k) for k in SEARCH_FIELDS if k in company},
                        "source": source,
                        "query": label,
                        "position": len(self.items) + i,
                    }
                )
            self.queries.append(
                {
                    "label": label,
                    "natural_language": bool(query),
                    "limit": limit,
                    "returned": len(rows),
                    "credits": record.credits_used,
                    "from_cache": record.from_cache,
                }
            )
            return len(rows)

    def unique_ids(self) -> int:
        return len({records.company_id(i["company"]) for i in self.items})


@step_handler("discover.search")
async def search_step(ctx: StepContext) -> dict[str, Any]:
    dr = await _discovery_run(ctx)
    criteria, activity = _snapshot(dr)
    if not activity:
        activity = (
            await ctx.session.scalar(select(Thesis.text).where(Thesis.id == dr.thesis_id))
        ) or ""
    free = factories.crustdata(recorder=None, cache=ctx.cache)
    paid = factories.crustdata(recorder=ctx.recorder, cache=ctx.cache)
    try:
        await ctx.set_detail("Resolving filter values")
        resolutions = await resolve_values(free, criteria)
        filters = build_filters(criteria, resolutions)
        s = _Searcher(ctx, paid, free, filters, activity, criteria)
        try:
            await s.search("primary", filters.combine(soft="inclusive"), SEARCH_LIMIT)
        except CrustdataError as exc:
            if exc.status != 400 or not filters.soft:
                raise
            # The provider refused the unknown-inclusive form: strict query, plus a
            # bounded search without those filters so missing fields are not dropped.
            s.notes.append("Unknown-inclusive filters were refused; ran a supplemental search.")
            await s.search("strict", filters.combine(soft="strict"), SEARCH_LIMIT)
            try:
                await s.search("supplemental", filters.combine(soft="drop"), SUPPLEMENT_LIMIT)
            except BudgetExceeded:
                s.notes.append("Supplemental search not run: budget reached.")
        if s.unique_ids() < WIDEN_BELOW and filters.soft:
            try:
                await s.search("widened", filters.combine(soft="drop"), WIDEN_LIMIT)
            except BudgetExceeded:
                s.notes.append("Wider search not run: budget reached.")
    finally:
        await free.aclose()
        await paid.aclose()
    for label in filters.skipped:
        s.notes.append(f"'{label}' was not sent as a filter: its value is not a Crustdata value.")
    ctx.result = (
        f"{len(s.items)} results from {len(s.queries)} "
        f"{'search' if len(s.queries) == 1 else 'searches'}"
        + (" (natural language)" if s.natural_language else " (filters only)")
    )
    return {
        "natural_language": s.natural_language,
        "resolutions": {k: v.as_json() for k, v in resolutions.items()},
        "queries": s.queries,
        "notes": s.notes,
        "items": s.items,
    }


# --- 2. Gate -------------------------------------------------------------------------------


def _prelim_key(c: dict[str, Any]) -> tuple:
    return (c["fit"] is None, -(c["fit"] or 0), -c["assessable_pct"], c["position"])


@step_handler("discover.gate")
async def gate_step(ctx: StepContext) -> dict[str, Any]:
    dr = await _discovery_run(ctx)
    criteria, _ = _snapshot(dr)
    found = _dep_output(ctx, S_SEARCH) or {}
    rule_criteria = _rule_criteria(criteria, found.get("resolutions") or {})
    seen_ids: set[int] = set()
    seen_domains: dict[str, int] = {}
    duplicates: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for item in found.get("items") or []:
        company = item["company"]
        cid = records.company_id(company)
        if cid is None:
            continue
        name = records.company_name(company)
        if cid in seen_ids:
            duplicates.append(
                {
                    "crustdata_company_id": cid,
                    "name": name,
                    "same_as": cid,
                    "basis": "crustdata_company_id",
                }
            )
            continue
        domain = records.company_domain(company)
        if domain and domain in seen_domains:
            duplicates.append(
                {
                    "crustdata_company_id": cid,
                    "name": name,
                    "same_as": seen_domains[domain],
                    "basis": "domain",
                }
            )
            continue
        seen_ids.add(cid)
        if domain:
            seen_domains[domain] = cid
        facts = {
            fv.key: records.add_evidence(
                ctx.session, source=item["source"], crustdata_company_id=cid, fv=fv
            )
            for fv in records.search_values(company)
        }
        assessment = assess_candidate(rule_criteria, records.company_record(cid, name, facts))
        candidates.append(
            {
                "crustdata_company_id": cid,
                "name": name,
                "domain": domain,
                "position": item["position"],
                "facts": facts,
                "excluded": assessment.excluded,
                "exclusion_reasons": assessment.exclusion_reasons,
                "fit": assessment.fit.fit,
                "assessable_pct": assessment.fit.assessable_pct,
            }
        )
    survivors = sorted((c for c in candidates if not c["excluded"]), key=_prelim_key)
    excluded = [c for c in candidates if c["excluded"]]
    ctx.result = (
        f"{len(candidates)} unique companies; {len(duplicates)} duplicates removed; "
        f"{len(excluded)} failed a must-have"
    )
    return {
        "candidates": candidates,
        "survivors": [c["crustdata_company_id"] for c in survivors],
        "duplicates": duplicates,
    }


# --- 3. Enrich -----------------------------------------------------------------------------


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value


def _trim_enriched(data: dict[str, Any]) -> dict[str, Any]:
    out = {k: data[k] for k in ("crustdata_company_id", *ENRICH_FIELDS) if k in data}
    headcount = dict(out.get("headcount") or {})
    if headcount.get("timeseries"):
        headcount["timeseries"] = sorted(
            headcount["timeseries"], key=lambda p: p.get("date") or ""
        )[-24:]
    keep = ("total", "timeseries", "growth_percent", "largest_headcount_country")
    out["headcount"] = {k: headcount[k] for k in keep if k in headcount}
    hiring = dict(out.get("hiring") or {})
    hiring.pop("recent_openings", None)
    hiring.pop("open_jobs_timeseries", None)
    out["hiring"] = hiring
    return out


@step_handler("discover.enrich")
async def enrich_step(ctx: StepContext) -> dict[str, Any]:
    gate = _dep_output(ctx, S_GATE) or {}
    top = list(gate.get("survivors") or [])[:ENRICH_TOP]
    if not top:
        ctx.result = "Nothing to enrich"
        return {"enriched": {}, "not_enriched": {}, "jobs": {}, "jobs_not_checked": {}}

    remaining = await ctx.budget_remaining()
    n = len(top) if remaining is None else min(len(top), int(remaining // Decimal("2")))
    if n < 1:
        raise BudgetExceeded()
    ids, left_out = top[:n], top[n:]
    await ctx.require_budget(n * PRICE_ENRICH)
    await ctx.set_detail(f"Enriching {n} companies in one call{await _fmt_credits(ctx)}")

    paid = factories.crustdata(recorder=ctx.recorder, cache=ctx.cache)
    try:
        # Read as plain JSON, through the client's cache and recorder: live responses
        # send some funding fields (e.g. `lead_investors`) as a comma-separated string,
        # which the typed model rejects after the call has been paid for.
        body = {"crustdata_company_ids": ids, "fields": list(ENRICH_FIELDS)}
        raw, record = await paid._post(COMPANY_ENRICH, body)
        enrich_source = await records.add_source(
            ctx.session,
            workspace_id=ctx.run.workspace_id,
            run_id=ctx.run.id,
            endpoint="/company/enrich",
            request={"crustdata_company_ids": ids, "fields": ENRICH_FIELDS},
            record=record,
            cache=ctx.cache,
        )
        enriched: dict[str, dict[str, Any]] = {}
        wanted = set(ids)
        for res in raw or []:
            for match in (res or {}).get("matches") or []:
                data = _drop_none((match or {}).get("company_data") or {})
                cid = records.company_id(data)
                if cid in wanted and str(cid) not in enriched:  # attach by id only
                    enriched[str(cid)] = _trim_enriched(data)

        # Hiring: dated postings for each enriched company, bounded by the budget.
        jobs: dict[str, dict[str, Any]] = {}
        jobs_not_checked: dict[str, str] = {}
        job_ids = [cid for cid in ids if str(cid) in enriched]
        remaining = await ctx.budget_remaining()
        per_company = Decimal(str(JOBS_PER_COMPANY * PRICE_JOB))
        affordable = len(job_ids) if remaining is None else max(0, int(remaining // per_company))
        for cid in job_ids[affordable:]:
            jobs_not_checked[str(cid)] = f"not checked ({cards.NOT_CHECKED_BUDGET})"
        await ctx.set_detail(f"Reading job postings for {min(affordable, len(job_ids))} companies")
        sem = asyncio.Semaphore(JOB_CONCURRENCY)

        async def fetch(cid: int) -> tuple[int, Any]:
            async with sem:
                try:
                    return cid, await paid.search_jobs(
                        cid, limit=JOBS_PER_COMPANY, fields=JOB_FIELDS
                    )
                except CrustdataError as exc:
                    return cid, exc

        fetched = await asyncio.gather(*(fetch(cid) for cid in job_ids[:affordable]))
    finally:
        await paid.aclose()

    for cid, outcome in fetched:
        if isinstance(outcome, CrustdataError):
            jobs_not_checked[str(cid)] = "not checked (provider error)"
            continue
        result, record = outcome
        source = await records.add_source(
            ctx.session,
            workspace_id=ctx.run.workspace_id,
            run_id=ctx.run.id,
            endpoint="/job/search",
            request={
                "filters": {"field": "company.basic_info.company_id", "type": "=", "value": cid},
                "limit": JOBS_PER_COMPANY,
                "fields": JOB_FIELDS,
            },
            record=record,
            cache=ctx.cache,
        )
        jobs[str(cid)] = {
            "source": source,
            "listings": [j.model_dump(mode="json", exclude_none=True) for j in result.job_listings],
        }

    ctx.result = f"Enriched {len(enriched)} of {n} in one call; postings for {len(jobs)}" + (
        f"; {len(left_out)} not enriched (budget)" if left_out else ""
    )
    return {
        "enrich_source": enrich_source,
        "enriched": enriched,
        "not_enriched": {str(cid): cards.NOT_CHECKED_BUDGET for cid in left_out},
        "jobs": jobs,
        "jobs_not_checked": jobs_not_checked,
    }


# --- 4. Score ------------------------------------------------------------------------------


def _enrich_status(ctx: StepContext) -> tuple[dict[str, Any] | None, str | None]:
    dep = ctx.dependencies.get(S_ENRICH) or {}
    state = dep.get("state")
    if state == "done":
        return dep.get("output") or {}, None
    if state == "skipped_budget":
        return None, dep.get("skip_reason") or cards.NOT_CHECKED_BUDGET
    return None, "enrichment failed"


@step_handler("discover.score")
async def score_step(ctx: StepContext) -> dict[str, Any]:
    dr = await _discovery_run(ctx)
    criteria, _ = _snapshot(dr)
    gate = _dep_output(ctx, S_GATE)
    found = _dep_output(ctx, S_SEARCH) or {}
    if gate is None:
        dep = ctx.dependencies.get(S_GATE) or {}
        reason = dep.get("skip_reason") or dep.get("error") or dep.get("state") or "not run"
        dr.status = "no_results"
        ctx.result = f"No companies to rank: search not completed ({reason})"
        return {"ranked": 0, "excluded": 0, "search_not_checked": reason}

    rule_criteria = _rule_criteria(criteria, found.get("resolutions") or {})
    enrich, not_enriched_reason = _enrich_status(ctx)
    by_id = {c["crustdata_company_id"]: c for c in gate["candidates"]}
    pool = list(gate["survivors"])[:ENRICH_TOP]

    built: dict[int, dict[str, Any]] = {}
    for cid in pool:
        cand = by_id[cid]
        facts = dict(cand["facts"])
        rounds: list[dict[str, Any]] = []
        postings: list[dict[str, Any]] = []
        data = (enrich or {}).get("enriched", {}).get(str(cid))
        reason = not_enriched_reason or (enrich or {}).get("not_enriched", {}).get(str(cid))
        if data is not None:
            src = enrich["enrich_source"]
            for fv in records.enrich_values(data):
                facts[fv.key] = records.add_evidence(
                    ctx.session, source=src, crustdata_company_id=cid, fv=fv
                )
            rounds = [
                records.add_evidence(ctx.session, source=src, crustdata_company_id=cid, fv=fv)
                for fv in records.funding_rounds(data)
            ]
            job = enrich.get("jobs", {}).get(str(cid))
            if job is not None:
                postings = [
                    records.add_evidence(
                        ctx.session, source=job["source"], crustdata_company_id=cid, fv=fv
                    )
                    for fv in records.job_postings(job["listings"])
                ]
        elif reason is None:
            reason = "no enrichment match for this id"
        hiring_note = None
        if data is not None:
            hiring_note = enrich.get("jobs_not_checked", {}).get(str(cid))
            if hiring_note is None and not postings:
                hiring_note = "none found in recent postings"
        built[cid] = {
            "cand": cand,
            "facts": facts,
            "rounds": rounds,
            "postings": postings,
            "enriched": data is not None,
            "not_enriched_reason": reason,
            "hiring_note": hiring_note,
        }

    result = shortlist(
        rule_criteria,
        [records.company_record(cid, b["cand"]["name"], b["facts"]) for cid, b in built.items()],
    )

    existing = set(
        (
            await ctx.session.execute(
                select(Criterion.id).where(Criterion.thesis_id == dr.thesis_id)
            )
        ).scalars()
    )
    await ctx.session.execute(delete(Candidate).where(Candidate.discovery_run_id == dr.id))

    def persist(cid: int, assessment: Any, rank: int | None, b: dict[str, Any] | None) -> None:
        cand = by_id[cid]
        facts = b["facts"] if b else cand["facts"]
        unknown_items = cards.unknowns(
            rule_criteria,
            assessment,
            facts,
            enriched=bool(b and b["enriched"]),
            not_enriched_reason=(b["not_enriched_reason"] if b else "excluded before enrichment"),
            rounds=b["rounds"] if b else [],
            hiring_note=b["hiring_note"] if b else None,
        )
        card = cards.build_card(
            facts,
            rounds=b["rounds"] if b else [],
            postings=b["postings"] if b else [],
            reasons=cards.met_reasons(rule_criteria, assessment),
            unknown_items=unknown_items,
        )
        row = Candidate(
            id=uuid.uuid4(),
            discovery_run_id=dr.id,
            crustdata_company_id=str(cid),
            name=cand["name"],
            domain=cand["domain"],
            rank=rank,
            fit=assessment.fit.fit,
            assessable_pct=assessment.fit.assessable_pct,
            card=card,
            unknowns=unknown_items,
            excluded=assessment.excluded,
            exclusion_reason="; ".join(assessment.exclusion_reasons) or None,
        )
        row.criterion_results = [
            CandidateCriterionResult(
                criterion_id=uuid.UUID(e.criterion_id),
                result=e.result.value,
                reason=e.reason,
                evidence_ids=list(e.evidence_ids),
            )
            for e in assessment.fit.evaluations
            if uuid.UUID(e.criterion_id) in existing
        ]
        ctx.session.add(row)

    for i, a in enumerate(result.ranked, start=1):
        persist(int(a.entity_id), a, i, built[int(a.entity_id)])
    for a in result.excluded:
        persist(int(a.entity_id), a, None, built[int(a.entity_id)])
    # Companies excluded at the gate keep the gate's search-field assessment.
    gate_excluded = [c for c in gate["candidates"] if c["excluded"]]
    for cand in gate_excluded:
        cid = cand["crustdata_company_id"]
        a = assess_candidate(
            rule_criteria, records.company_record(cid, cand["name"], cand["facts"])
        )
        persist(cid, a, None, None)

    dr.status = "scored"
    later_fails = len(result.excluded)
    ctx.result = (
        f"{len(result.ranked)} on the shortlist; {later_fails} removed after enrichment; "
        f"{len(gate_excluded)} removed at the gate"
    )
    return {
        "ranked": len(result.ranked),
        "excluded_after_enrichment": later_fails,
        "excluded_at_gate": len(gate_excluded),
        "not_enriched_survivors": max(0, len(gate["survivors"]) - len(pool)),
        "enrichment": "done" if enrich is not None else f"not checked ({not_enriched_reason})",
    }


# --- 5. Explain ----------------------------------------------------------------------------


def why_reasons(text: str, evidence_by_criterion: dict[str, list[str]]) -> list[dict[str, Any]]:
    """One reason per drafted sentence, citation markers moved into fields."""
    out: list[dict[str, Any]] = []
    for sentence in split_sentences(text):
        ids = [
            i.strip() for group in re.findall(r"\[([^\[\]]+)\]", sentence) for i in group.split(",")
        ]
        clean = re.sub(r"\s*\[[^\[\]]*\]", "", sentence).strip()
        if not clean:
            continue
        evidence: list[str] = []
        for cid in ids:
            evidence += [e for e in evidence_by_criterion.get(cid, []) if e not in evidence]
        out.append(
            {"text": clean, "criterion_id": ids[0] if ids else None, "evidence_ids": evidence}
        )
    return out


@step_handler("discover.explain")
async def explain_step(ctx: StepContext) -> dict[str, Any]:
    dr = await _discovery_run(ctx)
    criteria, _ = _snapshot(dr)
    labels = {c["id"]: (c["label"], c["kind"]) for c in criteria}
    rows = list(
        (
            await ctx.session.execute(
                select(Candidate)
                .where(Candidate.discovery_run_id == dr.id, Candidate.excluded.is_(False))
                .order_by(Candidate.rank)
            )
        ).scalars()
    )
    if not rows:
        dr.status = "done"
        ctx.result = "No shortlisted companies to explain"
        return {"explained": 0}
    by_candidate: dict[uuid.UUID, list[CandidateCriterionResult]] = {}
    for r in (
        await ctx.session.execute(
            select(CandidateCriterionResult).where(
                CandidateCriterionResult.candidate_id.in_([c.id for c in rows])
            )
        )
    ).scalars():
        by_candidate.setdefault(r.candidate_id, []).append(r)

    llm = factories.llm(recorder=ctx.recorder, cache=ctx.cache)
    sem = asyncio.Semaphore(LLM_CONCURRENCY)
    await ctx.set_detail(f"Drafting {len(rows)} explanations")

    async def explain(row: Candidate) -> tuple[Candidate, str, bool, dict[str, list[str]]]:
        items = [
            WhyCriterion(
                id=str(r.criterion_id),
                label=labels.get(str(r.criterion_id), ("criterion", "must"))[0],
                kind=labels.get(str(r.criterion_id), ("criterion", "must"))[1],
                result=r.result,
                detail=r.reason,
            )
            for r in sorted(by_candidate.get(row.id, []), key=lambda r: str(r.criterion_id))
        ]
        evidence = {
            str(r.criterion_id): list(r.evidence_ids or []) for r in by_candidate.get(row.id, [])
        }
        if not items:
            return row, "", True, evidence
        async with sem:
            try:
                why = await draft_shortlist_why(llm, row.name, items)
                return row, why.text, why.used_fallback, evidence
            except (LLMError, LlmOutputError):
                return row, fallback_why(items), True, evidence

    try:
        drafted = await asyncio.gather(*(explain(r) for r in rows))
    finally:
        close = getattr(llm, "aclose", None)
        if close is not None:
            await close()

    fallbacks = 0
    for row, text, used_fallback, evidence in drafted:
        fallbacks += int(used_fallback)
        if not text:
            continue
        reasons = why_reasons(text, evidence)
        if reasons:
            row.card = {**row.card, "reasons": reasons}
    dr.status = "done"
    ctx.result = f"Explained {len(rows)} companies" + (
        f" ({fallbacks} with the plain list)" if fallbacks else ""
    )
    return {"explained": len(rows), "fallbacks": fallbacks}
