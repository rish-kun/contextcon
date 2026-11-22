"""Certification and compliance claims: up to two public lookups (certifier or
registry, then the company's own pages), verbatim facts, validity dates.

The company is the PRD's Pune illustration; every page and certifier record below is
a fixture. Provider clients are fakes; nothing leaves the process.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import ClaimCategory
from app.domain.types import Claim, ClaimComponent
from app.jobs import BudgetExceeded
from app.pipelines.verify.checks.gather import CheckEnv
from app.pipelines.verify.checks.query import PublicTerms, build_lookup
from app.pipelines.verify.checks.sources import EvidenceStore, compliance
from app.pipelines.verify.checks.sources.compliance import claimed_standards, plan
from app.rules.policy import MAX_LOOKUPS_PER_CLAIM as MAX_LOOKUPS
from tests.pipelines.verify.fakes import claim_block, evidence_block
from tests.pipelines.verify.test_checks import (
    CID,
    DOMAIN,
    NAME,
    _case,
    _fact,
    _verify,
    intake_llm,
    pune_crustdata,
)

CLAIM = "We are an ISO/IEC 27001:2022 certified company"
SENTENCES = [(CLAIM, "compliance", [("certification", "ISO/IEC 27001:2022")])]

REGISTRY_URL = "https://www.iafcertsearch.org/certification/pune-warehousing-27001"
TRUST_URL = f"https://{DOMAIN}/trust"
STANDARD_SPAN = "Standard: ISO/IEC 27001:2022"


def registry_hit(expiry: str) -> dict:
    return {
        "title": f"{NAME} - ISO/IEC 27001:2022 certificate",
        "url": REGISTRY_URL,
        "snippet": f"{NAME}, Baner Road, Pune. {STANDARD_SPAN}. Expiry date: {expiry}.",
    }


def registry_page(expiry: str) -> str:
    return (
        f"<html><p>{NAME}</p><p>Address: Baner Road, Pune, Maharashtra</p>"
        f"<p>{STANDARD_SPAN}</p><p>Certification body: Fixture Cert Ltd</p>"
        f"<p>Expiry date: {expiry}</p></html>"
    )


TRUST_HIT = {
    "title": f"Trust and security | {NAME}",
    "url": TRUST_URL,
    "snippet": "We are ISO 27001 certified.",
}
TRUST_PAGE = "<html><p>Trust and security</p><p>We are ISO 27001 certified.</p></html>"


def facts_llm(sentences, *, expiry_iso: str | None = None, expiry_text: str | None = None):
    llm = intake_llm(sentences)

    def facts(system, user):
        text = evidence_block(user)
        comps = claim_block(user)["components"]
        assert "certificate_valid_until" in comps  # the extractor is asked for validity
        found = []
        if STANDARD_SPAN in text:
            found.append(_fact("certification", "ISO/IEC 27001:2022", STANDARD_SPAN))
        if expiry_text and f"Expiry date: {expiry_text}" in text:
            found.append(
                _fact("certificate_valid_until", expiry_iso, f"Expiry date: {expiry_text}")
            )
        if "We are ISO 27001 certified." in text:
            found.append(_fact("certification", "ISO 27001", "We are ISO 27001 certified"))
        return {"speaks_to_claim": bool(found), "facts": found}

    llm.responders["EvidenceFactsDraft"] = facts
    return llm


def searches(crust) -> list[str]:
    return [p["query"] for n, p in crust.calls if n == "web_search"]


@pytest.mark.asyncio
async def test_registry_record_confirms_the_certificate(sm, session):
    case = await _case(session)
    crust = pune_crustdata(
        search_hits={"certificate": [registry_hit("14 March 2028")], "site:": [TRUST_HIT]},
        pages={REGISTRY_URL: registry_page("14 March 2028"), TRUST_URL: TRUST_PAGE},
    )
    llm = facts_llm(SENTENCES, expiry_iso="2028-03-14", expiry_text="14 March 2028")
    _, ledger, _ = await _verify(sm, session, case, SENTENCES, crust, llm)

    out = ledger[CLAIM]
    assert out.status.value == "supported", out.reason
    # The certifier's record answered it: no second lookup was spent.
    assert searches(crust) == [f'"{NAME}" ISO 27001 certificate']
    classes = {e.source.source_class for e in out.evidence if e.quote}
    assert classes == {"counterparty_confirmation"}
    assert all(
        e.quote and e.quote in registry_page("14 March 2028") for e in out.evidence if e.quote
    )


@pytest.mark.asyncio
async def test_company_self_statement_is_partially_corroborated(sm, session):
    case = await _case(session)
    crust = pune_crustdata(search_hits={"site:": [TRUST_HIT]}, pages={TRUST_URL: TRUST_PAGE})
    _, ledger, _ = await _verify(sm, session, case, SENTENCES, crust, facts_llm(SENTENCES))

    out = ledger[CLAIM]
    assert out.status.value == "partially_corroborated", out.reason
    assert searches(crust) == [
        f'"{NAME}" ISO 27001 certificate',
        f'"{NAME}" certified site:{DOMAIN}',
    ]
    assert {e.source.source_class for e in out.evidence if e.quote} == {"company_announcement"}
    assert "announced only" in out.reason
    assert "certificate_valid_until" in out.reason  # validity stays unsettled
    assert "auditor's report under NDA" in (out.settle_with or "")


@pytest.mark.asyncio
async def test_expired_certificate_contradicts_the_claim(sm, session):
    case = await _case(session)
    crust = pune_crustdata(
        search_hits={"certificate": [registry_hit("14 March 2024")]},
        pages={REGISTRY_URL: registry_page("14 March 2024")},
    )
    llm = facts_llm(SENTENCES, expiry_iso="2024-03-14", expiry_text="14 March 2024")
    _, ledger, _ = await _verify(sm, session, case, SENTENCES, crust, llm)

    out = ledger[CLAIM]
    assert out.status.value == "contradicted", out.reason
    assert "certificate_valid_until: contradicted" in out.reason


@pytest.mark.asyncio
async def test_nothing_found_is_cannot_verify_with_the_searches_named(sm, session):
    case = await _case(session)
    crust = pune_crustdata(search_hits={})
    _, ledger, _ = await _verify(sm, session, case, SENTENCES, crust, facts_llm(SENTENCES))

    out = ledger[CLAIM]
    assert out.status.value == "cannot_verify", out.reason
    queries = searches(crust)
    assert len(queries) == MAX_LOOKUPS
    assert "Searched: ISO 27001 certification record" in out.reason
    assert f"the company's trust or security page ({DOMAIN})" in out.reason
    assert "auditor's report under NDA" in (out.settle_with or "")


@pytest.mark.asyncio
async def test_name_only_certifier_page_is_not_attached(sm, session):
    case = await _case(session)
    namesake = {
        "title": f"{NAME} - ISO 27001 certificate",
        "url": "https://www.iafcertsearch.org/certification/namesake",
        "snippet": f"{NAME}, Leeds. {STANDARD_SPAN}.",
    }
    crust = pune_crustdata(search_hits={"certificate": [namesake]})
    _, ledger, _ = await _verify(sm, session, case, SENTENCES, crust, facts_llm(SENTENCES))
    out = ledger[CLAIM]
    assert out.status.value == "cannot_verify"
    assert not [e for e in out.evidence if e.quote]  # read, never evidence


@pytest.mark.asyncio
async def test_no_seller_text_reaches_a_search_provider(sm, session):
    case = await _case(session)
    sentence = (
        "Pune Warehousing is an ISO 9001:2015 and ISO/IEC 27001:2022 certified company "
        "with zero audit findings across our Chakan sites"
    )
    sentences = [
        (sentence, "compliance", [("certification", "ISO 9001:2015 and ISO/IEC 27001:2022")])
    ]
    crust = pune_crustdata(search_hits={})
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, facts_llm(sentences))
    queries = searches(crust)
    assert queries == [
        f'"{NAME}" ISO 9001 ISO 27001 certificate',
        f'"{NAME}" certified site:{DOMAIN}',
    ]
    for query in queries:
        for word in ("zero", "findings", "Chakan", "2015", "2022", "IEC"):
            assert word not in query
    # Each standard is checked on its own.
    assert ledger[sentence].reason.count("certification:") == 2


@pytest.mark.asyncio
async def test_budget_caps_the_lookups(session):
    # Enough for the profile (2) and one search (1): the second lookup is refused,
    # and the claim is still decided on what was read.
    case = await _case(session)
    crust = pune_crustdata(search_hits={})
    spent: list[float] = []

    async def budget(credits: float) -> None:
        if sum(spent) + credits > 3:
            raise BudgetExceeded()
        spent.append(credits)

    env = CheckEnv(
        session=session,
        case=case,
        crustdata=crust,
        llm=facts_llm(SENTENCES),
        budget=budget,
        store=EvidenceStore(session, case.workspace_id, case.id, company_id=CID),
    )
    claim = Claim(
        id="c1",
        text=CLAIM,
        category=ClaimCategory.COMPLIANCE,
        components=[ClaimComponent(name="certification", value="ISO/IEC 27001:2022")],
    )
    out = await compliance.gather(env, claim)
    assert len(searches(crust)) == 1
    assert sum(spent) <= 3
    assert any("budget" in n for n in out.notes)
    assert [e["skipped"] for e in out.searched] == [None, "budget"]


@pytest.mark.asyncio
async def test_never_more_than_two_lookups(sm, session):
    case = await _case(session)
    other = {"title": "Unrelated", "url": "https://elsewhere.example/x", "snippet": "nothing"}
    crust = pune_crustdata(search_hits={"certificate": [other], "site:": [other]})
    await _verify(sm, session, case, SENTENCES, crust, facts_llm(SENTENCES))
    assert len(searches(crust)) == MAX_LOOKUPS


@pytest.mark.asyncio
async def test_no_budget_means_not_checked_and_no_search(sm, session):
    case = await _case(session, budget=Decimal("0"))
    crust = pune_crustdata(search_hits={"certificate": [registry_hit("14 March 2028")]})
    _, ledger, _ = await _verify(sm, session, case, SENTENCES, crust, facts_llm(SENTENCES))
    assert searches(crust) == []
    out = ledger[CLAIM]
    assert out.status.value == "not_checked"


# --- Queries, unit level ---------------------------------------------------------


def _claim(value: str, text: str = "free seller wording") -> Claim:
    return Claim(
        id="c1",
        text=text,
        category=ClaimCategory.COMPLIANCE,
        components=[ClaimComponent(name="certification", value=value)],
    )


def _queries(terms: PublicTerms, claim: Claim) -> list[str]:
    return [
        build_lookup(terms, lk.words, entity=lk.entity, site=lk.site, quote_entity=lk.quote_entity)
        for lk in plan(claim, terms.domain)
    ]


def test_queries_use_public_terms_and_standard_names_only():
    terms = PublicTerms(company_name="Technoforte", domain="technoforte.co.in")
    claim = _claim("ISO 9001:2015 and ISO/IEC 27001:2022", text="Technoforte is great")
    queries = _queries(terms, claim)
    assert queries == [
        '"Technoforte" ISO 9001 ISO 27001 certificate',
        '"Technoforte" certified site:technoforte.co.in',
    ]
    assert len(queries) <= MAX_LOOKUPS


def test_queries_without_a_domain_and_for_soc_cmmi_pci():
    terms = PublicTerms(company_name="Fixture Co")
    assert _queries(terms, _claim("SOC 2 Type II, CMMI Level 5 and PCI DSS")) == [
        '"Fixture Co" SOC 2 CMMI PCI DSS certificate',
        '"Fixture Co" SOC 2 CMMI PCI DSS certified',
    ]


def test_no_standard_means_no_lookup():
    assert plan(_claim("best-in-class security"), "fixture.test") == []
    assert claimed_standards(_claim("best-in-class security")) == []
