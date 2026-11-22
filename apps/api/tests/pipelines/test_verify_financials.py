"""`verify.financials` end to end: create a case, run every step, read the case detail.

Fake clients only (a real `CrustdataClient` over a mock transport, a regex-scripted LLM).
Companies are fictional."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

import app.pipelines.verify  # noqa: F401 - registers the step handlers
from app.api.cases_deps import CaseActor
from app.api.schemas.cases import CaseCreate
from app.db import repo
from app.db.models import Case, Claim, Evidence, Run
from app.domain.enums import SourceReliability
from app.jobs import StepSpec
from app.jobs import registry as default_registry
from app.jobs.engine import append_steps
from app.pipelines.verify import common
from app.pipelines.verify.common import (
    FINANCIALS,
    ConfirmedEntity,
    PublicTerms,
    registry_query,
)
from app.pipelines.verify.financials import (
    assert_public,
    bind_page,
    financials_query,
    listing_status,
    page_class,
    plan_lookups,
)
from tests.jobs.helpers import make_worker
from tests.pipelines.case_fakes import (
    DEFAULT_RULES,
    FakeCrustdata,
    FakeLlm,
    company,
    enrich_record,
    page,
)

pytestmark = pytest.mark.asyncio

NAME = "Acme Freight (fixture)"
DOMAIN = "acmefreight.example"
CID = 700101
CIN = "U63090PN2014PTC123456"
CONFIDENTIAL = "We secretly hold a 40 crore unannounced contract with BigRetail"

FIN_RULES = [
    ("revenue", r"Revenue from operations[^₹\n]*?(₹[\d,.]+ crore)"),
    ("revenue_from_operations", r"from (₹[\d,.]+ crore) in Q\d FY\d\d"),
    ("net_worth", r"Net worth:?\s*(₹[\d,.]+ crore)"),
]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeCrustdata:
    fake = FakeCrustdata()
    llm = FakeLlm(rules=[*DEFAULT_RULES, *FIN_RULES])
    monkeypatch.setattr(common.clients, "crustdata", fake.factory)
    monkeypatch.setattr(common.clients, "llm", lambda ctx: llm)
    acme = company(CID, NAME, DOMAIN)
    fake.identify[("domains", DOMAIN)] = [acme]
    fake.identify[("names", NAME)] = [acme]
    fake.enrich[CID] = enrich_record(CID, NAME, DOMAIN)
    return fake


def _record(api: FakeCrustdata) -> dict:
    return api.enrich[CID][0]["matches"][0]["company_data"]


def _registry(api: FakeCrustdata) -> None:
    url = "https://www.zaubacorp.com/company/acme"
    api.web[registry_query(PublicTerms(name=NAME, domain=DOMAIN))] = [{"url": url, "title": "x"}]
    api.pages[url] = page(
        url,
        "ACME FREIGHT (FIXTURE) - Company details",
        f"<p>Company Name: {NAME}</p><p>CIN: {CIN}</p><p>Date of Incorporation: 12 March 2014</p>",
        published=None,
    )


async def _run_case(session, sm, *, claim: str | None = None):
    ws = await repo.create_workspace(session, "fin-ws")
    user = await repo.create_user(
        session, ws.id, email=f"a-{ws.id.hex[:6]}@example.test", display_name="Asha Analyst"
    )
    await session.commit()
    actor = CaseActor(workspace_id=ws.id, user_id=user.id, display_name=user.display_name)
    from app.api.cases_service import create_case

    case = await create_case(session, actor, CaseCreate(name=NAME, website=DOMAIN))
    if claim:
        session.add(
            Claim(case_id=case.id, original_text=claim, origin="typed", category="financials")
        )
        await session.commit()
    await make_worker(sm, default_registry).drain()
    return actor, case.id


async def _detail(session, actor, case_id):
    from app.pipelines.memo.detail import build_case_detail

    session.expire_all()
    case = await session.get(Case, case_id)
    return case, await build_case_detail(session, actor.workspace_id, case_id)


async def _financial_rows(session, case_id) -> list[Evidence]:
    rows = await session.execute(
        select(Evidence).where(
            Evidence.case_id == case_id, Evidence.field_path.startswith("financials.")
        )
    )
    return list(rows.scalars())


def _today():
    return datetime.now(UTC).date()


# --- Planning and queries ---------------------------------------------------------


def test_listing_signals():
    assert listing_status({"cin": "L65910MH1945PLC004558"})[::2] == ("listed", "cin")
    assert listing_status({"stock_symbols": ["NSE:ACME"]})[::2] == ("listed", "stock_symbol")
    assert listing_status({"provider_company_type": "Public Company"})[::2] == (
        "listed",
        "company_type",
    )
    assert listing_status({"cin": CIN})[0] == "unlisted"
    assert listing_status({})[0] == "unknown"


def test_binding_needs_an_identifier_not_a_name_or_lookalike():
    entity = ConfirmedEntity(
        crustdata_company_id=CID, name=NAME, domains=(DOMAIN, "acme-old.example"), public_name=NAME
    )
    raw = {"stock_symbols": ["NSE:ACMEFRT", "NSE:AF"]}
    nse = "https://www.nseindia.com/x"
    R = SourceReliability.REGISTRY_MIRROR
    assert bind_page(entity, raw, nse, "", f"{NAME} results", R) == []  # name alone
    assert bind_page(entity, raw, nse, "", f"{NAME} (AF) results", R) == []  # 2-char symbol
    assert bind_page(entity, raw, nse, "", f"{NAME} (ACMEFRT)", R) == ["stock_symbol"]
    news = "https://news.example/x"
    C = SourceReliability.COMPANY_ANNOUNCEMENT
    assert bind_page(entity, raw, news, "", f"{NAME} (ACMEFRT)", C) == []  # symbol off-exchange
    lookalike = f"see https://{DOMAIN}.evil.example/page"
    assert bind_page(entity, raw, news, lookalike, f"{NAME}", C) == []
    assert bind_page(entity, raw, news, f"see https://{DOMAIN}/ir", NAME, C) == ["domain"]
    # Only the primary domain is the company's own site.
    assert page_class(f"https://{DOMAIN}/investors", entity, "results") == C
    assert page_class("https://acme-old.example/investors", entity, "results") is None


def test_at_most_two_lookups():
    for listing in ("listed", "unlisted", "unknown"):
        for india in (True, False):
            for pages in (True, False):
                assert 1 <= len(plan_lookups(listing, india, pages)) <= 2
    assert plan_lookups("listed", True, True) == ["results", "annual"]
    assert plan_lookups("unlisted", True, True) == ["registry_pages", "registry_search"]


def test_queries_carry_public_terms_only():
    terms = PublicTerms(name=NAME, domain=DOMAIN, cin=CIN)
    today = _today()
    for kind in ("results", "annual", "registry_search"):
        assert_public(financials_query(terms, kind, today), terms)
    assert financials_query(terms, "results", today).startswith(f'"{NAME}" quarterly results')
    with pytest.raises(ValueError):
        assert_public(f'"{NAME}" quarterly results revenue BigRetail', terms)


# --- End to end -------------------------------------------------------------------


async def test_listed_company_with_exchange_filing_is_assessed(session, sm, api) -> None:
    _record(api)["revenue"] = {"public_markets": {"stock_symbols": ["NSE:ACMEFRT"]}}
    nse = "https://www.nseindia.com/companies-listing/acmefrt-q2fy27-results"
    query = financials_query(PublicTerms(name=NAME, domain=DOMAIN), "results", _today())
    api.web[query] = [
        {"url": "https://news.example/acme-results", "title": "Acme results"},
        {"url": nse, "title": "ACMEFRT financial results"},
    ]
    api.pages[nse] = page(
        nse,
        "ACMEFRT - Financial Results",
        f"<p>{NAME} (NSE: ACMEFRT)</p>"
        "<p>Revenue from operations for Q2 FY27 at ₹2,095 crore, up from ₹1,690 crore in "
        "Q2 FY26.</p>",
        published=None,
    )
    actor, case_id = await _run_case(session, sm)
    case, detail = await _detail(session, actor, case_id)

    fa = detail.assessment.judgments.financial_assessment
    assert fa.assessed and fa.state == "assessed"
    assert fa.period == "Q2 FY27"
    assert fa.conclusion.startswith("Reported revenue ₹2,095 cr in Q2 FY27, +24% YoY")
    assert "(NSE filing)" in fa.conclusion
    head = fa.figures[0]
    assert head.label == "Revenue" and head.fact.value == "₹2,095 cr" and head.period == "Q2 FY27"
    assert head.basis == "filing" and head.fact.source is not None
    entity = case.identity_identifiers["entity"]["financials"]
    assert entity["listing"] == "listed"
    assert len(entity["searched"]) == 1  # figures found: the second lookup is not spent
    # Only the exchange page was read; the news hit is not a filing.
    fetched = [u for body in api.calls("/web/enrich/live") for u in body["urls"]]
    assert nse in fetched and "https://news.example/acme-results" not in fetched


async def test_private_company_with_registry_mirror_figures(session, sm, api) -> None:
    _registry(api)
    tofler = "https://www.tofler.in/acme-freight/company/U63090PN2014PTC123456"
    terms = PublicTerms(name=NAME, domain=DOMAIN, cin=CIN)
    api.web[financials_query(terms, "registry_search", _today())] = [{"url": tofler, "title": "t"}]
    api.pages[tofler] = page(
        tofler,
        "Acme Freight (fixture) financials",
        f"<p>{NAME} CIN {CIN}</p>"
        "<p>Revenue from operations (FY24): ₹45.2 crore</p><p>Net worth: ₹12 crore</p>",
        published=None,
    )
    actor, case_id = await _run_case(session, sm)
    case, detail = await _detail(session, actor, case_id)

    fa = detail.assessment.judgments.financial_assessment
    assert fa.state == "assessed" and fa.period == "FY24"
    assert fa.conclusion.startswith("Reported revenue ₹45.2 cr in FY24")
    assert "registry filing via tofler.in" in fa.conclusion
    assert {f.label for f in fa.figures} == {"Revenue", "Net worth"}
    searched = case.identity_identifiers["entity"]["financials"]["searched"]
    assert len(searched) == 2 and searched[0].startswith("registry pages already found")
    assert searched[1].startswith(f'web search "{CIN}" "{NAME}"')


async def test_estimates_only_are_shown_as_indicative(session, sm, api) -> None:
    _record(api)["revenue"] = {
        "estimated": {
            "lower_bound_usd": 10_000_000,
            "upper_bound_usd": 50_000_000,
            "timeseries": [{"date": "2026-10-01"}],
        }
    }
    actor, case_id = await _run_case(session, sm)
    _, detail = await _detail(session, actor, case_id)

    fa = detail.assessment.judgments.financial_assessment
    assert not fa.assessed and fa.state == "indicative"
    assert fa.reason.startswith("Indicative (estimate): annual revenue $10M–$50M")
    assert fa.figures[0].fact.is_estimate and fa.figures[0].basis == "estimate"


async def test_nothing_found_lists_what_was_searched(session, sm, api) -> None:
    _registry(api)
    actor, case_id = await _run_case(session, sm)
    case, detail = await _detail(session, actor, case_id)

    fa = detail.assessment.judgments.financial_assessment
    assert fa.state == "not_found" and not fa.assessed
    assert fa.reason.startswith("No public financials found — searched: registry pages already")
    assert len(fa.searched) == 2 and fa.would_need


async def test_no_seller_text_in_financial_queries(session, sm, api) -> None:
    _registry(api)
    await _run_case(session, sm, claim=CONFIDENTIAL)
    secret = {w.lower() for w in CONFIDENTIAL.split() if len(w) > 3}
    terms = PublicTerms(name=NAME, domain=DOMAIN, cin=CIN)
    financial = [
        b
        for b in api.calls("/web/search/live")
        if "revenue" in b["query"] or "results" in b["query"]
    ]
    assert financial
    for body in financial:
        assert_public(body["query"], terms)
        assert not any(w in json.dumps(body).lower() for w in secret), body


async def test_rerun_is_restart_safe(session, sm, api) -> None:
    _registry(api)
    tofler = "https://www.tofler.in/acme-freight/company/U63090PN2014PTC123456"
    terms = PublicTerms(name=NAME, domain=DOMAIN, cin=CIN)
    api.web[financials_query(terms, "registry_search", _today())] = [{"url": tofler, "title": "t"}]
    api.pages[tofler] = page(
        tofler,
        "Acme",
        f"<p>{NAME} CIN {CIN}</p><p>Revenue from operations (FY24): ₹45.2 crore</p>",
        published=None,
    )
    actor, case_id = await _run_case(session, sm)
    before = await _financial_rows(session, case_id)
    case, _ = await _detail(session, actor, case_id)
    searched = case.identity_identifiers["entity"]["financials"]["searched"]

    run = (await session.execute(select(Run).where(Run.case_id == case_id))).scalar_one()
    await append_steps(session, run.id, [StepSpec(f"{FINANCIALS}@2", FINANCIALS)])
    await session.commit()
    await make_worker(sm, default_registry).drain()

    after = await _financial_rows(session, case_id)
    assert sorted(str(e.id) for e in after) == sorted(str(e.id) for e in before)
    case, detail = await _detail(session, actor, case_id)
    assert case.identity_identifiers["entity"]["financials"]["searched"] == searched
    assert detail.assessment.judgments.financial_assessment.state == "assessed"
