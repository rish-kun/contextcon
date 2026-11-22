"""Financial assessment: reported figures with period, growth and margins; provider
estimates as indicative; a clear "nothing found" with what was searched. Companies are
fictional."""

from datetime import date, datetime

import pytest

from app.domain import Evidence, ExtractedFact, Source, SourceReliability
from app.domain.types import FinancialEstimate, FinancialInputs, ReportedFigure
from app.rules import financials as fin
from app.rules.evaluate import financial_assessment

R = SourceReliability
CO = "co-1"
RETRIEVED = datetime(2026, 11, 20)


def _source(id: str, url: str, reliability: SourceReliability) -> Source:
    return Source(
        id=id, provider="web", label=url, url=url, retrieved_at=RETRIEVED, reliability=reliability
    )


def _reported(
    id: str,
    source: Source,
    component: str,
    value: str,
    quote: str,
    period: str | None = None,
    *,
    basis: tuple[str, ...] = ("crustdata_id",),
    entity: str = CO,
) -> ReportedFigure:
    p = fin.parse_period(period or quote)
    a = fin.parse_amount(value)
    return ReportedFigure(
        fact=ExtractedFact(
            id=f"{id}:{component}",
            component=component,
            value=value,
            evidence=Evidence(
                id=id,
                source=source,
                entity_id=entity,
                quote=quote,
                field_path=f"financials.{component}",
                field_value=value,
                as_of=p.end if p else None,
                identity_basis=list(basis),
            ),
        ),
        period=p.label if p else None,
        period_end=p.end if p else None,
        period_months=p.months if p else None,
        amount=a.value if a else None,
        currency=a.currency if a else None,
        unit=a.unit if a else None,
    )


# --- Parsing ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "label", "end", "months"),
    [
        ("Revenue for Q2 FY27 rose", "Q2 FY27", date(2026, 9, 30), 3),
        ("Q2FY27 results", "Q2 FY27", date(2026, 9, 30), 3),
        ("Q4 FY 2025-26", "Q4 FY26", date(2026, 3, 31), 3),
        ("FY24 turnover", "FY24", date(2024, 3, 31), 12),
        ("FY 2023-24", "FY24", date(2024, 3, 31), 12),
        ("H1 FY26", "H1 FY26", date(2025, 9, 30), 6),
        ("9M FY26", "9M FY26", date(2025, 12, 31), 9),
        ("for the quarter ended September 30, 2026", "Q2 FY27", date(2026, 9, 30), 3),
        ("for the year ended 31st March 2024", "FY24", date(2024, 3, 31), 12),
        ("Q3 2026 revenue", "Q3 2026", date(2026, 9, 30), 3),
    ],
)
def test_period_parsing(text, label, end, months):
    p = fin.parse_period(text)
    assert p is not None and (p.label, p.end, p.months) == (label, end, months)


def test_no_period_in_plain_text():
    assert fin.parse_period("Revenue grew strongly") is None


@pytest.mark.parametrize(
    ("text", "value", "currency", "unit", "shown"),
    [
        ("₹2,095 crore", 2.095e10, "INR", "crore", "₹2,095 cr"),
        ("Rs. 45 lakh", 4.5e6, "INR", "lakh", "₹45 lakh"),
        ("INR 12.5 Cr", 1.25e8, "INR", "crore", "₹12.5 cr"),
        ("120 crores", 1.2e9, "INR", "crore", "₹120 cr"),
        ("$12.4 million", 1.24e7, "USD", "million", "$12.4M"),
        ("USD 3 billion", 3e9, "USD", "billion", "$3B"),
    ],
)
def test_amount_parsing_keeps_unit(text, value, currency, unit, shown):
    a = fin.parse_amount(text)
    assert a is not None
    assert a.value == pytest.approx(value)
    assert (a.currency, a.unit) == (currency, unit)
    assert fin.display_amount(a) == shown


def test_bare_number_takes_the_heading_unit():
    note = fin.unit_note("Statement of results (₹ in crore) Revenue from operations")
    assert note is not None and note[:2] == ("crore", "INR")
    a = fin.scale_bare(fin.parse_amount("2,095.40"), note)
    assert a.value == pytest.approx(2.0954e10) and a.unit == "crore"
    lakh = fin.scale_bare(fin.parse_amount("845"), fin.unit_note("(Rs. in lakhs)"))
    assert lakh.value == pytest.approx(8.45e7) and fin.display_amount(lakh) == "₹845 lakh"


def test_percentages_are_not_amounts():
    assert fin.parse_amount("up 24%") is None


# --- Assessment -------------------------------------------------------------------

NSE = _source("nse", "https://www.nseindia.com/results/acme-q2fy27.pdf", R.REGISTRY_MIRROR)
NSE_PRIOR = _source(
    "nse-prior", "https://www.nseindia.com/results/acme-q2fy26.pdf", R.REGISTRY_MIRROR
)


def test_listed_company_with_exchange_filing_is_assessed():
    fx = FinancialInputs(
        listing="listed",
        searched=['web search "Acme Motors (fixture)" quarterly results revenue FY27'],
        figures=[
            _reported(
                "e1",
                NSE,
                "revenue",
                "₹2,095 crore",
                "Revenue from operations for Q2 FY27 at ₹2,095 crore",
            ),
            _reported("e2", NSE, "ebitda", "₹419 crore", "EBITDA for Q2 FY27 at ₹419 crore"),
            _reported(
                "e3",
                NSE_PRIOR,
                "revenue",
                "₹1,690 crore",
                "Revenue from operations for Q2 FY26 at ₹1,690 crore",
            ),
        ],
    )
    f = financial_assessment([], [CO], fx)
    assert f.assessed and f.state == "assessed"
    assert f.period == "Q2 FY27"
    assert f.conclusion.startswith("Reported revenue ₹2,095 cr in Q2 FY27, +24% YoY")
    assert "EBITDA margin 20%" in f.conclusion
    assert "(NSE filing)" in f.conclusion
    assert "valuation" in f.conclusion  # bounded: says it is not one
    assert f.figures[0].period == "Q2 FY27" and f.figures[0].basis == "filing"
    assert any("limited-review" in a for a in f.assumptions)


def test_private_company_with_registry_mirror_figures():
    tofler = _source("tofler", "https://www.tofler.in/acme-freight/company/U1", R.REGISTRY_MIRROR)
    fx = FinancialInputs(
        listing="unlisted",
        searched=["registry pages already found (tofler.in)"],
        figures=[
            _reported(
                "m1",
                tofler,
                "revenue",
                "₹45.2 crore",
                "Revenue: ₹45.2 crore (FY24)",
                basis=("crustdata_id",),
            ),
            _reported("m2", tofler, "revenue", "₹38 crore", "Revenue: ₹38 crore (FY23)"),
            _reported("m3", tofler, "net_worth", "₹12 crore", "Net worth: ₹12 crore (FY24)"),
        ],
    )
    f = financial_assessment([], [CO], fx)
    assert f.state == "assessed"
    assert f.period == "FY24"
    assert f.conclusion.startswith("Reported revenue ₹45.2 cr in FY24, +18.9% YoY")
    assert "registry filing via tofler.in" in f.conclusion
    assert {x.component for x in f.figures} == {"revenue", "net_worth"}
    assert any("Registry-mirror" in a for a in f.assumptions)


def test_estimates_only_are_indicative_not_assessed():
    fx = FinancialInputs(
        searched=['web search "Acme" quarterly results revenue FY27: no figures'],
        estimates=[
            FinancialEstimate(
                lower_usd=1e7,
                upper_usd=5e7,
                as_of=date(2026, 10, 1),
                evidence_id="est",
                source_label="Company record: revenue",
            )
        ],
    )
    f = financial_assessment([], [CO], fx)
    assert not f.assessed and f.state == "indicative"
    assert f.reason.startswith("Indicative (estimate): annual revenue $10M–$50M")
    assert f.figures[0].basis == "estimate"
    assert f.would_need


def test_nothing_found_names_what_was_searched_and_what_would_settle_it():
    searched = [
        'web search "Acme" quarterly results revenue FY27: no filing, results or registry '
        "pages among 4 result(s)",
        'web search "Acme" annual results revenue FY26: no filing, results or registry '
        "pages among 2 result(s)",
    ]
    f = financial_assessment([], [CO], FinancialInputs(listing="listed", searched=searched))
    assert f.state == "not_found" and not f.assessed
    assert f.reason == "No public financials found — searched: " + "; ".join(searched)
    assert f.searched == searched
    assert any("stock exchange" in w for w in f.would_need)


def test_before_the_search_runs_it_is_not_assessed():
    f = financial_assessment([], [CO], FinancialInputs())
    assert f.state == "not_assessed" and f.reason.startswith("Not assessed")


def test_name_only_binding_never_counts():
    fx = FinancialInputs(
        listing="listed",
        searched=["x"],
        figures=[
            _reported(
                "n1",
                NSE,
                "revenue",
                "₹2,095 crore",
                "Revenue for Q2 FY27 at ₹2,095 crore",
                basis=("name",),
            )
        ],
    )
    assert financial_assessment([], [CO], fx).state == "not_found"


def test_company_results_page_counts_only_for_a_listed_company():
    ir = _source("ir", "https://acme.example/investors/results", R.COMPANY_ANNOUNCEMENT)
    fig = _reported("i1", ir, "revenue", "₹2,095 crore", "Q2 FY27 revenue ₹2,095 crore")
    listed = financial_assessment([], [CO], FinancialInputs(listing="listed", figures=[fig]))
    assert listed.state == "assessed" and "results on acme.example" in listed.conclusion
    unlisted = financial_assessment([], [CO], FinancialInputs(listing="unlisted", figures=[fig]))
    assert unlisted.state == "not_assessed"


def test_quote_must_state_the_value():
    fig = _reported("q1", NSE, "revenue", "₹2,095 crore", "Revenue for Q2 FY27 at ₹2,059 crore")
    f = financial_assessment([], [CO], FinancialInputs(listing="listed", figures=[fig]))
    assert not f.assessed
