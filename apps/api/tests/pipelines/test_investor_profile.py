"""Pure parts of investor discovery: profile → search plan, and ingestion."""

from app.domain.enums import FundingKind
from app.pipelines.investors.ingest import compact_company, funding_records, scrub_personal
from app.pipelines.investors.profile import (
    build_plan,
    country_of,
    employee_bands,
    normalize_stage,
    sought_kind,
    stage_window,
)


def test_stage_parsing() -> None:
    assert normalize_stage("Series A stage") == "series_a"
    assert normalize_stage("series_b") == "series_b"
    assert normalize_stage("Pre-seed") == "pre_seed"
    assert normalize_stage("growth") is None
    assert stage_window("seed") == ["pre_seed", "seed", "series_a"]
    assert stage_window(None) == []


def test_size_and_country() -> None:
    assert employee_bands("~200 employees") == ["51-200", "201-500"]
    assert employee_bands("51-200") == ["11-50", "51-200", "201-500"]
    assert employee_bands("unknown") == []
    assert country_of("Pune, India") == "India"
    assert country_of("IN") == "India"


def test_funding_kind_sought() -> None:
    assert sought_kind("seeking growth equity") == FundingKind.GROWTH_EQUITY
    assert sought_kind("venture debt") == FundingKind.DEBT
    assert sought_kind("equity", "series_a") == FundingKind.VENTURE_EQUITY
    assert sought_kind("equity") is None


def test_plan_uses_model_query_and_profile_filters() -> None:
    plan = build_plan(
        {"sector": "Cold chain", "location": "India", "stage": "seed", "size": "40"},
        {"activity_query": "cold-chain warehousing operators"},
    )
    assert plan.query == "cold-chain warehousing operators"
    assert plan.round_types == ["pre_seed", "seed", "series_a"]
    assert plan.kind_sought is None
    assert plan.filters(with_size=False) == {
        "op": "and",
        "conditions": [
            {"field": "locations.country", "type": "=", "value": "India"},
            {
                "field": "funding.last_round_type",
                "type": "in",
                "value": ["pre_seed", "seed", "series_a"],
            },
        ],
    }


def test_ingestion_whitelists_fields() -> None:
    raw = {
        "crustdata_company_id": 7,
        "basic_info": {"name": "Seven (fixture)"},
        "funding": {
            "contact_email": "x@seven.test",
            "milestones": [
                {
                    "round_type": "seed",
                    "funding_date": "2025-03-04T00:00:00",
                    "date": "2025-01-01",
                    "investors": ["Plain Name"],
                    "investors_detailed": [
                        {
                            "name": "Angel",
                            "type": "person",
                            "uuid": "a",
                            "linkedin_profile_url": "https://x.test/in/angel",
                            "email": "angel@x.test",
                        }
                    ],
                }
            ],
        },
    }
    c = compact_company(raw)
    r = c["rounds"][0]
    assert r["date"] == "2025-03-04"  # funding_date wins over date
    assert r["investors"] == [
        {"name": "Angel", "uuid": "a", "type": "person"},
        {"name": "Plain Name", "uuid": None, "type": None},
    ]
    assert "x.test" not in str(c) and "seven.test" not in str(c)
    r["evidence_id"] = "e1"
    recs = funding_records([c])
    assert [(x.investor_name, x.investor_id) for x in recs] == [
        ("Angel", "a"),
        ("Plain Name", None),
    ]


def test_scrub_personal_drops_links_and_people() -> None:
    value = {
        "body": [{"people": {"founders": [{"name": "F"}]}, "permalink": "p", "name": "Co"}],
        "phone_number": "+91 1",
    }
    assert scrub_personal(value) == {"body": [{"name": "Co"}]}
