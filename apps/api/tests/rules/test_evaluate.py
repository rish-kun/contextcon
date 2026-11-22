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


def ff(v, estimate=False):
    return FieldFact(value=v, evidence_id="ev-profile", is_estimate=estimate)


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


def test_prd_example_investigate_further_with_three_claim_documents():
    v = assess(PRD_INPUTS)
    j = v.judgments
    assert [o.status for o in v.outcomes].count(ClaimStatus.SUPPORTED) == 3
    assert j.opportunity_fit.fit == 100 and j.opportunity_fit.assessable_pct == 80
    assert v.company_type.company_type is CompanyType.ESTABLISHED
    # identity, location and leadership settled; team size, financials, customers open.
    assert j.evidence_sufficiency.pct == 50
    assert v.disposition is Disposition.INVESTIGATE_FURTHER
    assert j.disposition.rule == "evidence_incomplete"
    claim_docs = [d.document for d in v.requests.documents if d.claim_ids]
    assert claim_docs == [
        "Dated payroll summary",
        "Lease or occupancy evidence for the facility",
        "Lender statements",
    ]
    # An established company also needs financial inputs; asked for separately.
    assert any(q.kind == "financial_inputs" for q in v.requests.questions)
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
        update={
            "fields": {**STRONG.fields, "ownership": FieldFact(value="public", evidence_id="e")}
        }
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
        ),
    )
    f = financial_assessment([rev])
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
