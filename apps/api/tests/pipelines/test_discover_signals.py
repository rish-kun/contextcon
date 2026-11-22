"""Derived Discover signals: activity text match, expansion signal, tie-breaks."""

import datetime as dt

from app.domain.enums import CriterionKind, CriterionOperator
from app.domain.types import CompanyRecord, Criterion, FieldFact
from app.pipelines.discover import records, signals
from app.rules import shortlist

ACT = {
    "id": "a",
    "label": "Warehousing and supply-chain software",
    "value": "supply-chain software",
}
TODAY = dt.date(2026, 11, 22)


def f(value, eid="e1"):  # type: ignore[no-untyped-def]
    return {"value": value, "evidence_id": eid}


def test_activity_pass_quotes_the_description():
    facts = {
        "description": f("Acme builds warehouse management software for 3PLs. Founded in Pune.")
    }
    ok, reason, ids = signals.assess_activity(ACT, facts)
    assert ok is True and ids == ["e1"]
    assert '"Acme builds warehouse management software for 3PLs.' in reason


def test_activity_fail_only_on_a_long_contradicting_description():
    text = "Acme is a direct to consumer fashion brand selling apparel and footwear online " * 2
    ok, reason, _ = signals.assess_activity(ACT, {"description": f(text)})
    assert ok is False and "never mentions" in reason


def test_activity_unknown_with_searched_when_text_is_short_or_partial():
    ok, reason, _ = signals.assess_activity(ACT, {"description": f("Acme (fixture).")})
    assert ok is None and "searched" in reason
    ok, reason, _ = signals.assess_activity(
        ACT, {"description": f("Acme runs warehousing for brands across India and more.")}
    )
    assert ok is None and "not the product type" in reason
    ok, reason, _ = signals.assess_activity(ACT, {})
    assert ok is None and "searched" in reason


def _series(a, b):  # type: ignore[no-untyped-def]
    return f(
        [{"date": "2025-11-01", "employee_count": a}, {"date": "2026-11-01", "employee_count": b}],
        "hc",
    )


def test_expansion_signal_from_headcount_series():
    ok, reason, ids = signals.assess_expansion(
        {"headcount.timeseries": _series(100, 115)}, [], enriched=True, today=TODAY
    )
    assert ok is True and "+15%" in reason and "not confirmed expansion" in reason
    assert ids == ["hc"]


def test_expansion_signal_from_open_roles():
    ok, reason, _ = signals.assess_expansion(
        {"hiring.openings_count": f(7, "op")}, [], enriched=True, today=TODAY
    )
    assert ok is True and "7 open roles" in reason


def test_expansion_fails_only_when_both_measured_and_short():
    facts = {"headcount.timeseries": _series(100, 104), "hiring.openings_count": f(2, "op")}
    ok, reason, _ = signals.assess_expansion(facts, [], enriched=True, today=TODAY)
    assert ok is False and "below the thresholds" in reason
    ok, reason, _ = signals.assess_expansion(
        {"headcount.timeseries": _series(100, 104)}, [], enriched=True, today=TODAY
    )
    assert ok is None and "searched" in reason and "open roles" in reason


def test_derived_fail_is_an_estimate_and_never_excludes():
    rc = signals.signal_criterion(
        Criterion(
            id="a",
            label=ACT["label"],
            kind=CriterionKind.MUST,
            field="evidence:industry_activity",
            operator=CriterionOperator.CONTAINS_ANY,
            value="supply-chain software",
            dimension="industry_activity",
        )
    )
    text = "Acme is a direct to consumer fashion brand selling apparel and footwear online " * 2
    d = signals.derive([ACT], [rc], {"description": f(text)})
    rec = records.company_record(1, "Acme", d.facts)
    out = shortlist([rc], [rec])
    assert out.ranked and out.ranked[0].fit.fit == 0


def test_ties_break_on_sourced_signals_then_name():
    c = Criterion(
        id="x", label="x", kind=CriterionKind.MUST, field="k", operator=CriterionOperator.EQ
    )
    recs = [
        CompanyRecord(entity_id=str(i), name=n, fields={"k": FieldFact(value=None)})
        for i, n in ((1, "Alpha"), (2, "Beta"), (3, "Gamma"))
    ]
    ranked = shortlist([c], recs, signals={"3": 4, "2": 1}).ranked
    assert [a.name for a in ranked] == ["Gamma", "Beta", "Alpha"]
    ranked = shortlist([c], recs).ranked
    assert [a.name for a in ranked] == ["Alpha", "Beta", "Gamma"]
