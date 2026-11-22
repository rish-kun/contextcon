"""CP-19: case creation, identity, registry evidence, profile, dated events, comparables.

Fake clients only: a real `CrustdataClient` over a mock transport (so the cache and the
cost ledger run for real) and a regex-scripted LLM. Companies are fictional."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import select

import app.pipelines.verify  # noqa: F401 - registers the step handlers
from app.api import cases_deps
from app.api.cases_deps import CaseActor
from app.api.schemas.cases import CaseCreate, IdentityPickIn
from app.db import ledger, repo
from app.db.models import (
    Candidate,
    Case,
    Claim,
    Comparable,
    DiscoveryRun,
    Event,
    Evidence,
    Run,
    Source,
    Step,
    Thesis,
)
from app.jobs import registry as default_registry
from app.jobs.engine import append_steps
from app.main import create_app
from app.pipelines.verify import common
from app.pipelines.verify.common import (
    COMPARABLES,
    EVENTS,
    IDENTITY,
    PROFILE,
    REGISTRY,
    PublicTerms,
    news_query,
    registry_query,
)
from app.pipelines.verify.identity import dependent_steps
from tests.jobs.helpers import make_worker, states
from tests.pipelines.case_fakes import FakeCrustdata, FakeLlm, company, enrich_record, page

pytestmark = pytest.mark.asyncio

ACME = "Acme Freight (fixture)"
ACME_DOMAIN = "acmefreight.example"
ACME_ID = 700001
CONFIDENTIAL = "We secretly hold a 40 crore unannounced contract with BigRetail"


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeCrustdata:
    fake = FakeCrustdata()
    llm = FakeLlm()
    monkeypatch.setattr(common.clients, "crustdata", fake.factory)
    monkeypatch.setattr(common.clients, "llm", lambda ctx: llm)
    fake.llm = llm  # type: ignore[attr-defined]
    return fake


async def _actor(session) -> CaseActor:
    ws = await repo.create_workspace(session, "verify-ws")
    user = await repo.create_user(
        session, ws.id, email=f"analyst-{ws.id.hex[:6]}@example.test", display_name="Asha Analyst"
    )
    await session.commit()
    return CaseActor(workspace_id=ws.id, user_id=user.id, display_name=user.display_name)


async def _drain(sm) -> int:
    return await make_worker(sm, default_registry).drain()


async def _case(session, case_id) -> Case:
    session.expire_all()
    return await session.get(Case, case_id)


def _happy_api(api: FakeCrustdata) -> None:
    acme = company(ACME_ID, ACME, ACME_DOMAIN)
    api.identify[("domains", ACME_DOMAIN)] = [acme]
    api.identify[("names", ACME)] = [acme]
    api.enrich[ACME_ID] = enrich_record(ACME_ID, ACME, ACME_DOMAIN)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    api.web[registry_query(terms)] = [
        {"url": "https://www.zaubacorp.com/company/acme", "title": "Acme registry"},
        {"url": "https://randomblog.example/acme", "title": "Not a registry"},
    ]
    api.pages["https://www.zaubacorp.com/company/acme"] = page(
        "https://www.zaubacorp.com/company/acme",
        "ACME FREIGHT (FIXTURE) - Company details",
        "<p>Company Name: Acme Freight (fixture)</p>"
        "<p>CIN: U63090PN2014PTC123456</p>"
        "<p>Date of Incorporation: 12 March 2014</p>"
        "<p>Registrar of Companies: RoC-Pune</p>",
        published=None,
    )
    api.web[news_query(terms)] = [
        {"url": "https://news.example/acme-pune-hub", "title": "Acme opens hub"},
    ]
    api.pages["https://news.example/acme-pune-hub"] = page(
        "https://news.example/acme-pune-hub",
        "Acme Freight opens a new Pune warehouse hub",
        f"<p>Acme Freight (fixture) opens a 200,000 sq ft warehouse in Pune.</p>"
        f'<p>More at <a href="https://{ACME_DOMAIN}/news">{ACME_DOMAIN}</a></p>',
    )
    peer_categories = [
        ["Logistics", "Warehousing"],
        ["Logistics", "Freight Service", "Shipping"],
        ["Logistics", "Warehousing"],  # headcount out of band
        ["Airlines", "Logistics"],  # same coarse industry, one shared category: not fair
    ]
    api.companies = [
        {
            "crustdata_company_id": 700100 + i,
            "basic_info": {"name": f"Peer {i} (fixture)"},
            "locations": {"country": "IND", "headquarters": "Mumbai"},
            "headcount": {"total": hc},
            "taxonomy": {"categories": cats},
        }
        for i, (hc, cats) in enumerate(zip([300, 500, 5000, 400], peer_categories, strict=True))
    ] + [{"crustdata_company_id": ACME_ID, "headcount": {"total": 420}, "locations": {}}]


async def _shortlist_case(session, actor: CaseActor) -> Case:
    thesis = Thesis(workspace_id=actor.workspace_id, text="Indian logistics (fixture)")
    session.add(thesis)
    await session.flush()
    dr = DiscoveryRun(workspace_id=actor.workspace_id, thesis_id=thesis.id)
    session.add(dr)
    await session.flush()
    cand = Candidate(
        discovery_run_id=dr.id,
        crustdata_company_id=str(ACME_ID),
        name=ACME,
        domain=ACME_DOMAIN,
        card={"year_founded": 2014},
    )
    session.add(cand)
    discover_run = Run(workspace_id=actor.workspace_id, kind="discover", discovery_run_id=dr.id)
    session.add(discover_run)
    await session.flush()
    await ledger.record_cost(
        session,
        ledger.CostContext(actor.workspace_id, discovery_run_id=dr.id, run_id=discover_run.id),
        provider="crustdata",
        endpoint="/company/search",
        credits=Decimal("30"),
    )
    await session.commit()
    from app.api.cases_service import create_case

    return await create_case(session, actor, CaseCreate(shortlist_item_id=str(cand.id)))


# --- the pipeline -------------------------------------------------------------------


async def test_shortlist_case_confirms_and_builds_profile(session, sm, api) -> None:
    actor = await _actor(session)
    _happy_api(api)
    case = await _shortlist_case(session, actor)
    # identity, profile, registry, events, comparables, then evaluate → request list
    assert await _drain(sm) == 7
    case = await _case(session, case.id)

    assert case.identity_status == "confirmed"
    assert case.crustdata_company_id == str(ACME_ID)
    keys = {k["key"] for k in case.identity_identifiers["keys"]}
    assert keys == {"crustdata_company_id", "domain", "founded_year"}
    run = (await session.execute(select(Run).where(Run.case_id == case.id))).scalar_one()
    assert set((await states(sm, run.id)).values()) == {"done"}

    evidence = list(
        (await session.execute(select(Evidence).where(Evidence.case_id == case.id))).scalars()
    )
    paths = {e.field_path for e in evidence}
    assert {"headcount.total", "headcount.timeseries", "funding.milestones[0]"} <= paths
    assert {"registry.cin", "registry.incorporation_date"} <= paths
    for ev in evidence:
        assert ev.as_of is not None or ev.field_path is None
    founder = next(e for e in evidence if e.field_path == "people.founders")
    assert "email" not in json.dumps(founder.value)  # contact fields never stored
    registry_cin = next(e for e in evidence if e.field_path == "registry.cin")
    assert registry_cin.entity_ref == f"crustdata:founded_year+hq_city:{ACME_ID}"
    assert registry_cin.span == "CIN: U63090PN2014PTC123456"
    # only registry hosts are read
    fetched = [u for body in api.calls("/web/enrich/live") for u in body["urls"]]
    assert "https://randomblog.example/acme" not in fetched
    assert case.identity_identifiers["entity"]["cin"] == "U63090PN2014PTC123456"

    events = list((await session.execute(select(Event).where(Event.case_id == case.id))).scalars())
    assert len(events) == 1 and events[0].kind == "facility"
    assert str(events[0].event_date) == "2026-10-05"
    peers = list(
        (await session.execute(select(Comparable).where(Comparable.case_id == case.id))).scalars()
    )
    assert {p.name for p in peers} == {"Peer 0 (fixture)", "Peer 1 (fixture)"}
    assert peers[0].basis["headcount_band"].startswith("210-840")

    # enrich only by id, never by name or domain
    assert api.calls("/company/enrich") == [
        {"crustdata_company_ids": [ACME_ID], "fields": api.calls("/company/enrich")[0]["fields"]}
    ]


async def test_ambiguous_group_domain_blocks_dependent_steps(session, sm, api) -> None:
    actor = await _actor(session)
    group = "groupco.example"
    api.identify[("domains", group)] = [
        company(11, "GroupCo Logistics (fixture)", group),
        company(12, "GroupCo Warehousing (fixture)", group),
    ]
    from app.api.cases_service import create_case

    case = await create_case(
        session, actor, CaseCreate(name="GroupCo Logistics (fixture)", website=f"https://{group}")
    )
    assert await _drain(sm) == 1
    case = await _case(session, case.id)
    assert case.identity_status == "ambiguous"
    assert case.crustdata_company_id is None
    assert len(case.identity_candidates) == 2
    assert all(c["matching"] for c in case.identity_candidates)
    assert api.calls("/company/enrich") == [] and api.calls("/web/search/live") == []
    steps = (await session.execute(select(Step.key).join(Run).where(Run.case_id == case.id))).all()
    assert [s.key for s in steps] == [IDENTITY]


async def test_manual_pick_recorded_with_evidence_and_user(session, sm, api) -> None:
    actor = await _actor(session)
    group = "groupco.example"
    api.identify[("domains", group)] = [
        company(11, "GroupCo Logistics (fixture)", group),
        company(12, "GroupCo Warehousing (fixture)", group),
    ]
    api.enrich[12] = enrich_record(12, "GroupCo Warehousing (fixture)", group)
    from fastapi import HTTPException

    from app.api.cases_service import create_case, pick_identity

    case = await create_case(
        session, actor, CaseCreate(name="GroupCo Logistics (fixture)", website=group)
    )
    case_id = case.id
    await _drain(sm)
    with pytest.raises(HTTPException) as unknown:
        await pick_identity(session, actor, str(case_id), IdentityPickIn(crustdata_company_id=99))
    assert unknown.value.status_code == 422

    await pick_identity(session, actor, str(case_id), IdentityPickIn(crustdata_company_id=12))
    case = await _case(session, case_id)
    pick = case.identity_identifiers["pick"]
    assert case.identity_status == "confirmed" and case.crustdata_company_id == "12"
    assert case.identity_identifiers["basis"] == "manual"
    assert pick["user_id"] == str(actor.user_id) and pick["display_name"] == "Asha Analyst"
    assert pick["previous_state"] == "ambiguous"
    assert pick["matched_keys"] == ["domain"]
    assert {k["key"] for k in pick["evidence_shown"]["matching"]} >= {"domain"}
    assert {k["key"] for k in pick["evidence_shown"]["differing"]} == {"name"}
    assert pick["evidence_shown"]["other_candidates"] == [11]

    with pytest.raises(HTTPException) as again:
        await pick_identity(session, actor, str(case_id), IdentityPickIn(crustdata_company_id=11))
    assert again.value.status_code == 409

    await _drain(sm)
    assert api.calls("/company/enrich")[0]["crustdata_company_ids"] == [12]
    # a re-run never overrides the person's pick
    from app.api.cases_service import start_verify

    await start_verify(session, actor, str(case_id))
    await _drain(sm)
    case = await _case(session, case_id)
    assert case.crustdata_company_id == "12" and case.identity_identifiers["basis"] == "manual"


async def test_identity_dependent_steps_blocked_while_unresolved(session, sm, api) -> None:
    actor = await _actor(session)
    from app.api.cases_service import create_case

    case = await create_case(session, actor, CaseCreate(name=ACME, website=ACME_DOMAIN))
    await _drain(sm)  # nothing matches → unresolved
    case = await _case(session, case.id)
    assert case.identity_status == "unresolved"
    run = (await session.execute(select(Run).where(Run.case_id == case.id))).scalar_one()
    await append_steps(session, run.id, dependent_steps())
    await session.commit()
    before = len(api.requests)
    assert await _drain(sm) == 4
    assert len(api.requests) == before  # no paid call made
    for key in (PROFILE, REGISTRY, EVENTS, COMPARABLES):
        step = (
            await session.execute(select(Step).where(Step.run_id == run.id, Step.key == key))
        ).scalar_one()
        assert step.output == {"blocked": "identity unresolved"}, key
    assert (
        await session.execute(select(Evidence.id).where(Evidence.case_id == case.id))
    ).first() is None


async def _confirmed_case(session, sm, api, actor) -> Case:
    _happy_api(api)
    api.web = {k: v for k, v in api.web.items() if "CIN" in k}  # registry only
    case = await _shortlist_case(session, actor)
    return case


async def test_event_without_entity_corroboration_rejected(session, sm, api) -> None:
    actor = await _actor(session)
    case = await _confirmed_case(session, sm, api, actor)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    api.web[news_query(terms)] = [{"url": "https://news.example/name-only", "title": "x"}]
    api.pages["https://news.example/name-only"] = page(
        "https://news.example/name-only",
        "Acme Freight raises money",
        "<p>Acme Freight (fixture) raised a large round, reports say.</p>",
    )
    await _drain(sm)
    assert (await session.execute(select(Event).where(Event.case_id == case.id))).first() is None
    ev = (
        await session.execute(
            select(Evidence).where(
                Evidence.case_id == case.id, Evidence.origin_key.startswith("article:")
            )
        )
    ).scalar_one()
    assert ev.entity_ref.startswith("unattached:")
    # visible in Sources as an unattached candidate
    from app.api.cases_sections import build_case_detail

    detail = await build_case_detail(session, actor.workspace_id, await _case(session, case.id))
    src = next(s for s in detail.sources if s.url_or_endpoint == "https://news.example/name-only")
    assert src.attached is False and "corroborating" in src.unattached_reason
    assert detail.events == []


async def test_syndicated_copies_deduplicated(session, sm, api) -> None:
    actor = await _actor(session)
    case = await _confirmed_case(session, sm, api, actor)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    hosts = ["wire-a.example", "wire-b.example", "wire-c.example"]
    api.web[news_query(terms)] = [{"url": f"https://{h}/acme", "title": "x"} for h in hosts]
    for i, host in enumerate(hosts):
        api.pages[f"https://{host}/acme"] = page(
            f"https://{host}/acme",
            f"Acme Freight launches cold-chain service across western India | {host}",
            f"<p>Acme Freight (fixture) launched a cold-chain service.</p><p>{ACME_DOMAIN}</p>",
            published=f"2026-09-0{i + 1}",
        )
    await _drain(sm)
    rows = list(
        (
            await session.execute(
                select(Evidence).where(
                    Evidence.case_id == case.id, Evidence.origin_key.startswith("article:")
                )
            )
        ).scalars()
    )
    assert len(rows) == 3 and len({r.origin_key for r in rows}) == 1
    events = list((await session.execute(select(Event).where(Event.case_id == case.id))).scalars())
    assert len(events) == 1
    assert str(events[0].event_date) == "2026-09-01"  # earliest copy
    assert events[0].kind == "launch"


async def test_company_announcement_recorded_as_announcement(session, sm, api) -> None:
    actor = await _actor(session)
    case = await _confirmed_case(session, sm, api, actor)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    url = f"https://{ACME_DOMAIN}/press/nagpur"
    api.web[news_query(terms)] = [{"url": url, "title": "x"}]
    api.pages[url] = page(
        url,
        "Acme Freight plans to open a Nagpur facility",
        "<p>Acme Freight (fixture) plans to open a Nagpur warehouse facility next year.</p>",
    )
    await _drain(sm)
    event = (await session.execute(select(Event).where(Event.case_id == case.id))).scalar_one()
    assert event.stage == "announced"
    source = (
        await session.execute(select(Source).where(Source.endpoint_or_url == url))
    ).scalar_one()
    assert source.source_class == "company_announcement"


async def test_web_queries_carry_public_terms_only(session, sm, api) -> None:
    actor = await _actor(session)
    _happy_api(api)
    case = await _shortlist_case(session, actor)
    session.add(
        Claim(
            case_id=case.id,
            original_text=CONFIDENTIAL,
            origin="typed",
            category="customer_partnership",
        )
    )
    await session.commit()
    await _drain(sm)
    searches = api.calls("/web/search/live")
    assert len(searches) == 3  # registry, news, news page 2 (one direct hit only)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    allowed = {registry_query(terms), news_query(terms)}
    secret_words = {w.lower() for w in CONFIDENTIAL.split() if len(w) > 3}
    for body in searches:
        assert body["query"] in allowed
        blob = json.dumps(body).lower()
        assert not any(word in blob for word in secret_words), body
        assert set(body) <= {"query", "location", "sources", "page"}


async def test_case_budget_is_150_and_exhaustion_skips_paid_steps(session, sm, api) -> None:
    actor = await _actor(session)
    _happy_api(api)
    from app.api.cases_service import create_case

    case = await create_case(session, actor, CaseCreate(name=ACME, website=ACME_DOMAIN))
    run = (await session.execute(select(Run).where(Run.case_id == case.id))).scalar_one()
    assert case.credit_budget == Decimal(150) and run.budget_credits == Decimal(150)
    worker = make_worker(sm, default_registry)
    assert await worker.run_once()  # identity confirms on domain, the name agrees
    spent = await ledger.spent_credits(session, case_id=case.id)
    await ledger.record_cost(
        session,
        ledger.CostContext(actor.workspace_id, case_id=case.id, run_id=run.id),
        provider="crustdata",
        endpoint="/test/burn",
        credits=Decimal(150) - spent,
    )
    await session.commit()
    await worker.drain()
    final = await states(sm, run.id)
    assert final[IDENTITY] == "done"
    assert {final[k] for k in (PROFILE, REGISTRY, EVENTS, COMPARABLES)} == {"skipped_budget"}
    assert api.calls("/company/enrich") == [] and api.calls("/web/search/live") == []


async def test_cost_shared_from_discovery_not_double_counted(session, sm, api) -> None:
    actor = await _actor(session)
    _happy_api(api)
    case = await _shortlist_case(session, actor)
    await _drain(sm)
    from app.api.cases_sections import build_case_detail

    detail = await build_case_detail(session, actor.workspace_id, await _case(session, case.id))
    assert detail.cost.shared_discovery is not None
    assert detail.cost.shared_discovery.cost.crustdata_credits == 30
    # own spend: identify 0.4 + enrich 2 + registry 1+1 + news 2+1 + search 5 x 0.43
    assert detail.cost.crustdata_credits == pytest.approx(9.55)
    assert detail.cost.credit_budget == 150
    assert sum(line.cost.crustdata_credits for line in detail.cost.by_step) == pytest.approx(9.55)


async def test_case_detail_sections_over_http(session, sm, api, monkeypatch) -> None:
    actor = await _actor(session)
    _happy_api(api)
    case = await _shortlist_case(session, actor)
    await _drain(sm)
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    app = create_app()

    async def actor_dep() -> CaseActor:
        return actor

    async def session_dep():
        async with sm() as s:
            yield s

    app.dependency_overrides[cases_deps.get_case_actor] = actor_dep
    app.dependency_overrides[cases_deps.get_case_session] = session_dep
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as client:
        detail = (await client.get(f"/cases/{case.id}")).json()
        listing = (await client.get("/cases")).json()
        other = await client.get(f"/cases/{case.id.hex[:8]}-0000-0000-0000-000000000000")
    assert other.status_code == 404
    assert detail["identity"]["state"] == "confirmed"
    assert {k["key"] for k in detail["identity"]["keys"]} >= {"domain", "crustdata_company_id"}
    assert all(k["evidence"] for k in detail["identity"]["keys"])
    profile = detail["profile"]
    assert profile["headcount"]["is_estimate"] and profile["headcount"]["estimate_kind"] == "signal"
    assert profile["registry_id"]["value"] == "U63090PN2014PTC123456"
    assert profile["registry_id"]["source"]["source_class"] == "registry_mirror"
    assert profile["funding_rounds"][0]["source"]["source_class"] == "data_provider"
    assert profile["people"][0]["name"] == "Asha Founder (fixture)"
    assert detail["events"][0]["evidence"]["attached_to"]["matched_on"][0] == "domain"
    assert len(detail["comparables"]["companies"]) == 2
    assert detail["comparables"]["basis"]["country"] == "IND"
    # the verify run ends with evaluate → request list, so the case is assessed
    assert detail["case"]["status"] == "assessed"
    assert detail["claims"] == [] and detail["request_list"] is not None
    assert listing[0]["identity_state"] == "confirmed"
    assert listing[0]["cost"]["crustdata_credits"] > 0


async def test_cases_from_other_workspaces_are_not_visible(session, sm, api) -> None:
    actor = await _actor(session)
    other = await _actor(session)
    from app.api.cases_service import create_case, pick_identity

    case = await create_case(session, actor, CaseCreate(name=ACME, website=ACME_DOMAIN))
    with pytest.raises(repo.NotFound):
        await pick_identity(session, other, str(case.id), IdentityPickIn(crustdata_company_id=1))


async def test_redirect_hits_are_never_fetched_and_key_person_corroborates(
    session, sm, api
) -> None:
    """Seen live: many news hits are google.com/goto redirects the fetcher cannot follow.
    They are skipped (one extra news page is searched), and an article naming the
    company and one of its founders is attached on that basis."""
    actor = await _actor(session)
    case = await _confirmed_case(session, sm, api, actor)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    redirect = "https://www.google.com/goto?url=CAESabc"
    direct = "https://paper.example/business/2026-08-14/acme-funding"
    api.web[news_query(terms)] = [{"url": redirect, "title": "x"}, {"url": direct, "title": "y"}]
    api.pages[direct] = page(
        direct,
        "Acme Freight raises growth capital",
        "<p>Acme Freight (fixture) raised a growth round, said co-founder "
        "Asha Founder (fixture).</p>",
        published=None,
    )
    await _drain(sm)
    fetched = [u for body in api.calls("/web/enrich/live") for u in body["urls"]]
    assert redirect not in fetched and direct in fetched
    news_searches = [b for b in api.calls("/web/search/live") if b.get("sources") == ["news"]]
    assert [b.get("page", 1) for b in news_searches] == [1, 2]
    event = (await session.execute(select(Event).where(Event.case_id == case.id))).scalar_one()
    assert str(event.event_date) == "2026-08-14"  # from the URL path
    assert event.kind == "funding"
    ev = await session.get(Evidence, event.evidence_id)
    assert ev.entity_ref == f"crustdata:name+key_person:{ACME_ID}"


async def test_record_news_links_are_read_as_dated_events(session, sm, api) -> None:
    """Enrich `news` (requested in DEFAULT_ENRICH_FIELDS) lists dated article links. The
    profile step passes them on; the events step reads them like search hits and
    attaches only articles that corroborate the entity."""
    from app.clients.crustdata import DEFAULT_ENRICH_FIELDS

    actor = await _actor(session)
    _happy_api(api)
    terms = PublicTerms(name=ACME, domain=ACME_DOMAIN)
    api.web[news_query(terms)] = []  # the news search finds nothing
    url = "https://trade.example/acme-chennai"
    api.enrich[ACME_ID][0]["matches"][0]["company_data"]["news"] = [
        {
            "article_url": url,
            "article_title": "Acme Freight enters Chennai",
            "article_publish_date": "2026-08-14T00:00:00Z",
            "article_publisher_name": "Trade Example",
        },
        {"article_url": "https://news.google.com/rss/x", "article_title": "unreadable"},
    ]
    api.pages[url] = page(
        url,
        "Acme Freight enters Chennai",
        f"<p>Acme Freight (fixture) opens a warehouse in Chennai.</p>"
        f'<p><a href="https://{ACME_DOMAIN}">{ACME_DOMAIN}</a></p>',
        published=None,
    )
    case = await _shortlist_case(session, actor)
    await _drain(sm)
    assert "news" in DEFAULT_ENRICH_FIELDS
    assert "news" in api.calls("/company/enrich")[0]["fields"]
    fetched = [u for body in api.calls("/web/enrich/live") for u in body["urls"]]
    assert url in fetched and "https://news.google.com/rss/x" not in fetched
    [event] = list((await session.execute(select(Event).where(Event.case_id == case.id))).scalars())
    assert str(event.event_date) == "2026-08-14"  # the record's date when the page has none
