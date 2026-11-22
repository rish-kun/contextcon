import random
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.domain import (
    Claim,
    ClaimCategory,
    ClaimCheck,
    ClaimComponent,
    ClaimStatus,
    ComponentState,
    DocumentType,
    Evidence,
    ExtractedFact,
    NotCheckedReason,
    Source,
    SourceReliability,
)
from app.rules.claim_status import decide_claim_status
from tests.rules import prd_fixtures as prd

R = SourceReliability
NOW = datetime(2026, 11, 20)


def src(id, reliability, origin=None, label=None, document_type=None):
    return Source(
        id=id,
        provider="test",
        label=label or id,
        retrieved_at=NOW,
        reliability=reliability,
        origin_key=origin,
        document_type=document_type,
    )


def fact(id, source, component, value, quote, entity="co", as_of=None, basis=("crustdata_id",)):
    e = Evidence(
        id=f"ev-{id}",
        source=source,
        entity_id=entity,
        quote=quote,
        as_of=as_of,
        identity_basis=list(basis),
    )
    return ExtractedFact(id=id, evidence=e, component=component, value=value)


def check(category, components, facts, text="claim", entity_ids=("co",), **kw):
    claim = Claim(
        id="c",
        text=text,
        category=category,
        components=[ClaimComponent(name=k, value=v) for k, v in components.items()],
        entity_ids=list(entity_ids),
    )
    return ClaimCheck(claim=claim, facts=facts, **kw)


# --- The PRD illustration, row by row ------------------------------------------


@pytest.mark.parametrize("c", prd.PRD_CHECKS, ids=lambda c: c.claim.id)
def test_prd_illustration_status(c):
    assert decide_claim_status(c).status is prd.PRD_EXPECTED[c.claim.id]


def test_prd_incorporation_supported_by_registry():
    o = decide_claim_status(prd.INCORPORATION)
    assert o.settle_with == []
    assert {f.state for f in o.components} == {ComponentState.MATCHED}


def test_prd_250_employees_cannot_verify_with_payroll_request():
    o = decide_claim_status(prd.EMPLOYEES)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.settle_with == ["Dated payroll summary"]
    assert "signal, not a payroll count" in o.reason
    assert [r.role for r in o.evidence] == ["not_adequate"]


def test_prd_founder_supported_by_professional_record():
    o = decide_claim_status(prd.FOUNDER_HISTORY)
    assert o.status is ClaimStatus.SUPPORTED
    assert any(r.role == "related" for r in o.evidence)  # start year shown, not decisive


def test_prd_funding_supported_and_announcement_not_decisive():
    o = decide_claim_status(prd.FUNDING)
    decisive = {r.evidence_id for r in o.evidence if r.role == "decisive"}
    assert decisive == {"ev-funding", "ev-funding-type"}
    assert any(r.evidence_id == "ev-funding-pr" and r.role == "not_adequate" for r in o.evidence)
    rt = next(f for f in o.components if f.component == "round_type")
    assert rt.state is ComponentState.MATCHED


def test_prd_facility_partially_corroborated_lease_request():
    o = decide_claim_status(prd.FACILITY)
    states = {f.component: f.state for f in o.components}
    assert states == {
        "event": ComponentState.MATCHED,
        "event_date": ComponentState.UNSETTLED,
        "stage": ComponentState.UNSETTLED,
    }
    assert o.settle_with == ["Lease or occupancy evidence for the facility"]
    assert "announced it, not that it happened" in o.reason


def test_prd_no_debt_cannot_verify_with_charge_caveat():
    o = decide_claim_status(prd.NO_DEBT)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.settle_with == ["Lender statements"]
    assert "security was given, not that money is owed" in o.reason
    assert [r.role for r in o.evidence] == ["related"]


# --- Precedence and edge cases --------------------------------------------------


def test_not_checked_requires_reason():
    claim = prd.EMPLOYEES.claim
    with pytest.raises(ValidationError):
        ClaimCheck(claim=claim, ran=False)


def test_not_checked_carries_reason_and_what_would_settle():
    c = ClaimCheck(
        claim=prd.EMPLOYEES.claim,
        ran=False,
        not_run_reason=NotCheckedReason.BUDGET_EXHAUSTED,
        not_run_detail="case budget of 150 credits reached",
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.NOT_CHECKED
    assert o.not_checked_reason is NotCheckedReason.BUDGET_EXHAUSTED
    assert o.analyst_retry
    assert "budget exhausted" in o.reason and "150 credits" in o.reason
    assert o.settle_with == ["Dated payroll summary"]


def test_contradicted_by_registry_year():
    reg = src("reg", R.REGISTRY)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2012},
        [fact("f", reg, "incorporation_year", 2014, "Date of incorporation 12/06/2014")],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CONTRADICTED
    assert o.settle_with == ["Certificate of incorporation"]


def test_registry_and_mirror_that_disagree_are_conflicting_not_ranked_away():
    official = src("official", R.REGISTRY)
    mirror = src("mirror", R.REGISTRY_MIRROR)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014},
        [
            fact("a", official, "incorporation_year", 2014, "Incorporated on 12 June 2014"),
            fact("b", mirror, "incorporation_year", 2015, "Incorporation year 2015"),
        ],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CONFLICTING_EVIDENCE
    assert {r.evidence_id for r in o.evidence if r.role == "decisive"} == {"ev-a", "ev-b"}


def test_adequate_origins_that_conflict_with_each_other_are_conflicting():
    # Both disagree with the claim, and with each other.
    official = src("official", R.REGISTRY)
    mirror = src("mirror", R.REGISTRY_MIRROR)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2012},
        [
            fact("a", official, "incorporation_year", 2014, "Incorporated on 12 June 2014"),
            fact("b", mirror, "incorporation_year", 2015, "Incorporation year 2015"),
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.CONFLICTING_EVIDENCE


def test_adequate_origins_that_agree_against_the_claim_contradict():
    official = src("official", R.REGISTRY)
    mirror = src("mirror", R.REGISTRY_MIRROR)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2012},
        [
            fact("a", official, "incorporation_year", 2014, "Incorporated on 12 June 2014"),
            fact("b", mirror, "incorporation_year", 2014, "Incorporation year 2014"),
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.CONTRADICTED


def test_conflicting_sources_of_equal_authority():
    db = src("db", R.DATA_PROVIDER)
    news = src("news", R.NEWS)
    c = check(
        ClaimCategory.FUNDING,
        {"round_year": 2025},
        [
            fact("a", db, "round_year", 2025, "Funding date 2025-02-01"),
            fact("b", news, "round_year", 2024, "The company raised its round in 2024"),
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.CONFLICTING_EVIDENCE


def test_conflicting_outranks_contradicted_and_partial_in_compound_claims():
    reg = src("reg", R.REGISTRY)
    db = src("db", R.DATA_PROVIDER)
    mirror = src("mirror", R.REGISTRY_MIRROR)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2012, "country": "India"},
        [
            fact("a", reg, "incorporation_year", 2014, "Incorporated 2014"),
            fact("b", db, "country", "India", "Country: India"),
            fact("c", mirror, "country", "Singapore", "Registered in Singapore"),
        ],
    )
    o = decide_claim_status(c)
    states = {f.component: f.state for f in o.components}
    assert states["incorporation_year"] is ComponentState.CONTRADICTED
    assert states["country"] is ComponentState.CONFLICTING
    assert o.status is ClaimStatus.CONFLICTING_EVIDENCE


def test_syndicated_copies_count_as_one_origin_and_do_not_upgrade_announcement():
    # A press release saying the facility is operating, republished by three news sites.
    pr = src("pr", R.COMPANY_ANNOUNCEMENT, origin="press-release-1")
    copies = [src(f"news{i}", R.NEWS, origin="press-release-1") for i in range(3)]
    quote = "Our new warehouse facility in Chakan opened and is now operating since October 2026"
    facts = [fact("pr-stage", pr, "stage", "operating", quote)]
    facts += [fact(f"n{i}-stage", s, "stage", "operating", quote) for i, s in enumerate(copies)]
    facts += [fact("pr-event", pr, "event", "warehouse facility", quote)]
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event": "facility", "stage": "operating"},
        facts,
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.PARTIALLY_CORROBORATED
    stage = next(f for f in o.components if f.component == "stage")
    assert stage.state is ComponentState.UNSETTLED


def test_independent_news_settles_operating_stage():
    pr = src("pr", R.COMPANY_ANNOUNCEMENT, origin="press-release-1")
    news = src("indep", R.NEWS, origin="newsroom-story")
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event": "facility", "event_date": "2026-10", "stage": "operating"},
        [
            fact("pr-event", pr, "event", "warehouse facility", "plans a warehouse facility"),
            fact(
                "n-event",
                news,
                "event",
                "warehouse facility",
                "The warehouse facility in Chakan opened on 3 October 2026",
            ),
            fact(
                "n-date",
                news,
                "event_date",
                "2026-10-03",
                "The warehouse facility in Chakan opened on 3 October 2026",
            ),
            fact(
                "n-stage",
                news,
                "stage",
                "operating",
                "The warehouse facility in Chakan opened on 3 October 2026",
            ),
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.SUPPORTED


def test_planned_stage_after_claimed_date_contradicts():
    news = src("news", R.NEWS)
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event_date": "2026-10", "stage": "operating"},
        [
            fact(
                "s",
                news,
                "stage",
                "planned",
                "The facility is still planned, with no date set",
                as_of=date(2026, 11, 15),
            ),
        ],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CONTRADICTED


def test_planned_stage_before_claimed_date_is_not_a_contradiction():
    news = src("news", R.NEWS)
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event_date": "2026-10", "stage": "operating"},
        [fact("s", news, "stage", "planned", "The facility is planned", as_of=date(2026, 6, 1))],
    )
    assert decide_claim_status(c).status is ClaimStatus.CANNOT_VERIFY


def test_adequate_source_read_but_silent_is_cannot_verify():
    reg = src("reg", R.REGISTRY, label="Registry record")
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014},
        [],
        sources_read=[reg],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert "Registry record was read and does not state it" in o.reason
    assert o.settle_with == ["Certificate of incorporation"]


def test_profile_headcount_never_supports_even_when_equal():
    prof = src("p", R.PROFESSIONAL_PROFILE_SIGNAL)
    provider = src("d", R.DATA_PROVIDER)
    c = check(
        ClaimCategory.TEAM_SIZE,
        {"employee_count": 250},
        [
            fact("a", prof, "employee_count", 250, "250 employees on profiles"),
            fact("b", provider, "employee_count", 250, "Headcount: 250"),
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.CANNOT_VERIFY


PAYROLL_QUOTE = "Total employees on payroll, 30 Sep 2026: 246"


def test_payroll_summary_supports_within_tolerance():
    payroll = src("payroll", R.SELLER_DOCUMENT, document_type=DocumentType.PAYROLL_RECORD)
    c = check(
        ClaimCategory.TEAM_SIZE,
        {"employee_count": 250},
        [
            fact(
                "a",
                payroll,
                "employee_count",
                246,
                PAYROLL_QUOTE,
                as_of=date(2026, 9, 30),
                basis=("case_upload",),
            )
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.SUPPORTED


@pytest.mark.parametrize(
    ("document_type", "as_of", "why"),
    [
        (None, date(2026, 9, 30), "generic document"),
        (DocumentType.PITCH_DECK, date(2026, 9, 30), "pitch_deck"),
        (DocumentType.PAYROLL_RECORD, None, "must be dated"),
    ],
)
def test_generic_or_undated_seller_doc_cannot_settle_payroll(document_type, as_of, why):
    doc = src("doc", R.SELLER_DOCUMENT, document_type=document_type)
    c = check(
        ClaimCategory.TEAM_SIZE,
        {"employee_count": 250},
        [fact("a", doc, "employee_count", 246, PAYROLL_QUOTE, as_of=as_of, basis=("case_upload",))],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.settle_with == ["Dated payroll summary"]
    assert why in o.evidence[0].note


def test_lender_statement_contradicts_no_debt():
    lender = src("lender", R.COUNTERPARTY_CONFIRMATION)
    c = check(
        ClaimCategory.DEBT_SECURITY,
        {"has_debt": False},
        [fact("a", lender, "has_debt", True, "Outstanding term loan balance: 8.2 crore")],
    )
    assert decide_claim_status(c).status is ClaimStatus.CONTRADICTED


def test_rejected_fact_cannot_drive_status():
    reg = src("reg", R.REGISTRY)
    # The model "extracted" 2014, but the quote says nothing about it.
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014},
        [fact("a", reg, "incorporation_year", 2014, "Registered office: Pune")],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.evidence[0].role == "rejected"


def test_fact_attached_on_name_alone_is_rejected():
    reg = src("reg", R.REGISTRY)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014},
        [fact("a", reg, "incorporation_year", 2014, "Incorporated 2014", basis=("name",))],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.evidence[0].role == "rejected"
    assert "name alone" in o.evidence[0].note


def test_claim_without_corroborated_entity_accepts_no_facts():
    reg = src("reg", R.REGISTRY)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014},
        [fact("a", reg, "incorporation_year", 2014, "Incorporated 2014")],
        entity_ids=(),
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.NOT_CHECKED
    assert o.not_checked_reason is NotCheckedReason.IDENTITY_UNRESOLVED
    assert [r.role for r in o.evidence] == ["rejected"]


def test_fact_about_another_entity_is_rejected():
    reg = src("reg", R.REGISTRY)
    c = check(
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014},
        [fact("a", reg, "incorporation_year", 2014, "Incorporated 2014", entity="other-co")],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert "not to the entity" in o.evidence[0].note


def test_customer_claim_needs_counterparty_not_announcement():
    pr = src("pr", R.COMPANY_ANNOUNCEMENT)
    c = check(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        {"counterparty": "Big Retail"},
        [fact("a", pr, "counterparty", "Big Retail", "We now serve Big Retail")],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.settle_with == ["Customer confirmation or signed contract"]


def test_every_non_supported_status_names_what_would_settle_it():
    for c in prd.PRD_CHECKS:
        o = decide_claim_status(c)
        assert (o.status is ClaimStatus.SUPPORTED) == (o.settle_with == [])


def test_fact_order_does_not_change_outcome():
    base = decide_claim_status(prd.FUNDING)
    facts = list(prd.FUNDING.facts)
    random.Random(7).shuffle(facts)
    shuffled = prd.FUNDING.model_copy(update={"facts": facts})
    assert decide_claim_status(shuffled) == base


# --- Question-specific proof ----------------------------------------------------

OPENED = "We opened a new facility in October 2026"


def test_opening_claim_without_stage_is_partial_on_announcement_only():
    pr = src("pr", R.COMPANY_ANNOUNCEMENT, label="Company announcement")
    quote = "We are pleased to announce our new warehouse facility in Chakan, October 2026"
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event": "facility"},
        [fact("pr-event", pr, "event", "warehouse facility", quote, basis=("domain",))],
        text=OPENED,
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.PARTIALLY_CORROBORATED
    by = {f.component: f for f in o.components}
    assert by["stage"].state is ComponentState.UNSETTLED  # occurrence is required
    assert by["event"].announcement_only is True
    assert by["event"].provenance == [R.COMPANY_ANNOUNCEMENT]
    assert "announced only" in o.reason
    decisive = next(r for r in o.evidence if r.role == "decisive")
    assert "not that it happened" in decisive.note


def test_seller_deck_cannot_prove_an_event_happened():
    deck = src("deck", R.SELLER_DOCUMENT, document_type=DocumentType.PITCH_DECK)
    quote = "Our new warehouse facility in Chakan opened in October 2026"
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event": "facility", "event_date": "2026-10", "stage": "operating"},
        [
            fact("d-event", deck, "event", "warehouse facility", quote, basis=("case_upload",)),
            fact("d-date", deck, "event_date", "2026-10", quote, basis=("case_upload",)),
            fact("d-stage", deck, "stage", "operating", quote, basis=("case_upload",)),
        ],
        text=OPENED,
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.settle_with == ["Lease or occupancy evidence for the facility"]


def test_occupancy_evidence_proves_operation():
    occ = src("occ", R.SELLER_DOCUMENT, document_type=DocumentType.OCCUPANCY_EVIDENCE)
    quote = "Occupancy certificate: warehouse facility at Chakan, operational from 3 October 2026"
    c = check(
        ClaimCategory.DATED_EVENT,
        {"event": "facility", "event_date": "2026-10", "stage": "operating"},
        [
            fact("o-event", occ, "event", "warehouse facility", quote, basis=("case_upload",)),
            fact("o-date", occ, "event_date", "2026-10-03", quote, basis=("case_upload",)),
            fact("o-stage", occ, "stage", "operating", quote, basis=("case_upload",)),
        ],
        text=OPENED,
    )
    assert decide_claim_status(c).status is ClaimStatus.SUPPORTED


def test_term_sheet_does_not_prove_a_completed_round():
    ts = src("ts", R.SELLER_DOCUMENT, document_type=DocumentType.TERM_SHEET)
    quote = "Term sheet dated 2 February 2025 for a growth funding round"
    c = check(
        ClaimCategory.FUNDING,
        {"raised": True, "round_year": 2025},
        [
            fact("t-raised", ts, "raised", True, quote, basis=("case_upload",)),
            fact("t-year", ts, "round_year", 2025, quote, basis=("case_upload",)),
        ],
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert o.settle_with == [
        "Share allotment filing, closing statement or bank receipt of the funds"
    ]


def test_share_allotment_proves_a_completed_round():
    allot = src("allot", R.SELLER_DOCUMENT, document_type=DocumentType.SHARE_ALLOTMENT)
    quote = "Allotment of 1,20,000 equity shares on 14 March 2025 against growth funding received"
    c = check(
        ClaimCategory.FUNDING,
        {"raised": True, "round_year": 2025},
        [
            fact("a-raised", allot, "raised", True, quote, basis=("case_upload",)),
            fact("a-year", allot, "round_year", 2025, quote, basis=("case_upload",)),
        ],
    )
    assert decide_claim_status(c).status is ClaimStatus.SUPPORTED


# --- Pune negatives: the qualifiers decide ---------------------------------------


def _founder_with(employer_quote, *, basis=("crustdata_id",), scope_value=None):
    employer_ev = prd.ev(
        "ev-employer-alt",
        prd.EMPLOYER_RECORD,
        quote=employer_quote,
        entity=prd.EMPLOYER,
        basis=basis,
    )
    facts = [f for f in prd.FOUNDER_HISTORY.facts if f.evidence.id != "ev-employer"]
    facts.append(prd.fact("f-alt-industry", employer_ev, "employer_industry", "logistics"))
    if scope_value:
        facts.append(prd.fact("f-alt-scope", employer_ev, "employer_scope", scope_value))
    return prd.FOUNDER_HISTORY.model_copy(update={"facts": facts})


def test_founder_at_a_regional_firm_is_contradicted():
    c = _founder_with(
        "National Freight Logistics Ltd is a regional logistics firm in Maharashtra.",
        scope_value="regional",
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.CONTRADICTED
    scope = next(f for f in o.components if f.component == "employer_scope")
    assert scope.state is ComponentState.CONTRADICTED


def test_national_in_the_employer_name_is_not_evidence_of_national_scope():
    c = _founder_with("National Freight Logistics Ltd provides logistics services.")
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.PARTIALLY_CORROBORATED
    scope = next(f for f in o.components if f.component == "employer_scope")
    assert scope.state is ComponentState.UNSETTLED


def test_employer_record_bound_by_name_only_is_rejected():
    c = _founder_with(
        "National Freight Logistics Ltd is a national logistics firm with warehouses in 22 states.",
        basis=("name",),
        scope_value="national",
    )
    o = decide_claim_status(c)
    assert o.status is ClaimStatus.PARTIALLY_CORROBORATED
    assert {r.evidence_id for r in o.evidence if r.role == "rejected"} == {"ev-employer-alt"}


def test_seed_round_contradicts_growth_funding():
    seed_ev = prd.ev(
        "ev-funding-seed",
        prd.FUNDING_DB,
        field_path="funding_milestones[0].funding_round",
        field_value="Seed",
        as_of=date(2025, 3, 14),
    )
    facts = [f for f in prd.FUNDING.facts if f.id != "f-fund-type"]
    facts.append(prd.fact("f-fund-seed", seed_ev, "round_type", "Seed"))
    o = decide_claim_status(prd.FUNDING.model_copy(update={"facts": facts}))
    assert o.status is ClaimStatus.CONTRADICTED


def test_announcement_alone_does_not_support_the_funding_claim():
    facts = [f for f in prd.FUNDING.facts if f.evidence.id == "ev-funding-pr"]
    o = decide_claim_status(prd.FUNDING.model_copy(update={"facts": facts}))
    assert o.status is ClaimStatus.CANNOT_VERIFY
    assert "announced it, not that it happened" in o.reason
