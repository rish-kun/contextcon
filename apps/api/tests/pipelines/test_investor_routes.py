"""`/investor-searches` routes against Postgres, signed in with a real session cookie."""

from __future__ import annotations

import datetime as dt
import uuid

import httpx2 as httpx
import pytest
import pytest_asyncio

from app.auth.config import get_auth_settings
from app.auth.sessions import SESSION_COOKIE, create_session
from app.db.models import InvestorRun
from app.db.session import dispose_engine, init_engine
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


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_auth_settings.cache_clear()
    yield
    get_auth_settings.cache_clear()


@pytest_asyncio.fixture
async def app(sm, db_url):
    """The real app on the test database (no dependency overrides)."""
    init_engine(db_url)
    try:
        yield create_app()
    finally:
        await dispose_engine()


def _client(app, token: str | None = None) -> httpx.AsyncClient:
    cookies = {SESSION_COOKIE: token} if token else None
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", cookies=cookies
    )


async def _signed_in(session, name: str):
    t = await tenant(session, name)
    token, _ = await create_session(session, t.user, ttl=dt.timedelta(hours=1))
    await session.commit()
    return t, token


async def test_create_list_and_get(app, session, sm, monkeypatch) -> None:
    api = FakeCrustdata(
        [company(1, "Alpha Logistics", [round_("series_a", ago(40), [investor("Kite", "k1")])])]
    )
    monkeypatch.setattr(steps, "clients", FakeClients(api, FakeLlm()))
    t, token = await _signed_in(session, "acme")
    other, other_token = await _signed_in(session, "other")

    async with _client(app, token) as c:
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
        assert entry["comparable_rounds"][0]["source"]["source_class"] == "data_provider"
        assert entry["latest_sector_investment_scope"].startswith("searched ")
        assert entry["compatibility"] == "unknown"
        assert "does not predict" in got["ranking_basis"]

        listed = (await c.get("/investor-searches")).json()
        assert [(s["id"], s["entries_count"]) for s in listed] == [(body["id"], 1)]

        assert (await c.get("/investor-searches/not-a-uuid")).status_code == 404

    # The search belongs to the signed-in user's workspace and records who started it.
    async with sm() as s:
        row = await s.get(InvestorRun, uuid.UUID(body["id"]))
        assert row.workspace_id == t.workspace.id
        assert row.created_by == t.user.id

    # Another workspace's user sees neither the search nor its listing.
    async with _client(app, other_token) as c:
        assert (await c.get(f"/investor-searches/{body['id']}")).status_code == 404
        assert (await c.get("/investor-searches")).json() == []
    assert other.workspace.id != t.workspace.id


async def test_routes_need_a_session(app, session) -> None:
    await _signed_in(session, "acme")
    for token in (None, "forged-token"):
        async with _client(app, token) as c:
            assert (await c.post("/investor-searches", json=BODY)).status_code == 401
            assert (await c.get("/investor-searches")).status_code == 401
            missing = "00000000-0000-0000-0000-000000000000"
            assert (await c.get(f"/investor-searches/{missing}")).status_code == 401


async def test_fixture_mode_needs_no_session(monkeypatch) -> None:
    from app.api import fixtures

    monkeypatch.setenv("DEALPROOF_FIXTURES", "1")
    async with _client(create_app()) as c:
        created = await c.post("/investor-searches", json=BODY)
        assert created.status_code == 201 and created.json()["profile"] == BODY
        assert (await c.get("/investor-searches")).status_code == 200
        got = await c.get(f"/investor-searches/{fixtures.INVESTOR_SEARCH_ID}")
        assert got.status_code == 200
        assert (await c.get("/investor-searches/unknown")).status_code == 404
