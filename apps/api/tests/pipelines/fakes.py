"""Fake Crustdata (a real `CrustdataClient` over a mock transport) and a scripted LLM."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import httpx2

from app.clients import CrustdataClient, SlidingWindowRateLimiter
from app.extraction.investors import FundingSoughtDraft, InvestorSpecDraft

TODAY = dt.datetime.now(dt.UTC).date()


def ago(days: int) -> str:
    return (TODAY - dt.timedelta(days=days)).isoformat()


def investor(name: str | None, uuid: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"name": name, "uuid": uuid, "type": "organization", **extra}


def round_(
    round_type: str | None, date: str | None, investors: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "round_type": round_type,
        "date": date,
        "amount_usd": extra.pop("amount_usd", 5_000_000),
        "investors": [i["name"] for i in investors if i.get("name")],
        "investors_detailed": investors,
        **extra,
    }


def company(cid: int, name: str, rounds: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "crustdata_company_id": cid,
        "basic_info": {
            "crustdata_company_id": cid,
            "name": name,
            "primary_domain": f"{name.split()[0].lower()}.test",
            "description": "Warehousing and logistics operator (fixture)",
        },
        "locations": {"country": "India", "headquarters": "Pune, India"},
        "taxonomy": {"professional_network_industries": ["Warehousing and Storage"]},
        "funding": {"milestones": rounds, **extra.pop("funding_extra", {})},
        **extra,
    }


class FakeCrustdata:
    def __init__(self, companies: list[dict[str, Any]], *, nl_available: bool = True) -> None:
        self.companies = {c["crustdata_company_id"]: c for c in companies}
        self.nl_available = nl_available
        self.paths: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        body = json.loads(request.content or b"{}")
        self.paths.append(path)
        self.bodies.append(body)
        if path == "/company/search":
            if "search" in body and not self.nl_available:
                return httpx2.Response(
                    403,
                    json={"error": {"type": "permission_error", "message": "not enabled"}},
                    headers={"x-credits-used": "0"},
                )
            rows = [
                {k: c[k] for k in ("crustdata_company_id", "basic_info", "locations")}
                for c in self.companies.values()
            ][: body.get("limit", 20)]
            credits = f"{0.23 * len(rows):.2f}"
            return httpx2.Response(
                200, json={"companies": rows, "next_cursor": None}, headers=_h(credits)
            )
        if path == "/company/enrich":
            ids = body["crustdata_company_ids"]
            out = [
                {
                    "matched_on": str(i),
                    "match_type": "crustdata_company_id",
                    "matches": [{"confidence_score": 1.0, "company_data": self.companies[i]}],
                }
                for i in ids
                if i in self.companies
            ]
            return httpx2.Response(200, json=out, headers=_h(f"{2 * len(out)}"))
        return httpx2.Response(404, json={"error": {"type": "not_found", "message": path}})

    def client(self, *, recorder: Any, cache: Any) -> CrustdataClient:
        async def no_sleep(_: float) -> None:
            return None

        return CrustdataClient(
            "test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle)),
            recorder=recorder,
            cache=cache,
            rate_limiter=SlidingWindowRateLimiter({}),
            sleep=no_sleep,
            max_retries=0,
        )


def _h(credits: str) -> dict[str, str]:
    return {"x-credits-used": credits, "x-request-id": "req-fake"}


class FakeLlm:
    def __init__(self, query: str = "warehousing and logistics operators") -> None:
        self.query = query
        self.calls = 0

    async def extract_structured(self, system: str, user: str, schema: type) -> Any:
        self.calls += 1
        draft = InvestorSpecDraft(
            comparable_criteria=[],
            activity_query=self.query,
            funding_sought=FundingSoughtDraft(instrument="equity", quote="growth equity"),
        )
        return draft, None


class FakeClients:
    def __init__(self, api: FakeCrustdata, llm: Any = None) -> None:
        self.api = api
        self.llm_double = llm

    def crustdata(self, *, recorder: Any, cache: Any) -> CrustdataClient:
        return self.api.client(recorder=recorder, cache=cache)

    def llm(self, ctx: Any) -> Any:
        return self.llm_double
