from app.domain import (
    CompanyRecord,
    Criterion,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    FieldFact,
)
from app.rules.fit import assess_candidate, evaluate_criterion, fit_score, shortlist

MUST, PREF = CriterionKind.MUST, CriterionKind.PREFERENCE

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
        id="industry",
        label="Warehousing or supply chain",
        kind=MUST,
        field="industries",
        operator=CriterionOperator.CONTAINS_ANY,
        value=["warehousing", "supply chain"],
    ),
    Criterion(
        id="private",
        label="Privately held",
        kind=MUST,
        field="ownership",
        operator=CriterionOperator.EQ,
        value="private",
    ),
    Criterion(
        id="enterprise",
        label="Serves enterprise customers",
        kind=PREF,
        field="customer_type",
        operator=CriterionOperator.CONTAINS_ANY,
        value=["enterprise"],
    ),
]


def fact(value, ev="ev", estimate=False):
    return FieldFact(value=value, evidence_id=ev, is_estimate=estimate)


def company(**fields):
    return CompanyRecord(entity_id="c1", name="Acme", fields=fields)


FULL = company(
    country=fact("India"),
    industries=fact(["Warehousing", "Logistics"]),
    ownership=fact("Private"),
    customer_type=fact("Enterprise B2B"),
)


def test_all_pass_fit_100():
    a = assess_candidate(CRITERIA, FULL)
    assert not a.excluded
    assert (a.fit.fit, a.fit.assessable_pct) == (100, 100)
    assert a.fit.label == "Fit 100 out of 100, with 100% of the criteria assessable"


def test_unknown_does_not_lower_fit_but_lowers_assessable():
    partial = company(
        country=fact("India"), industries=fact(["Warehousing"]), ownership=fact("Private")
    )
    a = assess_candidate(CRITERIA, partial)
    assert not a.excluded
    assert a.fit.fit == 100
    assert a.fit.assessable_pct == 75
    assert a.unknown_criteria == ["Serves enterprise customers"]


def test_unknown_must_survives_then_verified_fail_after_enrichment_excludes():
    before = company(country=fact("India"), industries=fact(["Warehousing"]))
    a = assess_candidate(CRITERIA, before)
    assert not a.excluded
    assert a.fit.assessable_pct == 50
    # Enrichment reveals the company is listed: the gate re-applies.
    after = company(
        country=fact("India"), industries=fact(["Warehousing"]), ownership=fact("public")
    )
    b = assess_candidate(CRITERIA, after)
    assert b.excluded
    assert b.exclusion_reasons[0].startswith("Must-have failed: Privately held")


def test_weights_must_two_preference_one():
    c = company(
        country=fact("India"),
        industries=fact(["Warehousing"]),
        ownership=fact("Private"),
        customer_type=fact("SMB"),
    )
    a = assess_candidate(CRITERIA, c)
    # 6 of 7 assessable weight.
    assert a.fit.fit == 86


def test_fit_unavailable_when_nothing_assessable():
    a = assess_candidate(CRITERIA, company())
    assert a.fit.fit is None
    assert a.fit.assessable_pct == 0
    assert not a.excluded
    assert a.fit.label.startswith("Fit unavailable")


def test_estimate_fail_of_must_does_not_exclude():
    crit = Criterion(
        id="size",
        label="At least 200 staff",
        kind=MUST,
        field="headcount",
        operator=CriterionOperator.GTE,
        value=200,
    )
    c = company(headcount=fact(140, estimate=True))
    e = evaluate_criterion(crit, c)
    assert e.result is CriterionResult.FAIL and not e.verified
    a = assess_candidate([crit], c)
    assert not a.excluded
    assert a.fit.verified_fit is None


def test_unsourced_value_cannot_exclude():
    crit = CRITERIA[0]
    c = CompanyRecord(entity_id="c", name="X", fields={"country": FieldFact(value="Kenya")})
    assert not assess_candidate([crit], c).excluded


def test_revenue_criterion_with_only_headcount_is_unknown():
    crit = Criterion(
        id="rev",
        label="Revenue above 10 crore",
        kind=PREF,
        field="revenue_inr",
        operator=CriterionOperator.GTE,
        value=1e8,
    )
    e = evaluate_criterion(crit, company(headcount=fact(900, estimate=True)))
    assert e.result is CriterionResult.UNKNOWN


def test_between_and_in_operators():
    between = Criterion(
        id="b",
        label="Founded 2010-2018",
        kind=PREF,
        field="year_founded",
        operator=CriterionOperator.BETWEEN,
        value=[2010, 2018],
    )
    inside = Criterion(
        id="i",
        label="West India",
        kind=PREF,
        field="hq_city",
        operator=CriterionOperator.IN,
        value=["Pune", "Mumbai"],
    )
    c = company(year_founded=fact(2014), hq_city=fact("pune"))
    assert evaluate_criterion(between, c).result is CriterionResult.PASS
    assert evaluate_criterion(inside, c).result is CriterionResult.PASS
    fit, pct = fit_score([between, inside], [evaluate_criterion(x, c) for x in (between, inside)])
    assert (fit, pct) == (100, 100)


def test_ranking_by_fit_then_assessable():
    a = CompanyRecord(entity_id="a", name="A", fields=FULL.fields)  # 100 / 100
    b = CompanyRecord(  # 100 / 75
        entity_id="b",
        name="B",
        fields={k: v for k, v in FULL.fields.items() if k != "customer_type"},
    )
    c = CompanyRecord(  # 86 / 100
        entity_id="c",
        name="C",
        fields={**FULL.fields, "customer_type": fact("SMB")},
    )
    d = CompanyRecord(entity_id="d", name="D", fields={})  # unavailable
    e = CompanyRecord(  # excluded
        entity_id="e", name="E", fields={**FULL.fields, "country": fact("Kenya")}
    )
    s = shortlist(CRITERIA, [d, c, e, b, a])
    assert [x.entity_id for x in s.ranked] == ["a", "b", "c", "d"]
    assert [x.entity_id for x in s.excluded] == ["e"]
