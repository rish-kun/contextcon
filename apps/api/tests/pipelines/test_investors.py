"""Investor discovery pipeline, end to end on Postgres with fake clients."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.schemas.investors import InvestorSearchIn, InvestorSearchOut
from app.db import ledger
from app.db.models import ApiCache, Evidence, InvestorEntry, InvestorRun, Source, Step
from app.jobs import registry
from app.pipelines.investors import load_investor_search, start_investor_search, steps
from tests.db.factories import tenant
from tests.jobs.helpers import make_worker, states
from tests.pipelines.fakes import (
    TODAY,
    FakeClients,
    FakeCrustdata,
    FakeLlm,
    ago,
    company,
    investor,
    round_,
)

pytestmark = pytest.mark.asyncio

PROFILE = InvestorSearchIn(
    sector="B2B warehousing and logistics operator",
    location="India",
    stage="Series A",
    size="~200 employees",
    funding_sought="growth equity",
)


async def _search(
    session, sm, monkeypatch, companies, *, budget=60, llm=None, nl=True, **limits
) -> tuple[InvestorSearchOut, FakeCrustdata, object]:
    api = FakeCrustdata(companies, nl_available=nl)
    monkeypatch.setattr(steps, "clients", FakeClients(api, llm or FakeLlm()))
    t = await tenant(session)
    row, run = await start_investor_search(
        session, t.workspace.id, PROFILE, budget_credits=budget, **limits
    )
    await make_worker(sm, registry).drain()
    async with sm() as s:
        out = await load_investor_search(s, t.workspace.id, row.id)
    return out, api, t


def _by_name(out: InvestorSearchOut) -> dict:
    return {e.investor_name: e for e in out.entries}


async def test_undated_round_is_excluded(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("series_a", None, [investor("Undated Fund", "u1")])]),
        company(2, "Beta Warehousing", [round_("series_a", ago(200), [investor("Dated Fund")])]),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    names = _by_name(out)
    assert "Undated Fund" not in names
    assert "Dated Fund" in names
    assert out.rounds_read == 2 and out.rounds_excluded == 1


async def test_investor_without_name_is_excluded(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("seed", ago(100), [])]),
        company(2, "Beta Warehousing", [round_("seed", ago(100), [investor("  ", None)])]),
        company(3, "Gamma Freight", [round_("seed", ago(100), [investor("Named Fund")])]),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    assert [e.investor_name for e in out.entries] == ["Named Fund"]
    assert out.rounds_excluded == 2


async def test_name_only_duplicate_is_flagged_not_merged(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("series_a", ago(300), [investor("Banyan Capital")])]),
        company(
            2, "Beta Warehousing", [round_("series_a", ago(400), [investor("Banyan Capital")])]
        ),
        company(3, "Gamma Freight", [round_("seed", ago(500), [investor("Banyan Capital LLP")])]),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    banyan = [e for e in out.entries if e.investor_name.startswith("Banyan")]
    # Same exact name with no shared id or corroborating attribute: three entries.
    assert len(banyan) == 3
    ids = {e.id for e in banyan}
    for e in banyan:
        assert e.possible_duplicate_of in ids - {e.id}
        assert set(e.possible_duplicates) == ids - {e.id}
        assert any("not merged" in u for u in e.unknowns)
        assert len(e.comparable_rounds) == 1


async def test_shared_investor_id_merges(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("series_a", ago(30), [investor("Kite VC", "k1")])]),
        company(
            2, "Beta Warehousing", [round_("seed", ago(60), [investor("Kite Ventures", "k1")])]
        ),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    assert len(out.entries) == 1
    assert out.entries[0].investor_uuid == "k1"
    assert len(out.entries[0].comparable_rounds) == 2


async def test_recency_weighting(session, sm, monkeypatch) -> None:
    companies = [
        company(
            1, "Alpha Logistics", [round_("series_a", ago(5 * 365), [investor("Old Fund", "o1")])]
        ),
        company(
            2, "Beta Warehousing", [round_("series_a", ago(5 * 365), [investor("Old Fund", "o1")])]
        ),
        company(3, "Gamma Freight", [round_("series_a", ago(60), [investor("Recent Fund")])]),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    order = [e.investor_name for e in out.entries]
    # Two rounds five years ago weigh less than one round two months ago.
    assert order.index("Recent Fund") < order.index("Old Fund")
    old, recent = _by_name(out)["Old Fund"], _by_name(out)["Recent Fund"]
    assert old.score == pytest.approx(2 * 0.5 ** ((5 * 365 / 365.25) / 2), rel=1e-3)
    assert recent.score > old.score
    assert out.entries[0].rank == 1
    assert "does not predict" in out.ranking_basis


async def test_latest_found_shows_date_and_scope(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("series_a", ago(400), [investor("Lotus", "l1")])]),
        company(2, "Beta Warehousing", [round_("series_b", ago(90), [investor("Lotus", "l1")])]),
        company(3, "Gamma Freight", []),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    lotus = _by_name(out)["Lotus"]
    assert lotus.latest_sector_investment_found.isoformat() == ago(90)
    scope = lotus.latest_sector_investment_scope
    assert scope is not None
    assert f"searched {TODAY.isoformat()}" in scope
    assert "across 3 comparable companies" in scope
    assert "India" in scope
    assert out.scope_note == scope
    assert out.comparables_considered == 3


async def test_each_round_has_its_own_source(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("series_a", ago(10), [investor("Lotus", "l1")])]),
        company(2, "Beta Warehousing", [round_("series_b", ago(20), [investor("Lotus", "l1")])]),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    rounds = out.entries[0].comparable_rounds
    assert len(rounds) == 2
    assert len({r.source.source_id for r in rounds}) == 2
    assert all(r.evidence_id and r.source.source_class == "funding_database" for r in rounds)
    async with sm() as s:
        ev = await s.get(Evidence, uuid.UUID(rounds[0].evidence_id))
        assert ev.as_of == rounds[0].date
        assert ev.entity_ref.startswith("crustdata_company:")


async def test_compatibility_with_funding_kind_sought(session, sm, monkeypatch) -> None:
    companies = [
        company(1, "Alpha Logistics", [round_("private_equity", ago(50), [investor("Growth Co")])]),
        company(2, "Beta Warehousing", [round_("series_a", ago(50), [investor("Venture Co")])]),
        company(3, "Gamma Freight", [round_(None, ago(50), [investor("Mystery Co")])]),
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    by = _by_name(out)
    assert out.funding_kind_sought == "growth_equity"
    assert by["Growth Co"].compatibility == "compatible"
    assert "1 growth equity round in the record" in by["Growth Co"].funding_kind_compatibility
    assert by["Venture Co"].compatibility == "incompatible"
    assert by["Mystery Co"].compatibility == "unknown"
    assert "unknown" in by["Mystery Co"].funding_kind_compatibility.lower()


async def test_budget_exhaustion_skips_enrich(session, sm, monkeypatch) -> None:
    companies = [
        company(i, f"Co{i} Logistics", [round_("seed", ago(30), [investor("Fund")])])
        for i in range(1, 4)
    ]
    out, api, t = await _search(session, sm, monkeypatch, companies, budget=1, search_limit=3)
    assert "/company/enrich" not in api.paths
    async with sm() as s:
        st = await states(sm, out.run.id)
        totals = await ledger.investor_run_totals(s, t.workspace.id, uuid.UUID(out.id))
    assert st["investors.enrich"] == "skipped_budget"
    assert st["investors.rank"] == "done"
    assert out.entries == []
    assert "budget reached" in out.scope_note
    assert totals.credits <= Decimal(1)


async def test_budget_limits_enrich_to_what_fits(session, sm, monkeypatch) -> None:
    companies = [
        company(i, f"Co{i} Logistics", [round_("seed", ago(30 * i), [investor(f"Fund {i}")])])
        for i in range(1, 4)
    ]
    # Search costs 0.69 (3 × 0.23); the 2.31 left pays for one 2-credit enrich match.
    out, api, t = await _search(session, sm, monkeypatch, companies, budget=3, search_limit=3)
    enrich_bodies = [
        b for p, b in zip(api.paths, api.bodies, strict=True) if p == "/company/enrich"
    ]
    assert [len(b["crustdata_company_ids"]) for b in enrich_bodies] == [1]
    assert len(out.entries) == 1
    assert "2 comparable companies not read: budget reached" in out.scope_note
    async with sm() as s:
        totals = await ledger.investor_run_totals(s, t.workspace.id, uuid.UUID(out.id))
    assert totals.credits == Decimal("2.69")


async def test_costs_go_to_the_investor_run(session, sm, monkeypatch) -> None:
    companies = [company(1, "Alpha Logistics", [round_("seed", ago(30), [investor("Fund")])])]
    out, _, t = await _search(session, sm, monkeypatch, companies)
    async with sm() as s:
        totals = await ledger.investor_run_totals(s, t.workspace.id, uuid.UUID(out.id))
    # search 0.23, widened search 0.23 (fewer than 8 comparables), enrich 2
    assert totals.credits == Decimal("2.46")
    assert out.run is not None and out.run.cost.crustdata_credits == pytest.approx(2.46)
    assert out.run.kind == "investor_discover" and out.status == "ready"


async def test_no_person_or_contact_endpoints_called(session, sm, monkeypatch) -> None:
    companies = [company(1, "Alpha Logistics", [round_("seed", ago(30), [investor("Fund")])])]
    _, api, _ = await _search(session, sm, monkeypatch, companies)
    assert set(api.paths) == {"/company/search", "/company/enrich"}


async def test_contact_fields_are_stripped(session, sm, monkeypatch) -> None:
    secret_email, secret_phone = "founder@alpha.test", "+91 98765 43210"
    profile_link = "https://profiles.example/in/angel-person"
    angel = investor(
        "Asha Angel",
        "a1",
        type="person",
        email=secret_email,
        phone_number=secret_phone,
        crunchbase_profile_url=profile_link,
        permalink=profile_link,
    )
    companies = [
        company(
            1,
            "Alpha Logistics",
            [round_("seed", ago(30), [angel], contact_email=secret_email)],
            funding_extra={"contact_email": secret_email, "phone_number": secret_phone},
            people={"founders": [{"name": "F", "email": secret_email, "phone": secret_phone}]},
        )
    ]
    out, _, _ = await _search(session, sm, monkeypatch, companies)
    assert [e.investor_name for e in out.entries] == ["Asha Angel"]
    async with sm() as s:
        stored = []
        for model in (Source, Evidence, InvestorEntry, InvestorRun, Step, ApiCache):
            for row in (await s.execute(select(model))).scalars():
                stored.append({c.key: getattr(row, c.key) for c in model.__table__.columns})
    blob = json.dumps(stored, default=str) + out.model_dump_json()
    for secret in (secret_email, secret_phone, profile_link):
        assert secret not in blob


async def test_falls_back_to_filters_when_nl_search_is_off(session, sm, monkeypatch) -> None:
    other = company(9, "Zeta Software", [round_("seed", ago(30), [investor("Off-sector Fund")])])
    other["basic_info"]["description"] = "Accounting software for dentists"
    companies = [
        company(1, "Alpha Logistics", [round_("seed", ago(30), [investor("Sector Fund")])]),
        other,
    ]
    out, api, _ = await _search(session, sm, monkeypatch, companies, nl=False)
    names = _by_name(out)
    assert "Sector Fund" in names and "Off-sector Fund" not in names


async def test_spec_falls_back_to_profile_without_model(session, sm, monkeypatch) -> None:
    class Broken:
        async def extract_structured(self, *a, **k):
            raise RuntimeError("model down")

    companies = [company(1, "Alpha Logistics", [round_("seed", ago(30), [investor("Fund")])])]
    out, api, _ = await _search(session, sm, monkeypatch, companies, llm=Broken())
    assert len(out.entries) == 1
    search_body = api.bodies[api.paths.index("/company/search")]
    assert search_body["search"]["query"] == PROFILE.sector
    async with sm() as s:
        spec = (await s.execute(select(Step).where(Step.key == "investors.spec"))).scalar_one()
    assert spec.output["spec_source"] == "profile_only"
    assert spec.output["spec_error"] == "RuntimeError"


async def test_search_filters_from_profile(session, sm, monkeypatch) -> None:
    companies = [company(1, "Alpha Logistics", [round_("seed", ago(30), [investor("Fund")])])]
    _, api, _ = await _search(session, sm, monkeypatch, companies)
    body = api.bodies[api.paths.index("/company/search")]
    conds = {c["field"]: c for c in body["filters"]["conditions"]}
    assert conds["locations.country"]["value"] == "India"
    assert conds["basic_info.employee_count_range"]["value"] == ["51-200", "201-500"]
    assert conds["funding.last_round_type"]["value"] == [
        "seed",
        "series_a",
        "series_b",
        "private_equity",
    ]
    assert body["search"]["query"] == "warehousing and logistics operators"
    assert body["fields"] == ["crustdata_company_id", "basic_info", "locations"]
