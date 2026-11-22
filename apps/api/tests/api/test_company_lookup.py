"""`GET /companies/lookup`: identify by name, widened by one search, deduped, ranked."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.api import companies
from app.clients.crustdata_models import CompanySearchResult, IdentifyResult

pytestmark = pytest.mark.asyncio


def _basic(cid: int, name: str, domain: str, **extra: Any) -> dict[str, Any]:
    return {"crustdata_company_id": cid, "name": name, "primary_domain": domain, **extra}


class FakeClient:
    def __init__(self, identify: list[dict], search: list[dict]) -> None:
        self._identify = identify
        self._search = search
        self.calls: list[str] = []

    async def identify_company(self, **kwargs: Any):
        self.calls.append("identify")
        matches = [
            {"company_data": {"crustdata_company_id": d["crustdata_company_id"], "basic_info": d}}
            for d in self._identify
        ]
        return [IdentifyResult.model_validate({"matches": matches})], None

    async def search_companies(self, **kwargs: Any):
        self.calls.append("search")
        assert kwargs["limit"] == companies.SEARCH_LIMIT and kwargs["query"]
        return CompanySearchResult.model_validate({"companies": self._search}), None

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _clear_cache():
    companies._cache.clear()
    yield
    companies._cache.clear()


async def _call(client: FakeClient, workspace: uuid.UUID, q: str = "Acme"):
    return await companies.lookup_companies(workspace, lambda recorder: client, q)


async def test_merges_identify_and_search_dedupes_and_ranks(monkeypatch) -> None:
    monkeypatch.setattr(companies, "fixtures_enabled", lambda: False)
    one = _basic(1, "Acme Robotics", "acmerobotics.com", description="x" * 400)
    client = FakeClient(
        identify=[one],
        search=[
            {
                "crustdata_company_id": 1,
                "basic_info": one,
                "headcount": {"total": 140},
                "locations": {"headquarters": "Austin, TX", "country": "USA"},
            },
            {
                "crustdata_company_id": 2,
                "basic_info": _basic(2, "Acme Corp", "acme.com"),
                "headcount": {"total": 9000},
                "metadata": {"ticker": "ACME"},
            },
            {
                "crustdata_company_id": 3,
                "basic_info": _basic(3, "Acme Labs", "acmelabs.io"),
                "headcount": {"total": 50000},
            },
        ],
    )
    out = await _call(client, uuid.uuid4())
    assert client.calls == ["identify", "search"]
    ids = [c.crustdata_id for c in out.candidates]
    assert ids == [2, 3, 1]  # acme.com is a primary-domain match, then by headcount
    acme_robotics = out.candidates[2]
    assert acme_robotics.headcount == 140 and acme_robotics.hq_city == "Austin"
    assert len(acme_robotics.description or "") <= companies.DESCRIPTION_CHARS
    assert out.candidates[0].listed is True


async def test_no_search_when_identify_finds_two(monkeypatch) -> None:
    monkeypatch.setattr(companies, "fixtures_enabled", lambda: False)
    client = FakeClient(
        identify=[_basic(1, "Acme", "acme.com"), _basic(2, "Acme Labs", "acmelabs.io")],
        search=[],
    )
    out = await _call(client, uuid.uuid4())
    assert client.calls == ["identify"]
    assert [c.crustdata_id for c in out.candidates] == [1, 2]


async def test_cache_is_scoped_to_the_workspace(monkeypatch) -> None:
    monkeypatch.setattr(companies, "fixtures_enabled", lambda: False)
    client = FakeClient(
        identify=[_basic(1, "Acme", "acme.com"), _basic(2, "Acme Labs", "acmelabs.io")],
        search=[],
    )
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    await _call(client, ws_a)
    await _call(client, ws_a, "  acme ")
    assert client.calls == ["identify"]  # served from ws_a's cache
    await _call(client, ws_b)
    assert client.calls == ["identify", "identify"]  # never shared across workspaces
