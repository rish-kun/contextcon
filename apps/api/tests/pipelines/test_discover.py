"""Discover pipeline end to end on a fictional Crustdata world (no live calls)."""

import uuid
from decimal import Decimal
from typing import Any

import httpx2 as httpx
import pytest
from sqlalchemy import func, select, update

from app.api import runs as runs_api
from app.api.theses_deps import db_sessionmaker, llm_factory
from app.auth.deps import current_user
from app.auth.sessions import AuthUser
from app.db.models import (
    Candidate,
    CandidateCriterionResult,
    CostEntry,
    Criterion,
    DiscoveryRun,
    Evidence,
    Run,
    Source,
)
from app.jobs import StepRegistry, registry
from app.main import create_app
from app.pipelines.discover import clients, create_thesis, start_search
from app.pipelines.discover.steps import ENRICH_TOP
from tests.db.factories import tenant
from tests.jobs.helpers import make_worker, states, step
from tests.pipelines import discover_fakes as fakes

pytestmark = pytest.mark.asyncio


async def _thesis(session, sm, t):  # type: ignore[no-untyped-def]
    return await create_thesis(
        session,
        sm,
        t.workspace.id,
        fakes.PRD_THESIS,
        created_by=t.user.id,
        llm_factory=fakes.llm_factory(),
    )


async def _run(
    session,
    sm,
    fake: fakes.FakeCrustdata,
    *,
    budget: float | None = None,
    reg: StepRegistry | None = None,
    llm: Any = None,
):  # type: ignore[no-untyped-def]
    t = await tenant(session)
    thesis = await _thesis(session, sm, t)
    run = await start_search(session, t.workspace.id, thesis.id, created_by=t.user.id)
    if budget is not None:
        async with sm() as s:
            await s.execute(update(Run).where(Run.id == run.id).values(budget_credits=budget))
            await s.commit()
    with clients.use(crustdata=fake.client, llm=llm or fakes.llm_factory()):
        await make_worker(sm, reg or registry).drain()
    return t, thesis, run


async def _candidates(sm, run) -> dict[int, Candidate]:  # type: ignore[no-untyped-def]
    async with sm() as s:
        rows = (
            await s.execute(
                select(Candidate).where(Candidate.discovery_run_id == run.discovery_run_id)
            )
        ).scalars()
        return {int(c.crustdata_company_id): c for c in rows}


async def test_shortlist_gate_rerank_and_dedupe(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=10))
    _, _, run = await _run(session, sm, fake)
    assert set((await states(sm, run.id)).values()) == {"done"}
    cands = await _candidates(sm, run)

    # Dedupe: the repeated id (101) and the same domain under another id (106) are gone.
    assert 106 not in cands and list(cands).count(101) == 1
    gate = (await step(sm, run.id, "gate")).output
    assert {(d["crustdata_company_id"], d["basis"]) for d in gate["duplicates"]} >= {
        (101, "crustdata_company_id"),
        (106, "domain"),
    }

    # Verified fail at the gate (search data says Singapore).
    assert cands[104].excluded and "Based in India" in cands[104].exclusion_reason
    # A later verified fail: ownership unknown in search, "Public Company" after enrichment.
    b = cands[102]
    assert b.excluded and b.rank is None and "Privately held" in b.exclusion_reason
    # An unknown survives, with reduced coverage but the same fit.
    a, c = cands[101], cands[103]
    assert not c.excluded and c.rank is not None, c.exclusion_reason
    assert c.fit == a.fit == 100 and c.assessable_pct < a.assessable_pct
    assert any("Privately held: not known" in u for u in c.unknowns)
    # The provider's "IND" is read as India (evidence keeps the provider's value).
    async with sm() as s:
        ev = (
            (await s.execute(select(Evidence).where(Evidence.field_path == "locations.country")))
            .scalars()
            .first()
        )
    assert ev.value in ("IND", "SGP")
    assert a.card["location"]["value"].endswith("India")
    # Zero assessable criteria: fit unavailable, ranked last.
    g = cands[107]
    assert not g.excluded and g.fit is None and g.assessable_pct == 0
    assert g.rank == max(x.rank for x in cands.values() if x.rank is not None)
    # Ranked by fit, then assessable share.
    ranked = sorted((x for x in cands.values() if x.rank), key=lambda x: x.rank)
    keys = [((x.fit is None), -(x.fit or 0), -x.assessable_pct) for x in ranked]
    assert keys == sorted(keys)

    # Must-have filters: country is a hard filter (resolved "Indian" -> "India"),
    # ownership is unknown-inclusive; natural-language mode is on.
    first = fake.search_bodies[0]
    assert first["search"]["query"] == "warehousing and supply-chain software"
    conds = first["filters"]["conditions"]
    assert {"field": "locations.country", "type": "in", "value": ["India"]} in conds
    assert {
        "op": "or",
        "conditions": [
            {"field": "basic_info.company_type", "type": "in", "value": ["Privately Held"]},
            {"field": "basic_info.company_type", "type": "is_null"},
        ],
    } in conds

    # Per-criterion results are persisted for every candidate.
    async with sm() as s:
        n_criteria = await s.scalar(select(func.count()).select_from(Criterion))
        per = (
            await s.execute(
                select(CandidateCriterionResult.candidate_id, func.count()).group_by(
                    CandidateCriterionResult.candidate_id
                )
            )
        ).all()
    assert per and all(n == n_criteria for _, n in per)

    # The "why" text is citation-checked and stored as reasons tied to criteria.
    reasons = a.card["reasons"]
    assert reasons and all(r["criterion_id"] for r in reasons)
    assert all("[" not in r["text"] for r in reasons)


async def test_single_enrich_call_for_top_15(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=20))
    _, _, run = await _run(session, sm, fake)
    assert len(fake.enrich_bodies) == 1
    ids = fake.enrich_bodies[0]["crustdata_company_ids"]
    assert len(ids) == ENRICH_TOP == 15 and len(set(ids)) == 15
    # Hiring postings: one bounded job search per enriched company.
    assert len(fake.job_bodies) <= 15 and all(b["limit"] == 5 for b in fake.job_bodies)
    # Survivors past the top 15 are not on the shortlist.
    assert sum(1 for c in (await _candidates(sm, run)).values() if c.rank) <= 15


async def test_every_card_fact_has_source_and_evidence(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=3))
    _, _, run = await _run(session, sm, fake)
    cands = await _candidates(sm, run)
    async with sm() as s:
        sources = {str(r.id): r for r in (await s.execute(select(Source))).scalars()}
        evidence = {str(r.id): r for r in (await s.execute(select(Evidence))).scalars()}
        results = list((await s.execute(select(CandidateCriterionResult))).scalars())

    assert sources and all(r.source_class == "data_provider" for r in sources.values())
    assert all(
        r.retrieved_at is not None and r.endpoint_or_url.startswith("/") for r in sources.values()
    )

    checked = 0

    def walk(node: Any) -> None:
        nonlocal checked
        if isinstance(node, dict):
            if "source" in node and isinstance(node["source"], dict):
                src = node["source"]
                assert src["source_id"] in sources, node
                assert src["retrieved_at"] and src["url_or_endpoint"]
                if node.get("evidence_id"):
                    ev = evidence[node["evidence_id"]]
                    assert str(ev.source_id) == src["source_id"]
                checked += 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for c in cands.values():
        walk(c.card)
        card = c.card
        for key in (
            "business",
            "location",
            "headcount",
            "headcount_growth_yoy_pct",
            "total_funding_usd",
        ):
            if card[key] is not None:
                assert card[key]["evidence_id"] in evidence
    assert checked > 20

    a = cands[101].card
    assert a["headcount"]["is_estimate"] and a["headcount"]["estimate_kind"] == "estimate"
    assert a["headcount"]["as_of"] == "2026-10-01"
    assert a["headcount_growth_yoy_pct"]["is_estimate"]
    assert a["hiring"]["openings"]["estimate_kind"] == "signal"
    assert [p["title"] for p in a["hiring"]["postings"]] == [
        "WMS Engineer",
        "Enterprise Account Executive",
    ]
    # Undated rounds are never shown as dated.
    assert [r["date"] for r in a["funding_rounds"]] == ["2024-03-01", "2022-06-15"]
    assert a["funding_rounds"][1]["investors"] == [
        "Seed Partners (fixture)",
        "Angel Group (fixture)",
    ]
    # Criterion results cite evidence that exists.
    assert all(e in evidence for r in results for e in r.evidence_ids)


async def test_budget_exhaustion_skips_enrichment_with_not_checked(session, sm) -> None:
    # 17 results at 0.3 credits = 5.1 of 7 credits; 1.9 credits cannot pay for one
    # enrichment (2 credits).
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=10), search_price=0.3)
    _, _, run = await _run(session, sm, fake, budget=7)
    st = await states(sm, run.id)
    assert st["search"] == "done" and st["enrich"] == "skipped_budget"
    assert st["score"] == "done" and st["explain"] == "done"
    assert fake.enrich_bodies == [] and fake.job_bodies == []
    enrich = await step(sm, run.id, "enrich")
    assert enrich.skip_reason == "budget reached"
    cands = await _candidates(sm, run)
    survivors = [c for c in cands.values() if not c.excluded]
    assert survivors
    for c in survivors:
        assert "Funding, headcount and hiring: not checked (budget reached)" in c.unknowns
        assert c.card["headcount"] is None and c.card["funding_rounds"] == []
    async with sm() as s:
        assert (await s.get(Run, run.id)).state == "done"
        spent = await s.scalar(
            select(func.sum(CostEntry.credits)).where(
                CostEntry.discovery_run_id == run.discovery_run_id
            )
        )
    assert spent <= Decimal(7)


async def test_budget_for_part_of_the_top_15_enriches_only_those(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=10))
    # The search costs 2.21 of 6.5 credits, leaving enough to enrich 2 companies.
    _, _, run = await _run(session, sm, fake, budget=6.5)
    assert len(fake.enrich_bodies) == 1 and len(fake.enrich_bodies[0]["crustdata_company_ids"]) == 2
    cands = [c for c in (await _candidates(sm, run)).values() if c.rank]
    not_checked = [
        c
        for c in cands
        if "Funding, headcount and hiring: not checked (budget reached)" in c.unknowns
    ]
    # 0.29 credits are left for postings: one company's postings are read, one is not.
    postings_skipped = [
        c for c in cands if "Hiring postings: not checked (budget reached)" in c.unknowns
    ]
    assert len(postings_skipped) == 1 and len(fake.job_bodies) == 1
    assert len(not_checked) == len(cands) - 2


async def test_zero_budget_skips_search_and_says_so(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=2))
    _, _, run = await _run(session, sm, fake, budget=0)
    st = await states(sm, run.id)
    assert st["search"] == "skipped_budget" and st["gate"] == "skipped_budget"
    assert st["enrich"] == "skipped_budget" and st["score"] == "done"
    assert fake.paid_http_calls == 0
    score = await step(sm, run.id, "score")
    assert "budget reached" in score.result
    assert await _candidates(sm, run) == {}


async def test_resume_after_crash_replays_cache_without_paying(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=4))
    reg = StepRegistry()
    for name in registry.names():
        reg.register(name, registry.get(name), replace=True)
    real_enrich = registry.get("discover.enrich")
    crashed = []

    async def crash_once(ctx):  # type: ignore[no-untyped-def]
        out = await real_enrich(ctx)  # the paid calls happen and are recorded...
        if not crashed:
            crashed.append(ctx.attempt)
            raise RuntimeError("worker died before committing")  # ...then the step is lost
        return out

    reg.register("discover.enrich", crash_once, replace=True)
    _, _, run = await _run(session, sm, fake, reg=reg)

    enrich = await step(sm, run.id, "enrich")
    assert enrich.state == "done" and enrich.attempts == 2 and crashed == [1]
    assert len(fake.enrich_bodies) == 1  # the retry replayed the cached response
    async with sm() as s:
        rows = (
            (
                await s.execute(
                    select(CostEntry.credits).where(
                        CostEntry.run_id == run.id, CostEntry.endpoint == "/company/enrich"
                    )
                )
            )
            .scalars()
            .all()
        )
        sources = await s.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.run_id == run.id, Source.endpoint_or_url == "/company/enrich")
        )
    assert rows == [Decimal("2") * len(fake.enrich_bodies[0]["crustdata_company_ids"])]
    assert sources == 1  # the crashed attempt's writes were rolled back


async def test_semantic_search_unavailable_falls_back_to_filters(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=3), semantic_disabled=True)
    _, _, run = await _run(session, sm, fake)
    out = (await step(sm, run.id, "search")).output
    assert out["natural_language"] is False
    assert any("Natural-language search is not enabled" in n for n in out["notes"])
    retry = fake.search_bodies[1]
    assert "search" not in retry
    industries = [
        c for c in retry["filters"]["conditions"] if c.get("field") == "basic_info.industries"
    ]
    assert industries and "Warehousing" in industries[0]["value"]
    assert any(not c.excluded for c in (await _candidates(sm, run)).values())


async def test_unknown_inclusive_refused_runs_bounded_supplemental(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=3), reject_is_null=True)
    _, _, run = await _run(session, sm, fake)
    labels = [q["label"] for q in (await step(sm, run.id, "search")).output["queries"]]
    assert labels[:2] == ["strict", "supplemental"]
    supplemental = fake.search_bodies[2]
    assert supplemental["limit"] == 15
    assert "basic_info.company_type" not in str(supplemental["filters"])
    # Companies with no ownership value still reach the shortlist.
    assert not (await _candidates(sm, run))[103].excluded


async def test_costs_go_to_the_discovery_run(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=10))
    _, _, run = await _run(session, sm, fake)
    async with sm() as s:
        rows = list((await s.execute(select(CostEntry))).scalars())
        dr = await s.get(DiscoveryRun, run.discovery_run_id)
    assert rows and all(r.case_id is None and r.discovery_run_id == dr.id for r in rows)
    credits = sum(r.credits for r in rows)
    assert 0 < credits <= 60
    assert any(r.provider == "anthropic" and r.run_id is None for r in rows)  # extraction
    assert any(r.provider == "anthropic" and r.run_id == run.id for r in rows)  # why text


async def test_rejected_drafts_fall_back_to_plain_list(session, sm) -> None:
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=2))
    _, _, run = await _run(session, sm, fake, llm=fakes.llm_factory(fail_drafts=True))
    assert "with the plain list" in (await step(sm, run.id, "explain")).result
    a = (await _candidates(sm, run))[101]
    assert a.card["reasons"][0]["text"].startswith("Meets:")


# --- HTTP routes ------------------------------------------------------------------------


def _client(sm, workspace_id: uuid.UUID, user_id: uuid.UUID) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    app = create_app()
    user = AuthUser(
        id=user_id, workspace_id=workspace_id, email="a@example.test", display_name="Analyst"
    )
    app.dependency_overrides[current_user] = lambda: user  # stands in for a session cookie
    app.dependency_overrides[db_sessionmaker] = lambda: sm
    app.dependency_overrides[llm_factory] = lambda: fakes.llm_factory()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_theses_routes_end_to_end(session, sm, monkeypatch) -> None:
    monkeypatch.setattr(runs_api, "get_sessionmaker", lambda: sm)
    t = await tenant(session)
    other = await tenant(session, "other")
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=3))
    async with _client(sm, t.workspace.id, t.user.id) as http:
        created = await http.post("/theses", json={"text": fakes.PRD_THESIS})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "draft" and len(body["criteria"]) == 5
        by_label = {c["label"]: c for c in body["criteria"]}
        assert by_label["Based in India"]["crustdata_filter"] == {
            "field": "locations.country",
            "type": "=",
            "value": "Indian",
        }
        assert by_label["Serves enterprise customers"]["assessed_from_evidence"]

        edits = [
            {
                k: c[k]
                for k in (
                    "id",
                    "label",
                    "kind",
                    "dimension",
                    "operator",
                    "value",
                    "crustdata_filter",
                )
            }
            for c in body["criteria"]
        ]
        edits[3]["kind"] = "must"  # make "enterprise customers" a must-have
        edited = await http.put(f"/theses/{body['id']}/criteria", json=edits)
        assert edited.status_code == 200, edited.text
        crit = {c["label"]: c for c in edited.json()["criteria"]}
        assert crit["Serves enterprise customers"]["edited"]
        assert crit["Serves enterprise customers"]["kind"] == "must"
        assert not crit["Based in India"]["edited"]

        bad = [dict(edits[0], crustdata_filter={"field": "basic_info.year_founded"})]
        assert (await http.put(f"/theses/{body['id']}/criteria", json=bad)).status_code == 422

        started = await http.post(f"/theses/{body['id']}/search")
        assert started.status_code == 202, started.text
        run = started.json()
        assert run["kind"] == "discover" and run["budget_credits"] == 60
        assert [s["key"] for s in run["steps"]] == ["search", "gate", "enrich", "score", "explain"]
        assert (await http.post(f"/theses/{body['id']}/search")).status_code == 409

        with clients.use(crustdata=fake.client, llm=fakes.llm_factory()):
            await make_worker(sm, registry).drain()

        got = (await http.get(f"/theses/{body['id']}")).json()
        assert got["status"] == "ready" and got["run"]["state"] == "done"
        assert got["run"]["cost"]["crustdata_credits"] > 0
        items = got["shortlist"]
        assert items[0]["rank"] == 1 and items[-1]["excluded"]
        first = items[0]
        assert first["criterion_results"] and first["card"]["last_updated"]
        sourced = [r for r in first["criterion_results"] if r["evidence"]]
        assert sourced and sourced[0]["evidence"][0]["source"]["source_class"] == ("data_provider")
        unavailable = [i for i in items if i["fit"] is None]
        assert all(i["fit_unavailable_reason"] for i in unavailable)

        listed = (await http.get("/theses")).json()
        assert listed[0]["id"] == body["id"] and listed[0]["shortlist_count"] >= 1

        status = await http.get(f"/runs/{run['id']}")
        assert status.status_code == 200 and status.json()["state"] == "done"

    async with _client(sm, other.workspace.id, other.user.id) as http:
        assert (await http.get(f"/theses/{body['id']}")).status_code == 404
        assert (await http.get(f"/runs/{run['id']}")).status_code == 404


def test_country_codes_map_to_names_and_unknown_codes_stay_unknown() -> None:
    from app.pipelines.discover.records import search_values

    def country(value: str) -> list[str]:
        row = {"crustdata_company_id": 1, "locations": {"country": value}}
        return [f.value for f in search_values(row) if f.key == "locations.country"]

    assert country("IND") == ["India"]
    assert country("India") == ["India"]
    assert country("XQZ") == []  # not a known code: unknown, never a verified fail
