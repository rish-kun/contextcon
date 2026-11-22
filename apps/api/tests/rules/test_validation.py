from datetime import date, datetime

import pytest

from app.domain import Evidence, ExtractedFact, Source, SourceReliability
from app.rules.validation import span_for, validate_extraction

SRC = Source(
    id="s",
    provider="web",
    label="s",
    retrieved_at=datetime(2026, 11, 20),
    reliability=SourceReliability.NEWS,
)


def f(component, value, quote=None, field_path=None, field_value=None):
    ev = Evidence(id="e", source=SRC, quote=quote, field_path=field_path, field_value=field_value)
    return ExtractedFact(id="f", evidence=ev, component=component, value=value)


@pytest.mark.parametrize(
    ("component", "value", "span"),
    [
        ("incorporation_year", 2014, "Date of Incorporation: 12/06/2014"),
        ("incorporation_year", "2014", "incorporated in 2014"),
        ("incorporation_date", date(2014, 6, 12), "Date of Incorporation: 12/06/2014"),
        ("incorporation_date", "2014-06-12", "incorporated on June 12, 2014"),
        ("incorporation_date", "2014-06-12", "incorporated on 12th June 2014"),
        ("event_date", "2026-10", "plans to open in October 2026"),
        ("event_date", "2026-10", "opened on 2026-10-03"),
        ("round_date", "2025-03", "raised in Mar 2025"),
        ("hq_city", "Pune", "Registered office: Baner Road, PUNE, Maharashtra"),
        ("hq_city", "Bengaluru", "headquartered in Bangalore"),
        ("legal_name", "Acme Logistics Pvt Ltd", "ACME LOGISTICS PRIVATE LIMITED"),
        ("employee_count", 246, "Total employees on payroll: 246"),
        ("employee_count", 1250, "headcount of 1,250 staff"),
        ("amount_usd", 12_000_000, "raised $12 million"),
        ("debt_amount", 120_000_000, "term loan of 12 crore"),
        ("role", "Head of Operations", "Head of Operations, National Freight"),
        ("stage", "planned", "The company plans to open a facility"),
        ("stage", "operating", "The facility opened on 3 October"),
    ],
)
def test_value_derivable_from_span(component, value, span):
    check = validate_extraction(f(component, value, quote=span), span)
    assert check.valid, check.reason


@pytest.mark.parametrize(
    ("component", "value", "span"),
    [
        ("incorporation_year", 2014, "Registered office: Pune"),
        ("incorporation_year", 2015, "Date of Incorporation: 12/06/2014"),
        ("incorporation_date", "2014-06-13", "Date of Incorporation: 12/06/2014"),
        ("event_date", "2026-11", "plans to open in October 2026"),
        ("hq_city", "Mumbai", "Registered office: Pune"),
        ("employee_count", 250, "about 140 people on profiles"),
        ("amount_usd", 15_000_000, "raised $12 million"),
        ("person_name", "Ravi Kumar", "The founder previously worked at a logistics firm"),
        ("stage", "operating", "The company plans to open a facility"),
        ("stage", "launched-ish", "The facility opened"),
    ],
)
def test_value_not_in_span_is_rejected(component, value, span):
    check = validate_extraction(f(component, value, quote=span), span)
    assert not check.valid


def test_missing_span_is_rejected():
    assert not validate_extraction(f("hq_city", "Pune", quote="x"), None).valid
    assert not validate_extraction(f("hq_city", "Pune", quote="x"), "   ").valid


def test_missing_value_is_rejected():
    assert not validate_extraction(f("hq_city", None, quote="Pune"), "Pune").valid


def test_structured_field_is_its_own_span():
    fact = f("round_year", 2025, field_path="funding.date", field_value="2025-03-14")
    assert span_for(fact) == "2025-03-14"
    assert validate_extraction(fact, span_for(fact)).valid
    wrong = f("round_year", 2024, field_path="funding.date", field_value="2025-03-14")
    assert not validate_extraction(wrong, span_for(wrong)).valid
