import asyncio

import pytest

from app.extraction.criteria import (
    MUST_WEIGHT,
    PREFERENCE_WEIGHT,
    CriteriaDraft,
    extract_criteria,
)
from app.extraction.investors import BusinessProfile, amount_supported, extract_investor_spec
from app.extraction.llm import LlmOutputError, run_structured
from app.extraction.prompts import PROMPT_VERSION
from tests.extraction.fakes import FakeLlm

THESIS = (
    "privately held Indian warehousing and supply-chain software companies that serve "
    "enterprise customers and show recent expansion"
)


def crit(label, kind, dimension, quote, field=None, operator="equals", value=None):
    return {
        "label": label,
        "kind": kind,
        "dimension": dimension,
        "operator": operator,
        "value": value,
        "crustdata_field": field,
        "thesis_quote": quote,
    }


def run(coro):
    return asyncio.run(coro)


def test_criteria_mapping_weights_and_quote_enforcement():
    llm = FakeLlm(
        structured=[
            {
                "criteria": [
                    crit(
                        "Indian company",
                        "must",
                        "geography",
                        "Indian",
                        "locations.country",
                        value="India",
                    ),
                    crit(
                        "Privately held",
                        "must",
                        "ownership",
                        "privately held",
                        "basic_info.company_type",
                        value="Privately Held",
                    ),
                    crit(
                        "Serves enterprises",
                        "must",
                        "customer_type",
                        "serve enterprise customers",
                        "basic_info.industries",
                    ),
                    crit(
                        "Recent expansion",
                        "preference",
                        "growth_signal",
                        "show recent expansion",
                        "funding.last_round_type",
                    ),
                    # Invented: the thesis says nothing about headcount.
                    crit(
                        "Over 100 staff",
                        "must",
                        "size",
                        "more than 100 employees",
                        "headcount.total",
                        "gte",
                        100,
                    ),
                    # Field that does not exist.
                    crit(
                        "Software",
                        "must",
                        "industry_activity",
                        "supply-chain software",
                        "basic_info.made_up_field",
                    ),
                ],
                "activity_query": "warehousing and supply-chain software",
            }
        ]
    )
    out = run(extract_criteria(llm, THESIS))

    by_label = {c.label: c for c in out.criteria}
    assert set(by_label) == {
        "Indian company",
        "Privately held",
        "Serves enterprises",
        "Recent expansion",
        "Software",
    }
    assert [d.label for d in out.dropped] == ["Over 100 staff"]

    geo = by_label["Indian company"]
    assert geo.assessment == "crustdata_filter" and geo.weight == MUST_WEIGHT
    assert geo.needs_value_resolution is False

    own = by_label["Privately held"]
    assert own.crustdata_field == "basic_info.company_type" and own.needs_value_resolution

    # customer type never maps to a field; a field for the wrong dimension is removed
    assert by_label["Serves enterprises"].assessment == "assessed_from_evidence"
    assert by_label["Recent expansion"].crustdata_field is None
    assert by_label["Recent expansion"].weight == PREFERENCE_WEIGHT
    assert by_label["Software"].crustdata_field is None

    assert out.activity_query == "warehousing and supply-chain software"
    assert out.prompt_version == PROMPT_VERSION
    assert len(out.calls) == 1
    assert THESIS in llm.calls[0].user
    assert llm.calls[0].schema is CriteriaDraft


def test_criteria_empty_activity_query_falls_back_to_thesis():
    llm = FakeLlm(structured=[{"criteria": [], "activity_query": "  "}])
    assert run(extract_criteria(llm, THESIS)).activity_query == THESIS


def test_criteria_rejects_empty_thesis():
    with pytest.raises(ValueError):
        run(extract_criteria(FakeLlm(), "   "))


def test_run_structured_accepts_sync_clients_and_json_and_rejects_bad_shapes():
    sync = FakeLlm(structured=['{"criteria": [], "activity_query": "x"}'], is_async=False)
    draft, record = run(run_structured(sync, "s", "u", CriteriaDraft))
    assert draft.activity_query == "x" and record == {"n": 1}

    bad = FakeLlm(structured=[{"criteria": "nope"}])
    with pytest.raises(LlmOutputError):
        run(run_structured(bad, "s", "u", CriteriaDraft))


def test_investor_spec_keeps_only_supported_funding_fields():
    profile = BusinessProfile(
        sector="Cold-chain logistics software",
        location="Bengaluru, India",
        stage="Series A",
        size="80 employees",
        funding_sought="Raising a Series A of $5M in equity",
    )
    llm = FakeLlm(
        structured=[
            {
                "comparable_criteria": [
                    crit(
                        "Cold-chain software",
                        "must",
                        "industry_activity",
                        "Cold-chain logistics software",
                    ),
                    crit("India", "must", "geography", "India", "locations.country", value="India"),
                    crit("Profitable", "must", "other", "profitable for three years"),
                ],
                "activity_query": "cold-chain logistics software",
                "funding_sought": {
                    "instrument": "equity",
                    "round_type": "Series A",
                    "amount_usd": 5_000_000,
                    "quote": "Raising a Series A of $5M in equity",
                },
            }
        ]
    )
    spec = run(extract_investor_spec(llm, profile))
    assert [c.label for c in spec.comparable_criteria] == ["Cold-chain software", "India"]
    assert [d.label for d in spec.dropped] == ["Profitable"]
    assert spec.funding_sought.round_type == "series_a"
    assert spec.funding_sought.amount_usd == 5_000_000
    assert spec.funding_sought.needs_value_resolution


def test_investor_spec_drops_unquoted_funding_and_unstated_round():
    profile = BusinessProfile(sector="Freight brokerage", location="Pune, India")
    llm = FakeLlm(
        structured=[
            {
                "comparable_criteria": [],
                "activity_query": "",
                "funding_sought": {
                    "instrument": "debt",
                    "round_type": "series_b",
                    "amount_usd": 1e7,
                    "quote": "seeking $10M venture debt",
                },
            }
        ]
    )
    spec = run(extract_investor_spec(llm, profile))
    assert spec.funding_sought.instrument == "unspecified"
    assert spec.funding_sought.amount_usd is None and spec.funding_sought.round_type is None
    assert spec.activity_query == "Freight brokerage"


def test_amount_supported():
    assert amount_supported(2_000_000, "We seek USD 2,000,000")
    assert amount_supported(2_500_000, "raising $2.5M")
    assert not amount_supported(2_000_000, "raising INR 2,000,000")
    assert not amount_supported(3_000_000, "raising $2M")


# --- The activity criterion is always produced -------------------------------------

_LIVE_LIKE = [
    crit("Based in India", "must", "geography", "Indian", "locations.country", value="India"),
    crit(
        "Privately held",
        "must",
        "ownership",
        "privately held",
        "basic_info.company_type",
        value="Privately Held",
    ),
    crit("Enterprise customers", "preference", "customer_type", "serve enterprise customers"),
    crit("Recent expansion", "preference", "growth_signal", "show recent expansion"),
]


@pytest.mark.parametrize(
    "activity_query",
    [
        "warehousing and supply-chain software",
        "Indian warehousing and supply chain software companies serving enterprise customers",
    ],
)
def test_activity_criterion_restored_when_the_model_omits_it(activity_query):
    llm = FakeLlm(structured=[{"criteria": _LIVE_LIKE, "activity_query": activity_query}])
    out = run(extract_criteria(llm, THESIS))
    activity = [c for c in out.criteria if c.dimension == "industry_activity"]
    assert len(activity) == 1
    a = activity[0]
    assert a.thesis_quote == "warehousing and supply-chain software"
    assert a.thesis_quote in THESIS  # verbatim grounding is unchanged
    assert a.kind == "must" and a.weight == MUST_WEIGHT
    assert a.assessment == "assessed_from_evidence" and a.crustdata_field is None
    assert out.restored == [a.label]


def test_activity_criterion_restored_when_its_quote_was_invented():
    invented = crit("Supply-chain SaaS", "must", "industry_activity", "supply chain SaaS vendors")
    llm = FakeLlm(
        structured=[
            {
                "criteria": [*_LIVE_LIKE, invented],
                "activity_query": "warehousing and supply-chain software",
            }
        ]
    )
    out = run(extract_criteria(llm, THESIS))
    assert [d.label for d in out.dropped] == ["Supply-chain SaaS"]
    assert [c.thesis_quote for c in out.criteria if c.dimension == "industry_activity"] == [
        "warehousing and supply-chain software"
    ]


def test_activity_criterion_kept_as_is_when_the_model_returns_it():
    own = crit(
        "Warehousing software",
        "must",
        "industry_activity",
        "warehousing and supply-chain software",
        operator="contains",
        value="warehousing software",
    )
    llm = FakeLlm(
        structured=[
            {
                "criteria": [*_LIVE_LIKE, own],
                "activity_query": "warehousing and supply-chain software",
            }
        ]
    )
    out = run(extract_criteria(llm, THESIS))
    activity = [c for c in out.criteria if c.dimension == "industry_activity"]
    assert [c.label for c in activity] == ["Warehousing software"] and out.restored == []


def test_activity_criterion_not_invented_when_the_thesis_states_none():
    llm = FakeLlm(structured=[{"criteria": _LIVE_LIKE[:2], "activity_query": "payments software"}])
    out = run(extract_criteria(llm, "privately held Indian companies"))
    assert all(c.dimension != "industry_activity" for c in out.criteria)
    assert out.restored == []
