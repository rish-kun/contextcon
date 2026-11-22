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


# --- Typed parsing: tokens, sign, scale, unit, currency, precision, polarity -----


@pytest.mark.parametrize(
    ("component", "value", "span", "why"),
    [
        # Complete tokens only: 250 is not read inside 1250 or 1,250.
        ("employee_count", 250, "headcount of 1250 staff", "not in the span"),
        ("employee_count", 250, "headcount of 1,250 staff", "not in the span"),
        ("employee_count", 250, "a ratio of 12.250", "not in the span"),
        # Scale is kept: "5 million" is not 5.
        ("amount_usd", 5, "raised $5 million", "as stated"),
        ("employee_count", 12, "12 crore in turnover", "as stated"),
        # Sign is kept.
        ("revenue_growth_pct", 12, "revenue growth of -12% in FY25", "as stated"),
        # A percentage is not a count, and a count needs no percent sign.
        ("employee_count", 18, "headcount grew 18%", "as stated"),
        ("headcount_growth_pct", 18, "headcount grew by 18 people", "as stated"),
        # Currency is kept.
        ("amount_usd", 12_000_000, "raised ₹12 million", "as stated"),
        # No comparison tolerance in extraction validation.
        ("employee_count", 246, "Total employees on payroll: 250", "not in the span"),
        ("amount_usd", 12_100_000, "raised $12 million", "not in the span"),
        # Invented precision fails when the source gives only the year.
        ("event_date", "2026-10", "the facility will open in 2026", "not in the span"),
        ("incorporation_date", "2014-06-12", "incorporated in 2014", "not in the span"),
        ("round_date", "2025-03-14", "raised in March 2025", "not in the span"),
        ("incorporation_date", date(2014, 1, 1), "incorporated in 2014", "not in the span"),
        # Yes/no polarity.
        ("has_debt", True, "We have no debt", "negative"),
        ("has_debt", False, "Outstanding term loan balance: 8.2 crore", "negative"),
        ("raised", True, "The company has not raised external funding", "negative"),
        ("has_debt", True, "The company is debt-free", "negative"),
        # Stage wording that is negated or future does not count.
        ("stage", "operating", "The facility has not opened yet", "stage is operating"),
        ("stage", "operating", "The facility will be operational in 2027", "stage is operating"),
    ],
)
def test_typed_validation_rejects_altered_values(component, value, span, why):
    check = validate_extraction(f(component, value, quote=span), span)
    assert not check.valid
    assert why in check.reason, check.reason


@pytest.mark.parametrize(
    ("component", "value", "span"),
    [
        ("employee_count", 1250, "headcount of 1,250 staff"),
        ("amount_usd", 5_000_000, "raised $5 million"),
        ("amount_usd", "$5 million", "raised $5 million"),
        ("revenue_growth_pct", -12, "revenue growth of -12% in FY25"),
        ("headcount_growth_pct", 18, "headcount grew 18 per cent"),
        ("debt_amount", 120_000_000, "term loan of ₹12 crore"),
        ("revenue", 25_000_000, "Revenue: Rs.2.5 crore"),
        ("event_date", 2026, "the facility will open in 2026"),
        ("has_debt", False, "We have no debt"),
        ("has_debt", False, "The company is debt-free"),
        ("has_debt", True, "Outstanding term loan balance: 8.2 crore"),
        ("stage", "operating", "The Chakan facility has been operational since October"),
        ("start_year", 2008, "Head of Operations, 2008 - 2013"),
        ("end_year", 2013, "Head of Operations, 2008-2013"),
    ],
)
def test_typed_validation_accepts_values_as_stated(component, value, span):
    check = validate_extraction(f(component, value, quote=span), span)
    assert check.valid, check.reason


def test_structured_percent_field_needs_no_percent_sign():
    fact = f("headcount_growth_pct", 18.2, field_path="headcount.growth_12m", field_value=18.2)
    assert validate_extraction(fact, span_for(fact)).valid


def test_parse_quantities_keeps_sign_scale_unit_and_currency():
    from app.rules.compare import parse_quantities

    qs = parse_quantities("raised $5 million; loss of -₹2 crore; margin 18%; 2008-2013")
    assert [(q.value, q.currency, q.percent) for q in qs] == [
        (5_000_000.0, "USD", False),
        (-20_000_000.0, "INR", False),
        (18.0, None, True),
        (2008.0, None, False),
        (2013.0, None, False),
    ]


def test_screen_fact_requires_corroborated_binding_to_a_claim_entity():
    from app.rules.validation import screen_fact

    def bound(entity, basis):
        ev = Evidence(
            id="e",
            source=SRC,
            entity_id=entity,
            quote="Incorporated in 2014",
            identity_basis=basis,
        )
        return ExtractedFact(id="f", evidence=ev, component="incorporation_year", value=2014)

    assert screen_fact(bound("co", ["cin"]), ["co"]).valid
    assert not screen_fact(bound("co", ["name"]), ["co"]).valid
    assert not screen_fact(bound("co", []), ["co"]).valid
    assert not screen_fact(bound("other", ["cin"]), ["co"]).valid
    assert not screen_fact(bound("co", ["cin"]), []).valid
