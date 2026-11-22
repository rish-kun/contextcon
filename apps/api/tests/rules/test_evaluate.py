from datetime import date, datetime

import pytest

from app.domain import (
    AssessmentInputs,
    BusinessInputs,
    ClaimCategory,
    ClaimCheck,
    ClaimStatus,
    CompanyProfile,
    CompanyRecord,
    CompanyType,
    Criterion,
    CriterionKind,
    CriterionOperator,
    DatedEvent,
    Disposition,
    DocumentType,
    Evidence,
    ExtractedFact,
    FieldFact,
    IdentityStatus,
    NotCheckedReason,
    SeriesPoint,
    Source,
    SourceReliability,
)
from app.rules.company_type import classify_company, criteria_for, required_checks
from app.rules.evaluate import (
    assess,
    business_assessment,
    decide_disposition,
    evidence_sufficiency,
    financial_assessment,
)
from app.rules.fit import opportunity_fit
from tests.rules import prd_fixtures as prd

TODAY = date(2026, 11, 22)
MUST, PREF = CriterionKind.MUST, CriterionKind.PREFERENCE


# --- Company type ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("founded", "headcount", "stage", "expected"),
    [
        (2022, 40, "seed", CompanyType.STARTUP),
        (2019, None, None, CompanyType.STARTUP),
        (2018, "1001-5000", "series_c", CompanyType.STARTUP),  # large but venture-stage
        (2018, "1001-5000", "private equity", CompanyType.ESTABLISHED),
        (2014, 250, "growth", CompanyType.ESTABLISHED),  # the PRD company: 12 years old
        (2005, 30, "seed", CompanyType.ESTABLISHED),
        (None, 900, None, CompanyType.ESTABLISHED),
        (None, "11-50", None, CompanyType.STARTUP),
    ],
)
def test_classify_company(founded, headcount, stage, expected):
    assert classify_company(founded, headcount, stage, TODAY).company_type is expected


def test_criteria_sets_follow_the_prd():
    assert [c.name for c in criteria_for(CompanyType.STARTUP)] == [
        "thesis_fit",
        "founder_relevance",
        "team_development",
        "funding_history",
    ]
    assert [c.name for c in criteria_for(CompanyType.ESTABLISHED)] == [
        "strategic_fit",
        "identity",
        "operating_scale",
        "financial_performance",
        "commercial_position",
        "leadership_continuity",
    ]
    assert ClaimCategory.IDENTITY_INCORPORATION in required_checks(CompanyType.STARTUP)


# --- Fixtures: thesis and company -------------------------------------------------

CRITERIA = [
    Criterion(
        id="geo",
        label="Based in India",
        kind=MUST,
        field="country",
        operator=CriterionOperator.EQ,
        value="India",
    ),
    Criterion(
        id="ind",
        label="Warehousing",
        kind=MUST,
        field="industries",
        operator=CriterionOperator.CONTAINS_ANY,
        value=["warehousing"],
    ),
    Criterion(
        id="own",
        label="Privately held",
        kind=MUST,
        field="ownership",
        operator=CriterionOperator.EQ,
        value="private",
    ),
    Criterion(
        id="ent",
        label="Enterprise customers",
        kind=PREF,
        field="customers",
        operator=CriterionOperator.CONTAINS_ANY,
        value=["enterprise"],
    ),
    Criterion(
        id="exp",
        label="Recent expansion",
        kind=PREF,
        field="expansion",
        operator=CriterionOperator.IS_TRUE,
    ),
]


def ff(v, estimate=False, **kw):
    """A company field bound to the Pune company on its Crustdata id."""
    kw.setdefault("entity_id", prd.COMPANY)
    kw.setdefault("identity_basis", ["crustdata_id"])
    kw.setdefault("evidence_id", "ev-profile")
    return FieldFact(value=v, is_estimate=estimate, **kw)


STRONG = CompanyRecord(
    entity_id=prd.COMPANY,
    name="Illustrative Pune operator",
    fields={
        "country": ff("India"),
        "industries": ff(["Warehousing", "Logistics"]),
        "ownership": ff("private"),
        "customers": ff("enterprise"),
    },
)  # fit 100, assessable 80%

# The PRD illustration, extended: the PRD gives the six claims, their statuses and
# "a request list of three documents". This fixture adds what a full case needs on
# top of that illustration (a thesis with fit, the company profile that makes it an
# established company), so its request list also asks for audited financials.
PRD_INPUTS = AssessmentInputs(
    case_id="case-pune",
    version=1,
    today=TODAY,
    identity_status=IdentityStatus.CONFIRMED,
    profile=CompanyProfile(founded_year=2014, headcount=250, funding_stage="growth"),
    company=STRONG,
    criteria=CRITERIA,
    claim_checks=prd.PRD_CHECKS,
)


# --- The PRD illustration end to end ---------------------------------------------


def test_prd_example_investigate_further_with_four_documents():
    v = assess(PRD_INPUTS)
    j = v.judgments
    assert [o.status for o in v.outcomes].count(ClaimStatus.SUPPORTED) == 3
    assert j.opportunity_fit.fit == 100 and j.opportunity_fit.assessable_pct == 80
    assert v.company_type.company_type is CompanyType.ESTABLISHED
    # identity, location and leadership settled; team size, financials, customers open.
    assert j.evidence_sufficiency.pct == 50
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    assert j.disposition.rule == "evidence_incomplete"
    # The three claim-linked documents are exactly the PRD's.
    claim_docs = [d.document for d in v.requests.documents if d.claim_ids]
    assert claim_docs == [
        "Dated payroll summary",
        "Lease or occupancy evidence for the facility",
        "Lender statements",
    ]
    # Extension of the illustration: an established company also needs financial
    # inputs, so the full list has four documents.
    assert [(d.document, d.claim_ids) for d in v.requests.documents] == [
        ("Dated payroll summary", ["c-employees"]),
        ("Lease or occupancy evidence for the facility", ["c-facility"]),
        ("Lender statements", ["c-debt"]),
        ("Audited financial statements", []),
    ]
    assert any(q.kind == "financial_inputs" for q in v.requests.questions)
    assert v.requests.analyst_questions == []
    assert j.financial.assessed is False


def test_five_judgments_are_separate_and_never_blended():
    j = assess(PRD_INPUTS).judgments
    assert set(type(j).model_fields) == {
        "opportunity_fit",
        "evidence_sufficiency",
        "business",
        "financial",
        "disposition",
    }
    dumped = j.model_dump()
    assert "score" not in dumped and "overall" not in dumped


def test_sufficiency_records_adequacy_separately_from_result():
    v = assess(PRD_INPUTS)
    by = {c.check: c for c in v.judgments.evidence_sufficiency.checks}
    team = by[ClaimCategory.TEAM_SIZE]
    assert team.adequate is False and team.result is ClaimStatus.CANNOT_VERIFY
    assert team.settle_with == ["Dated payroll summary"]
    assert by[ClaimCategory.FINANCIALS].result is None
    assert by[ClaimCategory.LOCATION].adequate is True


# --- Disposition precedence -------------------------------------------------------


def suff(company_type=CompanyType.STARTUP, outcomes=()):
    return evidence_sufficiency(company_type, list(outcomes))


def _fit(fields):
    return opportunity_fit(CRITERIA, CompanyRecord(entity_id="x", name="X", fields=fields))


def test_missing_evidence_never_deprioritises():
    # Nothing assessable at all: cannot assess, not deprioritise.
    d = decide_disposition(IdentityStatus.CONFIRMED, _fit({}), suff(), [])
    assert d.disposition is Disposition.CANNOT_ASSESS
    # Strong fit, every claim unverifiable: investigate further.
    v = assess(
        PRD_INPUTS.model_copy(
            update={
                "claim_checks": [
                    ClaimCheck(
                        claim=c.claim, ran=False, not_run_reason=NotCheckedReason.BUDGET_EXHAUSTED
                    )
                    for c in prd.PRD_CHECKS
                ]
            }
        )
    )
    assert v.disposition is Disposition.INVESTIGATE_FURTHER


def test_identity_uncertain_cannot_assess_even_with_failed_requirement():
    fit = _fit({**STRONG.fields, "country": FieldFact(value="Kenya", evidence_id="e")})
    for status in (IdentityStatus.AMBIGUOUS, IdentityStatus.UNRESOLVED):
        d = decide_disposition(status, fit, suff(), ["Must-have failed: Based in India"])
        assert d.disposition is Disposition.CANNOT_ASSESS
        assert d.rule == "identity_uncertain"


def test_verified_must_fail_deprioritises():
    company = STRONG.model_copy(
        update={"fields": {**STRONG.fields, "ownership": ff("public", evidence_id="e")}}
    )
    v = assess(PRD_INPUTS.model_copy(update={"company": company}))
    assert v.disposition is Disposition.DEPRIORITISE
    assert v.judgments.disposition.rule == "requirement_failed"


def test_poor_fit_on_good_evidence_deprioritises():
    crits = [
        Criterion(
            id=f"p{i}", label=f"P{i}", kind=PREF, field=f"f{i}", operator=CriterionOperator.IS_TRUE
        )
        for i in range(5)
    ]
    company = CompanyRecord(
        entity_id="x",
        name="X",
        fields={f"f{i}": FieldFact(value=(i == 0), evidence_id="e") for i in range(5)},
    )
    fit = opportunity_fit(crits, company)
    assert fit.fit == 20
    d = decide_disposition(IdentityStatus.CONFIRMED, fit, suff(), [])
    assert d.disposition is Disposition.DEPRIORITISE and d.rule == "poor_fit_on_good_evidence"


def test_poor_fit_on_estimates_only_is_not_deprioritised():
    crits = [
        Criterion(
            id=f"p{i}", label=f"P{i}", kind=PREF, field=f"f{i}", operator=CriterionOperator.IS_TRUE
        )
        for i in range(5)
    ]
    company = CompanyRecord(
        entity_id="x",
        name="X",
        fields={
            f"f{i}": FieldFact(value=(i == 0), evidence_id="e", is_estimate=True) for i in range(5)
        },
    )
    d = decide_disposition(IdentityStatus.CONFIRMED, opportunity_fit(crits, company), suff(), [])
    assert d.disposition is Disposition.INVESTIGATE_FURTHER


def _supported_startup_checks():
    """Startup with every required check supported."""
    reg = Source(
        id="reg",
        provider="t",
        label="Registry",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.REGISTRY,
    )
    payroll = Source(
        id="pay",
        provider="t",
        label="Payroll summary",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.SELLER_DOCUMENT,
        document_type=DocumentType.PAYROLL_RECORD,
    )

    def f(id, src, comp, val, quote):
        return ExtractedFact(
            id=id,
            component=comp,
            value=val,
            evidence=Evidence(
                id=f"ev-{id}",
                source=src,
                entity_id=prd.COMPANY,
                quote=quote,
                as_of=date(2026, 10, 31),
                identity_basis=["case_upload"],
            ),
        )

    inc = prd.INCORPORATION
    team = prd.EMPLOYEES.model_copy(
        update={"facts": [f("pay", payroll, "employee_count", 248, "Employees on payroll: 248")]}
    )
    return [inc, team, prd.FOUNDER_HISTORY, prd.FUNDING], reg


def test_prioritise_when_strong_fit_and_checks_satisfied():
    checks, _ = _supported_startup_checks()
    inputs = PRD_INPUTS.model_copy(
        update={
            "profile": CompanyProfile(founded_year=2021, headcount=60, funding_stage="series_a"),
            "claim_checks": checks,
        }
    )
    v = assess(inputs)
    assert v.company_type.company_type is CompanyType.STARTUP
    assert v.judgments.evidence_sufficiency.pct == 100
    assert v.disposition is Disposition.PRIORITISE


def test_conflicting_required_check_blocks_prioritise():
    checks, _ = _supported_startup_checks()
    news = Source(
        id="n",
        provider="t",
        label="News",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.NEWS,
    )
    clash = ExtractedFact(
        id="clash",
        component="round_year",
        value=2024,
        evidence=Evidence(
            id="ev-clash",
            source=news,
            entity_id=prd.COMPANY,
            quote="The company raised its round in 2024",
            identity_basis=["domain"],
        ),
    )
    funding = prd.FUNDING.model_copy(update={"facts": [*prd.FUNDING.facts, clash]})
    inputs = PRD_INPUTS.model_copy(
        update={
            "profile": CompanyProfile(founded_year=2021, headcount=60, funding_stage="series_a"),
            "claim_checks": [*checks[:3], funding],
        }
    )
    v = assess(inputs)
    assert v.outcomes[3].status is ClaimStatus.CONFLICTING_EVIDENCE
    assert v.judgments.opportunity_fit.fit == 100
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    assert any("conflicting" in r.lower() for r in v.judgments.disposition.reasons)


def test_budget_exhaustion_never_prioritises():
    checks, _ = _supported_startup_checks()
    skipped = ClaimCheck(
        claim=prd.FUNDING.claim, ran=False, not_run_reason=NotCheckedReason.BUDGET_EXHAUSTED
    )
    inputs = PRD_INPUTS.model_copy(
        update={
            "profile": CompanyProfile(founded_year=2021, headcount=60, funding_stage="series_a"),
            "claim_checks": [*checks[:3], skipped],
        }
    )
    v = assess(inputs)
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    assert [r.claim_id for r in v.requests.analyst_retries] == ["c-funding"]


# --- Business and financial judgments ---------------------------------------------


def test_business_signals_are_labelled_and_never_revenue():
    b = business_assessment(
        BusinessInputs(
            headcount_series=[
                SeriesPoint(date=date(2025, 10, 1), value=120, evidence_id="h1"),
                SeriesPoint(date=date(2026, 10, 1), value=150, evidence_id="h2"),
            ],
            open_roles=FieldFact(value=12, evidence_id="jobs", as_of=date(2026, 11, 1)),
            locations=[FieldFact(value="Pune", evidence_id="loc")],
            events=[
                DatedEvent(
                    label="Facility announced", date=date(2026, 6, 2), evidence_id="ev-facility"
                )
            ],
        )
    )
    labels = [s.label for s in b.signals]
    assert labels[0] == "Headcount estimate (professional profiles)"
    assert b.signals[1].value == "+25.0%"
    assert all(s.is_signal for s in b.signals)
    assert not any("revenue" in s.label.lower() for s in b.signals)
    assert "never treated as revenue" in b.note


def test_financial_not_assessed_without_reliable_inputs():
    f = financial_assessment([])
    assert not f.assessed and f.reason.startswith("Not assessed")
    seller = Source(
        id="s",
        provider="t",
        label="Seller deck",
        retrieved_at=datetime(2026, 1, 1),
        reliability=SourceReliability.SELLER_STATEMENT,
    )
    deck = ExtractedFact(
        id="rev",
        component="revenue",
        value=5e8,
        evidence=Evidence(id="ev", source=seller, quote="Revenue of 50 crore"),
    )
    assert not financial_assessment([deck]).assessed


def test_financial_assessed_from_audited_statement():
    audited = Source(
        id="a",
        provider="upload",
        label="Audited statements FY26",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.AUDITED_STATEMENT,
    )
    rev = ExtractedFact(
        id="rev",
        component="revenue",
        value=5e8,
        evidence=Evidence(
            id="ev-a",
            source=audited,
            quote="Revenue from operations: 50 crore",
            as_of=date(2026, 3, 31),
            entity_id="co",
            identity_basis=["case_upload"],
        ),
    )
    f = financial_assessment([rev], ["co"])
    assert f.assessed and f.figures[0].evidence_id == "ev-a" and f.assumptions


# --- Determinism ------------------------------------------------------------------


def test_same_inputs_same_assessment():
    a, b = assess(PRD_INPUTS), assess(PRD_INPUTS)
    assert a == b
    assert a.model_dump_json() == b.model_dump_json()
    assert len(a.inputs_hash) == 64


def test_version_number_does_not_change_inputs_hash_but_inputs_do():
    a = assess(PRD_INPUTS)
    b = assess(PRD_INPUTS.model_copy(update={"version": 2}))
    c = assess(PRD_INPUTS.model_copy(update={"identity_status": IdentityStatus.AMBIGUOUS}))
    assert a.inputs_hash == b.inputs_hash != c.inputs_hash


@pytest.mark.parametrize(
    "blocking",
    [ClaimStatus.CONFLICTING_EVIDENCE, ClaimStatus.CONTRADICTED, ClaimStatus.NOT_CHECKED],
)
def test_blocking_required_check_stops_prioritise_even_when_sufficiency_is_high(blocking):
    from app.domain import CheckSufficiency, EvidenceSufficiency

    checks = [
        CheckSufficiency(check=c, adequate=True, result=ClaimStatus.SUPPORTED)
        for c in required_checks(CompanyType.ESTABLISHED)[:5]
    ]
    checks.append(
        CheckSufficiency(
            check=ClaimCategory.CUSTOMER_PARTNERSHIP,
            adequate=blocking is ClaimStatus.CONTRADICTED,
            result=blocking,
        )
    )
    s = EvidenceSufficiency(company_type=CompanyType.ESTABLISHED, pct=83, checks=checks)
    fit = _fit(STRONG.fields)
    d = decide_disposition(IdentityStatus.CONFIRMED, fit, s, [])
    assert d.disposition is Disposition.INVESTIGATE_FURTHER
    ok = s.model_copy(update={"checks": checks[:5]})
    assert decide_disposition(IdentityStatus.CONFIRMED, fit, ok, []).disposition is (
        Disposition.PRIORITISE
    )


# --- Entity guard: financials and fit use the same screened evidence --------------

AUDITED = Source(
    id="aud",
    provider="upload",
    label="Audited statements FY26",
    retrieved_at=datetime(2026, 11, 1),
    reliability=SourceReliability.AUDITED_STATEMENT,
)


def _revenue(entity, basis):
    return ExtractedFact(
        id="rev",
        component="revenue",
        value=5e8,
        evidence=Evidence(
            id="ev-rev",
            source=AUDITED,
            quote="Revenue from operations: 50 crore",
            entity_id=entity,
            identity_basis=basis,
        ),
    )


@pytest.mark.parametrize(
    ("entity_ids", "entity", "basis"),
    [
        (None, prd.COMPANY, ["case_upload"]),  # no entity to attach to
        ([prd.COMPANY], prd.COMPANY, ["name"]),  # name alone
        ([prd.COMPANY], "other-co", ["case_upload"]),  # another company
    ],
)
def test_financial_assessment_does_not_bypass_entity_screening(entity_ids, entity, basis):
    assert not financial_assessment([_revenue(entity, basis)], entity_ids).assessed


def test_assess_screens_financial_facts_against_the_company():
    other = assess(
        PRD_INPUTS.model_copy(update={"financial_facts": [_revenue("other-co", ["cin"])]})
    )
    assert other.judgments.financial.assessed is False
    ours = assess(
        PRD_INPUTS.model_copy(update={"financial_facts": [_revenue(prd.COMPANY, ["cin"])]})
    )
    assert ours.judgments.financial.assessed is True


# --- Fit in a case: recomputed from bound, adequate, undisputed evidence ----------


def _case(fields, **update):
    company = STRONG.model_copy(update={"fields": {**STRONG.fields, **fields}})
    return assess(PRD_INPUTS.model_copy(update={"company": company, **update}))


def _eval(v, cid):
    return next(e for e in v.judgments.opportunity_fit.evaluations if e.criterion_id == cid)


@pytest.mark.parametrize(
    "bad_field",
    [
        FieldFact(value="public", evidence_id="e"),  # no entity binding at all
        ff("public", identity_basis=["name"]),  # name alone
        ff("public", entity_id="another-co"),  # another company's record
    ],
)
def test_unbound_field_is_unknown_never_a_failed_must_have(bad_field):
    v = _case({"ownership": bad_field})
    e = _eval(v, "own")
    assert e.result.value == "unknown"
    assert v.disposition is not Disposition.DEPRIORITISE


def test_field_bound_through_registered_evidence_uses_that_evidence():
    announcement = Source(
        id="pr",
        provider="web",
        label="Announcement",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.COMPANY_ANNOUNCEMENT,
    )
    ev = Evidence(
        id="ev-own",
        source=announcement,
        entity_id=prd.COMPANY,
        quote="We are a listed company",
        identity_basis=["domain"],
    )
    # The field claims a binding, but its evidence is an announcement: not adequate.
    v = _case({"ownership": ff("public", evidence_id="ev-own")}, evidence=[ev])
    assert _eval(v, "own").result.value == "unknown"
    assert v.disposition is not Disposition.DEPRIORITISE


def test_disputed_must_have_is_unknown_not_fail():
    v = _case({"ownership": ff("public", disputed=True)})
    assert _eval(v, "own").result.value == "unknown"
    assert v.disposition is Disposition.INVESTIGATE_FURTHER


def test_conflicting_alternative_values_make_the_criterion_unknown():
    company = STRONG.model_copy(
        update={
            "fields": {**STRONG.fields, "ownership": ff("public")},
            "field_alternatives": {"ownership": [ff("private", evidence_id="ev-other")]},
        }
    )
    v = assess(PRD_INPUTS.model_copy(update={"company": company}))
    assert _eval(v, "own").result.value == "unknown"
    assert v.disposition is Disposition.INVESTIGATE_FURTHER


def test_field_evidence_in_a_conflicting_claim_is_disputed():
    reg = Source(
        id="reg2",
        provider="t",
        label="Registry",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.REGISTRY,
    )
    mirror = Source(
        id="mir",
        provider="t",
        label="Mirror",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.REGISTRY_MIRROR,
    )

    def f(id, src, value, quote):
        return ExtractedFact(
            id=id,
            component="country",
            value=value,
            evidence=Evidence(
                id=f"ev-{id}",
                source=src,
                entity_id=prd.COMPANY,
                quote=quote,
                identity_basis=["cin"],
            ),
        )

    from app.domain import Claim, ClaimComponent

    country_claim = ClaimCheck(
        claim=Claim(
            id="c-country",
            text="An Indian company",
            category=ClaimCategory.LOCATION,
            components=[ClaimComponent(name="country", value="India")],
            entity_ids=[prd.COMPANY],
        ),
        facts=[
            f("kenya", reg, "Kenya", "Country of incorporation: Kenya"),
            f("india", mirror, "India", "Country: India"),
        ],
    )
    # The thesis field "country" rests on the registry evidence that is in dispute.
    v = _case(
        {"country": ff("Kenya", evidence_id="ev-kenya")},
        claim_checks=[*prd.PRD_CHECKS, country_claim],
    )
    assert v.outcomes[-1].status is ClaimStatus.CONFLICTING_EVIDENCE
    assert _eval(v, "geo").result.value == "unknown"
    assert v.disposition is not Disposition.DEPRIORITISE


def test_stale_field_never_triggers_deprioritise():
    v = _case({"ownership": ff("public", as_of=date(2022, 1, 1))})
    e = _eval(v, "own")
    assert e.result.value == "fail" and e.verified is False and "stale" in e.reason
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    fresh = _case({"ownership": ff("public", as_of=date(2026, 6, 1))})
    assert fresh.disposition is Disposition.DEPRIORITISE


# --- Prioritise gate --------------------------------------------------------------


def _startup(checks):
    return PRD_INPUTS.model_copy(
        update={
            "profile": CompanyProfile(founded_year=2021, headcount=60, funding_stage="series_a"),
            "claim_checks": checks,
        }
    )


def test_absent_covered_check_is_a_gap_that_blocks_prioritise():
    checks, _ = _supported_startup_checks()
    v = assess(_startup(checks[:3]))  # no funding claim at all
    funding = next(
        c for c in v.judgments.evidence_sufficiency.checks if c.check is ClaimCategory.FUNDING
    )
    assert funding.result is None and funding.covered_in_v1
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    assert "Required check funding: not claimed and not checked" in v.judgments.disposition.reasons


def test_established_company_prioritises_when_every_covered_check_is_complete():
    checks, _ = _supported_startup_checks()
    v = assess(PRD_INPUTS.model_copy(update={"claim_checks": checks}))
    assert v.company_type.company_type is CompanyType.ESTABLISHED
    by = {c.check: c for c in v.judgments.evidence_sufficiency.checks}
    # Financials and customers are outside v1's checks: listed as gaps, not blocking.
    assert by[ClaimCategory.FINANCIALS].covered_in_v1 is False
    assert by[ClaimCategory.FINANCIALS].gap
    assert v.disposition is Disposition.PRIORITISE


def _contradicted_debt(material=True):
    lender = Source(
        id="lender",
        provider="t",
        label="Lender statement",
        retrieved_at=datetime(2026, 11, 1),
        reliability=SourceReliability.COUNTERPARTY_CONFIRMATION,
    )
    fact = ExtractedFact(
        id="loan",
        component="has_debt",
        value=True,
        evidence=Evidence(
            id="ev-loan",
            source=lender,
            entity_id=prd.COMPANY,
            quote="Outstanding term loan balance: 8.2 crore",
            identity_basis=["cin"],
        ),
    )
    claim = prd.NO_DEBT.claim.model_copy(update={"material": material})
    return ClaimCheck(claim=claim, facts=[fact])


def test_contradicted_material_claim_anywhere_in_the_ledger_blocks_prioritise():
    checks, _ = _supported_startup_checks()
    v = assess(_startup([*checks, _contradicted_debt()]))
    assert v.outcomes[-1].status is ClaimStatus.CONTRADICTED
    # Debt is not a required check, but the claim is material.
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    assert "Material claim c-debt: Contradicted" in v.judgments.disposition.reasons
    immaterial = assess(_startup([*checks, _contradicted_debt(material=False)]))
    assert immaterial.disposition is Disposition.PRIORITISE
