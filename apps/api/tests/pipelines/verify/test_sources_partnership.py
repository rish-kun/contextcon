"""ProofGate source layer: partnership claims search the counterparty's public record.

Fake clients only; the company is the PRD's Pune illustration, not a real company.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Source
from app.jobs import BudgetExceeded
from app.pipelines.verify.checks.gather import (
    CheckEnv,
    Gathered,
    Lookup,
    run_lookups,
    source_kind,
)
from app.pipelines.verify.checks.query import PublicTerms, UnsafeQuery, assert_public, build_lookup
from app.pipelines.verify.checks.run import check_claim, domain_claim
from app.pipelines.verify.checks.sources import EvidenceStore
from app.pipelines.verify.checks.sources.partnership import plan
from tests.pipelines.verify.fakes import claim_block, evidence_block
from tests.pipelines.verify.test_checks import (
    CANARY,
    DOMAIN,
    NAME,
    _case,
    _claims,
    _fact,
    _verify,
    intake_llm,
    pune_crustdata,
)

pytestmark = pytest.mark.asyncio

SENTENCE = "We are a Microsoft partner"
CLAIM = [
    (SENTENCE, "customer_partnership", [("counterparty", "Microsoft"), ("relationship", "partner")])
]
DIRECTORY_URL = "https://partner.microsoft.com/find/pune-warehousing"
DIRECTORY_HIT = {
    "title": f"{NAME} | Microsoft partner directory",
    "url": DIRECTORY_URL,
    "snippet": f"{NAME} ({DOMAIN}) is a Microsoft Solutions Partner.",
}
DIRECTORY_HTML = (
    f"<html><nav>Menu</nav><main><h1>{NAME}</h1><p>Website: {DOMAIN}</p>"
    "<p>Microsoft Solutions Partner for Data and AI (Azure).</p></main></html>"
)
OWN_URL = f"https://{DOMAIN}/partners"
OWN_HIT = {
    "title": f"Partners - {NAME}",
    "url": OWN_URL,
    "snippet": f"{NAME} is a Microsoft partner.",
}


def partner_facts(system: str, user: str) -> dict:
    claim = claim_block(user)["claim"]
    text = evidence_block(user)
    if "Microsoft" not in claim:
        return {"speaks_to_claim": False, "facts": []}
    if "Microsoft Solutions Partner" in text:
        span = "Microsoft Solutions Partner"
    elif "is a Microsoft partner" in text:
        span = "is a Microsoft partner"
    else:
        return {"speaks_to_claim": False, "facts": []}
    return {
        "speaks_to_claim": True,
        "facts": [_fact("counterparty", "Microsoft", span), _fact("relationship", "partner", span)],
    }


def _llm(sentences=CLAIM):
    llm = intake_llm(sentences)
    llm.responders["EvidenceFactsDraft"] = partner_facts
    return llm


async def test_partner_directory_page_on_the_counterparty_domain_supports(sm, session):
    case = await _case(session)
    crust = pune_crustdata(
        search_hits={"site:microsoft.com": [DIRECTORY_HIT], "press release": [OWN_HIT]},
        pages={DIRECTORY_URL: DIRECTORY_HTML},
    )
    _, ledger, _ = await _verify(sm, session, case, CLAIM, crust, _llm())
    out = ledger[SENTENCE]
    assert out.status == "supported", out.reason
    queries = [p["query"] for n, p in crust.calls if n == "web_search"]
    assert queries == [
        f'"{NAME}" site:microsoft.com',
        f'"{NAME}" "Microsoft" partner press release',
    ]
    directory = (
        await session.execute(select(Source).where(Source.endpoint_or_url == DIRECTORY_URL))
    ).scalar_one()
    assert directory.source_class == "counterparty_confirmation"
    assert [s.label for s in out.searched] == [
        "Microsoft partner directory (microsoft.com)",
        "Microsoft partner press releases",
    ]
    assert crust.names().count("fetch_pages") <= 2  # at most one page per lookup


async def test_company_page_alone_is_partially_corroborated_with_searched_sources(sm, session):
    case = await _case(session)
    crust = pune_crustdata(search_hits={"press release": [OWN_HIT]})
    _, ledger, _ = await _verify(sm, session, case, CLAIM, crust, _llm())
    out = ledger[SENTENCE]
    assert out.status == "partially_corroborated", out.reason
    assert "company says it" in out.reason
    assert "Searched: Microsoft partner directory (microsoft.com) (0 results)" in out.reason
    assert out.settle_with == "Customer confirmation or signed contract"
    own = (
        await session.execute(select(Source).where(Source.endpoint_or_url == OWN_URL))
    ).scalar_one()
    assert own.source_class == "company_announcement"
    assert out.searched[0].results == []
    assert out.searched[1].results[0].source_class == "company_announcement"


async def test_namesake_on_the_partner_site_is_not_attached(sm, session):
    """A partner listing that only shares the name, with no domain or HQ city."""
    case = await _case(session)
    namesake = {
        "title": f"{NAME} | Microsoft partner directory",
        "url": DIRECTORY_URL,
        "snippet": f"{NAME}, Leeds. Microsoft Solutions Partner.",
    }
    crust = pune_crustdata(
        search_hits={"site:microsoft.com": [namesake]},
        pages={DIRECTORY_URL: f"<p>{NAME}, Leeds. Microsoft Solutions Partner.</p>"},
    )
    _, ledger, _ = await _verify(sm, session, case, CLAIM, crust, _llm())
    out = ledger[SENTENCE]
    assert out.status == "cannot_verify"
    assert "Searched:" in out.reason
    assert out.searched[0].results[0].attached is False


async def test_seller_words_never_reach_a_partner_lookup(sm, session):
    case = await _case(session, website="https://project-falcon.example")
    case.company_name = CANARY
    await session.commit()
    sentences = [
        (
            f"Under {CANARY} we became a Microsoft Gold partner for our anchor client Zentrix",
            "customer_partnership",
            [("counterparty", "Microsoft"), ("relationship", "Gold partner")],
        ),
        (
            f"{CANARY} Capital is our OEM partner",
            "customer_partnership",
            [("counterparty", f"{CANARY} Capital"), ("relationship", "OEM partner")],
        ),
    ]
    crust = pune_crustdata(search_hits={"site:microsoft.com": [DIRECTORY_HIT]})
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, _llm(sentences))
    searches = [p for n, p in crust.calls if n == "web_search"]
    assert searches
    for params in searches:
        flat = repr(params).casefold()
        for word in ("falcon", "zentrix", "anchor", "gold", "under", "became"):
            assert word not in flat, params
    terms = PublicTerms(company_name=NAME, domain=DOMAIN)
    for params in searches:
        assert_public(
            params["query"],
            terms,
            extra_terms=("Microsoft", "site", "microsoft.com", "partner press release oem"),
        )
    # The code-named counterparty is refused, and the refusal is listed.
    falcon = ledger[sentences[1][0]]
    assert {s.skipped for s in falcon.searched} == {"unsafe_query"}


async def test_query_builder_takes_one_short_public_name():
    terms = PublicTerms(company_name=NAME, domain=DOMAIN)
    assert build_lookup(terms, "partner", entity="Qlik") == f'"{NAME}" "Qlik" partner'
    with pytest.raises(UnsafeQuery):
        build_lookup(terms, "partner", entity="our anchor client, under NDA, since the pilot.")
    with pytest.raises(UnsafeQuery):
        build_lookup(terms, "partner", entity="Falcon Labs", deny=("Project Falcon",))
    with pytest.raises(UnsafeQuery):
        build_lookup(terms, "exclusive strategic", entity="Qlik")


async def test_plan_has_at_most_two_lookups_and_known_partner_sites():
    claim = domain_claim_like(
        "customer_partnership", {"counterparty": "Qlik", "relationship": "OEM partner"}
    )
    lookups = plan(claim)
    assert len(lookups) == 2
    assert lookups[0].site == "qlik.com"
    assert lookups[1].words == "oem partner press release"
    assert source_kind(claim) == "partnership"
    count = domain_claim_like("customer_partnership", {"customer_count": "100"})
    assert source_kind(count) == "customers"


def domain_claim_like(category, components):
    from app.domain.types import Claim, ClaimComponent

    return Claim(
        id="c",
        text="claim",
        category=category,
        components=[ClaimComponent(name=k, value=v) for k, v in components.items()],
    )


# --- Budget ---------------------------------------------------------------------------


async def _env(session, case, crust, llm, budget):
    store = EvidenceStore(
        session, case.workspace_id, case.id, company_id=int(case.crustdata_company_id)
    )
    return CheckEnv(
        session=session, case=case, crustdata=crust, llm=llm, budget=budget, store=store
    )


class CountingBudget:
    """Allows `allow` paid calls of at most `max_each` credits, then refuses."""

    def __init__(self, allow: int):
        self.allow = allow
        self.spent: list[float] = []

    async def __call__(self, credits: float) -> None:
        if len(self.spent) >= self.allow:
            raise BudgetExceeded()
        self.spent.append(credits)


async def test_lookups_are_capped_at_two_and_a_refused_lookup_is_listed(session):
    case = await _case(session)
    llm = _llm()
    [row] = await _claims(session, case, llm, CLAIM)
    crust = pune_crustdata(search_hits={"press release": [OWN_HIT]})
    claim = domain_claim(row)
    three = [Lookup(label=f"lookup {i}", words="partner") for i in range(3)]
    # enrich + one search allowed; the second search is refused by the budget.
    env = await _env(session, case, crust, llm, CountingBudget(allow=2))
    out = Gathered()
    await run_lookups(env, claim, three, out)
    assert len(out.searched) == 2  # never a third
    assert out.searched[0]["skipped"] is None
    assert out.searched[1]["label"] == "lookup 1"
    # Identical queries are one search (memoised), so the second is served free.
    assert crust.names().count("web_search") == 1

    distinct = [
        Lookup(label="one", words="partner"),
        Lookup(label="two", words="customer"),
    ]
    env = await _env(session, case, pune_crustdata(), llm, CountingBudget(allow=2))
    out = Gathered()
    await run_lookups(env, claim, distinct, out)
    assert [e["skipped"] for e in out.searched] == [None, "budget"]


async def test_every_lookup_refused_is_not_checked_budget(session):
    case = await _case(session)
    llm = _llm()
    [row] = await _claims(session, case, llm, CLAIM)
    crust = pune_crustdata()
    meta = await check_claim(
        session,
        claim_row=row,
        case=case,
        crustdata=crust,
        llm=llm,
        budget=CountingBudget(allow=1),  # the profile read only
    )
    assert meta["status"] == "not_checked"
    assert meta["not_checked_reason"] == "budget_exhausted"
    assert "web_search" not in crust.names()


async def test_only_the_partys_own_curated_hosts_count_as_its_record():
    from app.clients.crustdata_models import WebSearchHit
    from app.pipelines.verify.checks.gather import classify_hit, on_party_site

    terms = PublicTerms(company_name=NAME, domain=DOMAIN)
    ms = plan(domain_claim_like("customer_partnership", {"counterparty": "Microsoft"}))[0]
    assert on_party_site("https://partner.microsoft.com/x", ms, terms)
    # Community and forum subdomains carry user content.
    assert not on_party_site("https://techcommunity.microsoft.com/t/post", ms, terms)
    # A marketplace listing is written by the company: its own statement.
    listing = WebSearchHit(
        url="https://appsource.microsoft.com/product/pune",
        title=f"{NAME} WMS",
        snippet=f"Published by {NAME} ({DOMAIN}).",
    )
    att = classify_hit(listing, terms, {}, ms)
    assert att.attached and att.reliability.value == "company_announcement"
    # No host is trusted by name alone: a lookalike domain is cheap.
    tata = plan(domain_claim_like("customer_partnership", {"counterparty": "Tata Steel"}))[0]
    assert tata.party_hosts == ()
    assert not on_party_site("https://www.tatasteel.com/newsroom/x", tata, terms)
    # The company's own site is never the other party.
    own = Lookup(label="x", words="partner", party_hosts=(DOMAIN,))
    assert not on_party_site(f"https://{DOMAIN}/partners", own, terms)
