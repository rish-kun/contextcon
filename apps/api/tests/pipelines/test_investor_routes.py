"""`/investor-searches` routes against Postgres, with the workspace dependency overridden."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest

from app.api.investors import InvestorActor, get_investor_actor, investor_session
from app.jobs import registry
from app.main import create_app
from app.pipelines.investors import steps
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

BODY = {
    "sector": "B2B warehousing and logistics operator",
    "location": "India",
    "stage": "Series A",
    "size": "~200 employees",
    "funding_sought": "growth equity",
}


def _client(sm, workspace_id: uuid.UUID) -> httpx.AsyncClient:
    app = create_app()

    async def actor() -> InvestorActor:
        return InvestorActor(workspace_id=workspace_id)

    async def session():  # type: ignore[no-untyped-def]
        async with sm() as s:
            yield s

    app.dependency_overrides[get_investor_actor] = actor
    app.dependency_overrides[investor_session] = session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_create_list_and_get(session, sm, monkeypatch) -> None:
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    api = FakeCrustdata(
        [company(1, "Alpha Logistics", [round_("series_a", ago(40), [investor("Kite", "k1")])])]
    )
    monkeypatch.setattr(steps, "clients", FakeClients(api, FakeLlm()))
    t = await tenant(session)
    other = await tenant(session, "other")

    async with _client(sm, t.workspace.id) as c:
        created = await c.post("/investor-searches", json=BODY)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "searching"
        assert body["run"]["kind"] == "investor_discover"
        assert body["run"]["budget_credits"] == 60
        assert body["profile"] == BODY

        await make_worker(sm, registry).drain()

        got = (await c.get(f"/investor-searches/{body['id']}")).json()
        assert got["status"] == "ready"
        assert [e["investor_name"] for e in got["entries"]] == ["Kite"]
        entry = got["entries"][0]
        assert entry["comparable_rounds"][0]["source"]["source_class"] == "funding_database"
        assert entry["latest_sector_investment_scope"].startswith("searched ")
        assert entry["compatibility"] == "incompatible"
        assert "does not predict" in got["ranking_basis"]

        listed = (await c.get("/investor-searches")).json()
        assert [(s["id"], s["entries_count"]) for s in listed] == [(body["id"], 1)]

        assert (await c.get("/investor-searches/not-a-uuid")).status_code == 404

    async with _client(sm, other.workspace.id) as c:
        assert (await c.get(f"/investor-searches/{body['id']}")).status_code == 404
        assert (await c.get("/investor-searches")).json() == []


async def test_routes_fail_closed_without_auth(monkeypatch) -> None:
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.post("/investor-searches", json=BODY)).status_code == 501
        assert (await c.get("/investor-searches")).status_code == 501
