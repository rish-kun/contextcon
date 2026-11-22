"""Public lookups for trademark/IP claims and customer claims.

Provider clients are fakes; nothing leaves the process. The company is the PRD's
illustration (`test_checks.NAME`), not a real company.
"""

from __future__ import annotations

import pytest

from app.pipelines.verify.checks.sources.trademark import clean_mark, register_entry_problem
from tests.pipelines.verify.fakes import claim_block, evidence_block
from tests.pipelines.verify.test_checks import (
    DOMAIN,
    NAME,
    _case,
    _fact,
    _verify,
    intake_llm,
    pune_crustdata,
)

DOC_TRADEMARK = "Trademark registration certificate or IP assignment records"
DOC_CUSTOMER_LIST = "Dated customer list or customer reference letters (under NDA)"

MARK = "PALMS"
TM_SENTENCE = f"{MARK}™ is a registered trademark and Intellectual Property of {NAME}"
TM_COMPONENTS = [("trademark", MARK), ("mark_owner", NAME)]
MIRROR_URL = "https://www.quickcompany.in/trademarks/1234567-palms"
TM_SPAN_MARK = f"Trademark: {MARK}"
TM_SPAN_OWNER = f"Proprietor: {NAME}"
TM_LINES = [
    TM_SPAN_MARK,
    TM_SPAN_OWNER,
    "Address: Baner Road, Pune",
    "Class: 9",
    "Status: Registered",
]
TM_RECORD = "\n".join(TM_LINES)
TM_PAGE = "".join(f"<p>{line}</p>" for line in TM_LINES)
TM_HITS = [
    {"title": f"{MARK} trademark - {NAME}", "url": MIRROR_URL, "snippet": f"{MARK} Class 9"},
    {  # a blog naming the mark and the company: not a register, never its record
        "title": f"Why {MARK} matters",
        "url": "https://blog.example/palms",
        "snippet": f"{MARK} by {NAME}.",
    },
]

CUSTOMER = "Acme Retail"
CUSTOMER_URL = "https://www.acmeretail.com/case-studies/fulfilment"
CUSTOMER_SPAN = f"{CUSTOMER} chose {NAME} of Pune to run its western-region fulfilment"


def _queries(crust) -> list[str]:
    return [p["query"] for n, p in crust.calls if n == "web_search"]


def _no_seller_text(crust, sentence: str, public: set[str]) -> None:
    """No word of the seller's sentence reaches the provider unless it is a public
    term (the confirmed name, the structured mark or customer, fixed words)."""
    allowed = {w.casefold() for w in public}
    assert _queries(crust)
    for query in _queries(crust):
        q = f" {query.casefold().replace('"', ' ')} "
        assert sentence.casefold() not in q
        for word in sentence.replace("™", " ").split():
            w = word.strip(".,+").casefold()
            if len(w) > 3 and w not in allowed:
                assert f" {w} " not in q, (w, query)


def _tm_facts(system: str, user: str) -> dict:
    text = evidence_block(user)
    if claim_block(user)["claim"] == TM_SENTENCE and TM_SPAN_OWNER in text:
        return {
            "speaks_to_claim": True,
            "facts": [
                _fact("trademark", MARK, TM_SPAN_MARK),
                _fact("mark_owner", NAME, TM_SPAN_OWNER),
            ],
        }
    return {"speaks_to_claim": False, "facts": []}


def _customer_facts(marker: str):
    def facts(system: str, user: str) -> dict:
        if marker in evidence_block(user):
            return {"speaks_to_claim": True, "facts": [_fact("counterparty", CUSTOMER, CUSTOMER)]}
        return {"speaks_to_claim": False, "facts": []}

    return facts


# --- Unit ---------------------------------------------------------------------


def test_register_entry_needs_mark_owner_and_class():
    ok = register_entry_problem
    assert ok(TM_RECORD, MARK, NAME) is None
    assert "class" in ok(f"{TM_SPAN_MARK}\n{TM_SPAN_OWNER}\nStatus: Registered", MARK, NAME)
    assert "proprietor" in ok(f"{TM_SPAN_MARK}\nClass 9\nStatus: Registered", MARK, NAME)
    assert ok("", MARK, NAME) == "register page not read"
    assert clean_mark("PALMS\u2122") == "PALMS"


def test_register_entry_rejects_near_misses():
    ok = register_entry_problem
    tail = "Class: 9\nStatus: Registered"
    # The name merely appearing on the page is not the proprietor field.
    assert ok(f"{TM_SPAN_MARK}\n{tail}\nSee also {NAME}", MARK, NAME) is not None
    # A longer proprietor name is another company, even one ending in a field word.
    for suffix in ("Holdings", "Services", "Trademark"):
        other = f"{TM_SPAN_MARK}\nProprietor: {NAME} {suffix}\n{tail}"
        assert ok(other, MARK, NAME) is not None, suffix
    # A previous owner is not the proprietor.
    prev = f"{TM_SPAN_MARK}\nPrevious owner: {NAME}\n{tail}"
    assert ok(prev, MARK, NAME) is not None
    # An application that is not registered does not settle "registered trademark".
    objected = f"{TM_SPAN_MARK}\n{TM_SPAN_OWNER}\nClass: 9\nStatus: Objected"
    assert "not a registered entry" in ok(objected, MARK, NAME)
    # Two entries on one page: the mark and the company's entry must be the same one.
    listing = (
        f"Trademark: OTHERMARK\n{TM_SPAN_OWNER}\n{tail}\n"
        f"Trademark: {MARK}\nProprietor: Someone Else Ltd\n{tail}"
    )
    assert ok(listing, MARK, NAME) is not None
    # A field value followed by the next label on the same line still matches.
    inline = f"{TM_SPAN_MARK}\nProprietor: {NAME}. Class: 9\nStatus: Registered"
    assert ok(inline, MARK, NAME) is None


# --- Trademark ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trademark_mirror_confirms_owner_mark_and_class(sm, session):
    case = await _case(session)
    sentences = [(TM_SENTENCE, "intellectual_property", TM_COMPONENTS)]
    crust = pune_crustdata(search_hits={"trademark": TM_HITS}, pages={MIRROR_URL: TM_PAGE})
    llm = intake_llm(sentences)
    llm.responders["EvidenceFactsDraft"] = _tm_facts
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, llm)

    outcome = ledger[TM_SENTENCE]
    assert outcome.status == "supported"
    assert any(e.source.source_class == "registry_mirror" for e in outcome.evidence)
    assert _queries(crust) == [f'"{NAME}" "{MARK}" trademark']  # one lookup was enough
    assert crust.names().count("fetch_pages") == 1
    _no_seller_text(crust, TM_SENTENCE, {MARK, *NAME.split(), "trademark"})


@pytest.mark.asyncio
async def test_trademark_not_found_cannot_verify_and_asks_for_certificate(sm, session):
    case = await _case(session)
    sentences = [(TM_SENTENCE, "intellectual_property", TM_COMPONENTS)]
    crust = pune_crustdata(search_hits={"trademark": TM_HITS[1:]})  # only the blog
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)

    outcome = ledger[TM_SENTENCE]
    assert outcome.status == "cannot_verify"
    assert _queries(crust) == [
        f'"{NAME}" "{MARK}" trademark',
        f'"{NAME}" "{MARK}" trademark site:quickcompany.in',
    ]
    assert "Searched:" in outcome.reason and "quickcompany.in" in outcome.reason
    assert outcome.settle_with == DOC_TRADEMARK
    _no_seller_text(crust, TM_SENTENCE, {MARK, *NAME.split(), "trademark"})


@pytest.mark.asyncio
async def test_mirror_page_without_a_class_is_not_a_register_entry(sm, session):
    case = await _case(session)
    sentences = [(TM_SENTENCE, "intellectual_property", TM_COMPONENTS)]
    no_class = f"{TM_SPAN_MARK}. {TM_SPAN_OWNER}."
    hit = {**TM_HITS[0], "snippet": f"{MARK} by {NAME}"}
    crust = pune_crustdata(
        search_hits={"trademark": [hit]}, pages={MIRROR_URL: f"<p>{no_class}</p>"}
    )
    llm = intake_llm(sentences)
    llm.responders["EvidenceFactsDraft"] = _tm_facts
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, llm)
    assert ledger[TM_SENTENCE].status == "cannot_verify"


@pytest.mark.asyncio
async def test_mark_read_under_identity_gets_the_register_lookup_and_request(sm, session):
    case = await _case(session)
    sentences = [(TM_SENTENCE, "identity_incorporation", TM_COMPONENTS)]
    crust = pune_crustdata(search_hits={})
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)
    assert ledger[TM_SENTENCE].settle_with == DOC_TRADEMARK
    assert _queries(crust)[0] == f'"{NAME}" "{MARK}" trademark'


@pytest.mark.asyncio
async def test_identity_facts_beside_a_mark_keep_the_registry_check(sm, session):
    """A claim that states a CIN or year as well as a mark is not rerouted: the
    identity components still get the registry and profile check."""
    case = await _case(session)
    sentence = f"{NAME}, incorporated in 2014, owns the {MARK}\u2122 trademark"
    comps = [("trademark", MARK), ("incorporation_year", "2014")]
    sentences = [(sentence, "identity_incorporation", comps)]
    crust = pune_crustdata(search_hits={})
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)
    assert "web_search" not in crust.names()  # no register lookup took its place
    assert "enrich_company" in crust.names()  # the identity check ran
    settle = ledger[sentence].settle_with or ""
    assert DOC_TRADEMARK in settle and "Certificate of incorporation" in settle


# --- Customers ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_named_customer_confirmed_on_its_own_site_is_supported(sm, session):
    """The customer's own site, on hosts known to be its own (the partnership
    module's curated hosts), naming the company with its HQ city."""
    case = await _case(session)
    customer = "Honeywell"
    sentence = f"{customer} is our customer"
    sentences = [(sentence, "customer_partnership", [("counterparty", customer)])]
    url = "https://www.honeywell.com/case-studies/fulfilment"
    span = f"{customer} chose {NAME} of Pune to run its western-region fulfilment"
    hits = [{"title": f"{customer} case study", "url": url, "snippet": span}]
    crust = pune_crustdata(search_hits={"honeywell.com": hits}, pages={url: f"<p>{span}.</p>"})
    llm = intake_llm(sentences)

    def facts(system, user):
        if span in evidence_block(user):
            return {"speaks_to_claim": True, "facts": [_fact("counterparty", customer, customer)]}
        return {"speaks_to_claim": False, "facts": []}

    llm.responders["EvidenceFactsDraft"] = facts
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, llm)

    outcome = ledger[sentence]
    assert outcome.status == "supported"
    assert any(e.source.source_class == "counterparty_confirmation" for e in outcome.evidence)
    assert len(_queries(crust)) <= 2
    _no_seller_text(crust, sentence, {customer, *NAME.split()})


@pytest.mark.asyncio
async def test_lookalike_customer_domain_is_not_the_customers_confirmation(sm, session):
    """A host that only looks like the customer's name is not trusted as its site."""
    case = await _case(session)
    sentence = f"{CUSTOMER} is our customer"
    sentences = [(sentence, "customer_partnership", [("counterparty", CUSTOMER)])]
    hits = [{"title": f"{CUSTOMER} case study", "url": CUSTOMER_URL, "snippet": CUSTOMER_SPAN}]
    crust = pune_crustdata(
        search_hits={CUSTOMER: hits}, pages={CUSTOMER_URL: f"<p>{CUSTOMER_SPAN}.</p>"}
    )
    llm = intake_llm(sentences)
    llm.responders["EvidenceFactsDraft"] = _customer_facts(CUSTOMER_SPAN)
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, llm)

    outcome = ledger[sentence]
    # A customer outside the curated platforms has no public provenance: its name is
    # never sent (private_counterparty), so its pages are never searched at all.
    assert all(CUSTOMER.casefold() not in q.casefold() for q in _queries(crust))
    assert outcome.searched[0].skipped == "private_counterparty"
    assert outcome.status != "supported"
    assert all(e.source.source_class != "counterparty_confirmation" for e in outcome.evidence)
    assert "Searched:" in outcome.reason
    _no_seller_text(crust, sentence, {*CUSTOMER.split(), *NAME.split(), "customer"})


@pytest.mark.asyncio
async def test_customer_count_claim_stays_cannot_verify_and_records_the_search(sm, session):
    case = await _case(session)
    sentence = "Trusted by 100+ clients in 20+ countries"
    comps = [("customer_count", "100"), ("country_count", "20")]
    sentences = [(sentence, "customer_partnership", comps)]
    own_url = f"https://{DOMAIN}/customers"
    hits = [{"title": f"{NAME} customers", "url": own_url, "snippet": f"{CUSTOMER} chose {NAME}."}]
    crust = pune_crustdata(search_hits={"customer case study": hits})
    llm = intake_llm(sentences)
    llm.responders["EvidenceFactsDraft"] = _customer_facts(f"{CUSTOMER} chose")
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, llm)

    outcome = ledger[sentence]
    assert outcome.status == "cannot_verify"
    assert _queries(crust) == [f'"{NAME}" customer case study']
    assert "Searched:" in outcome.reason
    # The named customer found on the company's own site is kept as evidence.
    assert any(e.source.source_class == "company_announcement" for e in outcome.evidence)
    assert outcome.settle_with == DOC_CUSTOMER_LIST
    _no_seller_text(crust, sentence, set(NAME.split()))
