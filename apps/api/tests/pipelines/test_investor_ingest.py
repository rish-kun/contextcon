"""Investor ingestion: contact values never stored or cached, and in-round
deduplication only on a shared id or the provider's own link."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.api.schemas.investors import InvestorSearchIn
from app.db.models import ApiCache, Evidence, InvestorEntry, InvestorRun, Source, Step
from app.jobs import registry
from app.pipelines.investors import load_investor_search, start_investor_search, steps
from app.pipelines.investors.ingest import ScrubbingCache, compact_company, is_contact_value
from tests.db.factories import tenant
from tests.jobs.helpers import make_worker
from tests.pipelines.fakes import (
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


async def _start(session, sm, monkeypatch, api):
    monkeypatch.setattr(steps, "clients", FakeClients(api, FakeLlm()))
    t = await tenant(session)
    row, _ = await start_investor_search(session, t.workspace.id, PROFILE, budget_credits=60)
    await make_worker(sm, registry).drain()
    return t, row, None


async def _load(sm, t, row):
    async with sm() as s:
        return await load_investor_search(s, t.workspace.id, row.id)


# --- Privacy ------------------------------------------------------------------------

PROFILE_URL = "https://www.linkedin.com/in/asha-angel"
BARE_URL = "angels.example/people/ravi"
PHONE = "+919876543210"
PHONE_SPACED = "98765 43210"


def _leaky_company() -> dict:
    r = round_(
        "seed",
        ago(30),
        [
            investor("Kite VC", "k1"),
            investor(PROFILE_URL, None, type="person"),
            investor("Asha Angel", PHONE, type="person"),
        ],
    )
    r["lead_investors"] = f"Kite VC, {PROFILE_URL}, {PHONE}"
    r["investors"] = ["Kite VC", BARE_URL, PHONE_SPACED, "Asha Angel"]
    return company(1, "Alpha Logistics", [r])


async def test_contact_values_in_retained_fields_never_stored(session, sm, monkeypatch) -> None:
    t, row, _ = await _start(session, sm, monkeypatch, FakeCrustdata([_leaky_company()]))
    out = await _load(sm, t, row)
    assert sorted(e.investor_name for e in out.entries) == ["Asha Angel", "Kite VC"]
    async with sm() as s:
        stored = []
        for model in (Source, Evidence, InvestorEntry, InvestorRun, Step, ApiCache):
            for r in (await s.execute(select(model))).scalars():
                stored.append({c.key: getattr(r, c.key) for c in model.__table__.columns})
    blob = json.dumps(stored, default=str) + out.model_dump_json()
    for secret in (PROFILE_URL, "linkedin.com/in", BARE_URL, PHONE, PHONE_SPACED):
        assert secret not in blob, secret


async def test_shared_cache_hits_are_sanitized() -> None:
    class Inner:
        def __init__(self) -> None:
            self.data: dict = {}

        async def get(self, key):  # type: ignore[no-untyped-def]
            return self.data.get(key)

        async def set(self, key, value):  # type: ignore[no-untyped-def]
            self.data[key] = value

    inner = Inner()
    # Stored by another caller without the investor allowlist.
    inner.data["k"] = {
        "body": [
            {
                "matched_on": "1",
                "matches": [{"confidence_score": 1.0, "company_data": _leaky_company()}],
            }
        ],
        "http_status": 200,
    }
    hit = await ScrubbingCache(inner).get("k")
    blob = json.dumps(hit)
    for secret in (PROFILE_URL, BARE_URL, PHONE, PHONE_SPACED):
        assert secret not in blob, secret
    rnd = hit["body"][0]["matches"][0]["company_data"]["funding"]["milestones"][0]
    assert rnd["lead_investors"] == ["Kite VC"]
    assert rnd["investors"] == ["Kite VC", "Asha Angel"]
    assert rnd["investors_detailed"] == [
        {"name": "Kite VC", "uuid": "k1", "type": "organization"},
        {"name": "Asha Angel", "uuid": None, "type": "person"},
    ]
    assert hit["http_status"] == 200

    await ScrubbingCache(inner).set("k2", inner.data["k"])
    assert PROFILE_URL not in json.dumps(inner.data["k2"])


@pytest.mark.parametrize(
    "value",
    [PROFILE_URL, BARE_URL, "www.angel.example", PHONE, PHONE_SPACED, "a@b.example"],
)
async def test_contact_values_detected(value: str) -> None:
    assert is_contact_value(value)


@pytest.mark.parametrize(
    "value", ["Kite VC", "Fund 2020-21", "Series A", "Y Combinator", "3one4 Capital"]
)
async def test_names_are_not_contact_values(value: str) -> None:
    assert not is_contact_value(value)


# --- In-round deduplication -----------------------------------------------------------


async def test_plain_mention_merges_only_on_the_provider_link() -> None:
    r = round_("seed", ago(30), [investor("Kite VC", "k1")])
    r["investors"] = ["Kite VC", "KITE V.C."]
    r["lead_investors"] = "Kite VC"
    rounds = compact_company(company(1, "Alpha Logistics", [r]))["rounds"]
    assert rounds[0]["investors"] == [
        {"name": "Kite VC", "uuid": "k1", "type": "organization"},
        {"name": "KITE V.C.", "uuid": None, "type": None},
    ]


async def test_ambiguous_mention_is_kept_as_possible_duplicate(session, sm, monkeypatch) -> None:
    r = round_("seed", ago(30), [investor("Kite VC", "k1")])
    r["investors"] = ["Kite VC", "kite vc"]
    t, row, _ = await _start(
        session, sm, monkeypatch, FakeCrustdata([company(1, "Alpha Logistics", [r])])
    )
    out = await _load(sm, t, row)
    by = {e.investor_name: e for e in out.entries}
    assert set(by) == {"Kite VC", "kite vc"}
    assert by["kite vc"].possible_duplicates == [by["Kite VC"].id]
    assert by["Kite VC"].possible_duplicates == [by["kite vc"].id]


async def test_redaction_placeholder_is_not_a_name() -> None:
    assert is_contact_value("[redacted:phone]")
