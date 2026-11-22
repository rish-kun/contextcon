"""A fictional Crustdata world and a scripted LLM for the discover pipeline tests.

The Crustdata fake is a real `CrustdataClient` over an httpx mock transport, so the
client's caching, metering and error mapping are exercised; responses follow the
shapes recorded from the live API (search / enrich / job search / autocomplete).
Every company is fictional and named "... (fixture)".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx2

from app.clients import CrustdataClient, SlidingWindowRateLimiter
from app.clients.base import CallRecord, report

PRD_THESIS = (
    "privately held Indian warehousing and supply-chain software companies that serve "
    "enterprise customers and show recent expansion"
)

CRITERIA_DRAFT = {
    "criteria": [
        {
            "label": "Based in India",
            "kind": "must",
            "dimension": "geography",
            "operator": "equals",
            "value": "Indian",
            "crustdata_field": "locations.country",
            "thesis_quote": "Indian",
        },
        {
            "label": "Privately held",
            "kind": "must",
            "dimension": "ownership",
            "operator": "equals",
            "value": "privately held",
            "crustdata_field": "basic_info.company_type",
            "thesis_quote": "privately held",
        },
        {
            "label": "Warehousing and supply-chain software",
            "kind": "must",
            "dimension": "industry_activity",
            "operator": "contains",
            "value": "supply-chain software",
            "crustdata_field": None,
            "thesis_quote": "warehousing and supply-chain software",
        },
        {
            "label": "Serves enterprise customers",
            "kind": "preference",
            "dimension": "customer_type",
            "operator": "equals",
            "value": "enterprise",
            "crustdata_field": None,
            "thesis_quote": "serve enterprise customers",
        },
        {
            "label": "Recent expansion",
            "kind": "preference",
            "dimension": "growth_signal",
            "operator": "gte",
            "value": 10,
            "crustdata_field": "headcount.growth_percent.12m",
            "thesis_quote": "show recent expansion",
        },
    ],
    "activity_query": "warehousing and supply-chain software",
}

AUTOCOMPLETE: dict[str, list[str]] = {
    "locations.country": ["India", "Indonesia", "British Indian Ocean Territory"],
    "basic_info.company_type": ["Privately Held", "Public Company"],
    "basic_info.industries": [
        "Warehousing and Storage",
        "Warehousing",
        "Software Development",
        "Logistics & Supply Chain",
    ],
}

FILLER_NAMES = [
    "Kestrel",
    "Heron",
    "Falcon",
    "Osprey",
    "Plover",
    "Wren",
    "Lark",
    "Finch",
    "Robin",
    "Swift",
    "Martin",
    "Tern",
    "Egret",
    "Ibis",
    "Crane",
    "Stork",
    "Shrike",
    "Thrush",
    "Pipit",
    "Bunting",
    "Siskin",
    "Linnet",
    "Dunlin",
    "Avocet",
]


def _search_row(
    cid: int,
    name: str,
    domain: str,
    *,
    country: str | None,
    ctype: str,
    hq: str | None = "Pune, Maharashtra",
) -> dict[str, Any]:
    locations: dict[str, Any] = {}
    if country:
        locations["country"] = country
    if hq:
        locations["headquarters"] = hq
    return {
        "crustdata_company_id": cid,
        "basic_info": {
            "crustdata_company_id": cid,
            "name": f"{name} (fixture)",
            "primary_domain": domain,
            "website": f"https://{domain}",
            "description": f"{name} builds warehouse management software (fixture).",
            "company_type": ctype,
            "year_founded": 2016,
            "employee_count_range": "51-200",
        },
        "locations": locations,
        "taxonomy": {
            "professional_network_industry": "Software Development",
            "professional_network_industries": ["Software Development"],
        },
    }


def _enrich(
    row: dict[str, Any],
    *,
    ctype: str | None,
    growth: float | None,
    funding: bool = True,
    headcount: bool = True,
    openings: int | None = 4,
) -> dict:
    data = json.loads(json.dumps(row))
    data["basic_info"]["company_type"] = ctype or ""
    data["updated_at"] = "2026-11-01T00:00:00Z"
    if headcount:
        data["headcount"] = {
            "total": 140,
            "timeseries": [
                {"date": "2025-11-01", "employee_count": 110},
                {"date": "2026-10-01", "employee_count": 140},
            ],
            "growth_percent": {"yoy": growth} if growth is not None else {},
        }
    if funding:
        data["funding"] = {
            "total_investment_usd": 4500000,
            "last_round_type": "series_a",
            "last_fundraise_date": "2024-03-01",
            "milestones": [
                {
                    "round_type": "series_a",
                    "funding_date": "2024-03-01",
                    "amount_usd": 4000000,
                    "investors": ["Example Ventures (fixture)"],
                },
                {"round_type": "seed", "date": "2022-06-15", "amount_usd": 500000, "investors": []},
                {"round_type": "angel", "amount_usd": 100000},  # undated: never shown
            ],
        }
    if openings is not None:
        data["hiring"] = {"openings_count": openings, "recent_titles_csv": "WMS Engineer,Sales"}
    return data


@dataclass
class World:
    search_rows: list[dict[str, Any]]
    enriched: dict[int, dict[str, Any]]
    jobs: dict[int, list[dict[str, Any]]]


def make_world(fillers: int = 10) -> World:
    a = _search_row(
        101, "Alpha Warehouse Tech", "alpha.example", country="India", ctype="Privately Held"
    )
    b = _search_row(102, "Beta Supply Systems", "beta.example", country="India", ctype="")
    c = _search_row(103, "Gamma Logistics Cloud", "gamma.example", country="India", ctype="")
    d = _search_row(
        104,
        "Delta Freight Labs",
        "delta.example",
        country="Singapore",
        ctype="Privately Held",
        hq="Singapore",
    )
    e = json.loads(json.dumps(a))  # same Crustdata id as A: a duplicate
    f = _search_row(
        106,
        "Alpha Warehouse Tech India",
        "www.alpha.example",
        country="India",
        ctype="Privately Held",
    )  # same domain as A
    g = _search_row(107, "Omega Stores", "omega.example", country=None, ctype="", hq=None)
    rows = [a, b, c, d, e, f, g]
    enriched = {
        101: _enrich(a, ctype="Privately Held", growth=25.0),
        102: _enrich(b, ctype="Public Company", growth=30.0),
        103: _enrich(c, ctype=None, growth=None, funding=False),
        107: _enrich(g, ctype=None, growth=None, funding=False, headcount=False, openings=None),
    }
    for i in range(fillers):
        cid = 200 + i
        name = f"{FILLER_NAMES[i]} Logistics Software"
        row = _search_row(
            cid, name, f"{FILLER_NAMES[i].lower()}.example", country="India", ctype="Privately Held"
        )
        rows.append(row)
        enriched[cid] = _enrich(row, ctype="Privately Held", growth=5.0)
    jobs = {
        101: [
            {
                "crustdata_job_id": 1,
                "job_details": {"title": "WMS Engineer", "url": "https://alpha.example/jobs/wms"},
                "location": {"raw": "Pune"},
                "metadata": {"date_added": "2026-10-20"},
            },
            {
                "crustdata_job_id": 2,
                "job_details": {"title": "Enterprise Account Executive"},
                "location": {"city": "Mumbai"},
                "metadata": {"date_added": "2026-11-02"},
            },
        ]
    }
    return World(rows, enriched, jobs)


@dataclass
class FakeCrustdata:
    world: World
    semantic_disabled: bool = False
    reject_is_null: bool = False
    search_price: float = 0.13
    search_bodies: list[dict[str, Any]] = field(default_factory=list)
    enrich_bodies: list[dict[str, Any]] = field(default_factory=list)
    job_bodies: list[dict[str, Any]] = field(default_factory=list)
    autocomplete_bodies: list[dict[str, Any]] = field(default_factory=list)

    @property
    def paid_http_calls(self) -> int:
        return len(self.search_bodies) + len(self.enrich_bodies) + len(self.job_bodies)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content or b"{}")
        path = request.url.path
        if path == "/company/search/autocomplete":
            self.autocomplete_bodies.append(body)
            q = body["query"].lower()[:4]
            values = [v for v in AUTOCOMPLETE.get(body["field"], []) if q in v.lower()]
            return httpx2.Response(
                200,
                json={"suggestions": [{"value": v} for v in values]},
                headers={"x-credits-used": "0"},
            )
        if path == "/company/search":
            self.search_bodies.append(body)
            if self.semantic_disabled and "search" in body:
                return httpx2.Response(
                    403,
                    json={
                        "error": {
                            "type": "permission_error",
                            "message": "Company semantic search is not available for your account",
                        }
                    },
                    headers={"x-credits-used": "0"},
                )
            if self.reject_is_null and "is_null" in json.dumps(body.get("filters")):
                return httpx2.Response(
                    400,
                    json={"error": {"type": "invalid_request", "message": "bad operator"}},
                    headers={"x-credits-used": "0"},
                )
            rows = self.world.search_rows[: body.get("limit", 20)]
            return httpx2.Response(
                200,
                json={"companies": rows, "next_cursor": None, "total_count": None},
                headers={"x-credits-used": f"{self.search_price * len(rows):.2f}"},
            )
        if path == "/company/enrich":
            self.enrich_bodies.append(body)
            out = []
            for cid in body["crustdata_company_ids"]:
                data = self.world.enriched.get(cid)
                out.append(
                    {
                        "matched_on": str(cid),
                        "match_type": "crustdata_company_id",
                        "matches": [{"confidence_score": 1.0, "company_data": data}]
                        if data
                        else [],
                    }
                )
            matched = sum(1 for o in out if o["matches"])
            return httpx2.Response(200, json=out, headers={"x-credits-used": str(2 * matched)})
        if path == "/job/search":
            self.job_bodies.append(body)
            listings = self.world.jobs.get(body["filters"]["value"], [])[: body["limit"]]
            return httpx2.Response(
                200,
                json={"job_listings": listings, "next_cursor": None, "total_count": len(listings)},
                headers={"x-credits-used": f"{0.03 * len(listings):.2f}"},
            )
        return httpx2.Response(404, json={"error": {"type": "not_found", "message": path}})

    def client(self, *, recorder: Any, cache: Any) -> CrustdataClient:
        async def no_sleep(_: float) -> None:
            return None

        return CrustdataClient(
            "test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle)),
            recorder=recorder,
            cache=cache,
            rate_limiter=SlidingWindowRateLimiter({}),
            sleep=no_sleep,
            max_retries=0,
        )


class FakeLlm:
    """Criteria extraction and shortlist drafting without a network. Every call is
    reported to the recorder like the real client (tokens and USD)."""

    def __init__(self, recorder: Any = None, *, fail_drafts: bool = False) -> None:
        self.recorder = recorder
        self.fail_drafts = fail_drafts
        self.calls = 0

    async def _record(self) -> CallRecord:
        self.calls += 1
        record = CallRecord(
            provider="anthropic",
            endpoint="/v1/messages",
            params_hash="h",
            cache_key=f"fake-{self.calls}",
            status="succeeded",
            model="fake",
            input_tokens=200,
            output_tokens=60,
            cost_usd=0.00005,
            usage_known=True,
            attempts=1,
        )
        await report(self.recorder, record)
        return record

    async def extract_structured(self, system: str, user: str, schema: type) -> Any:
        return schema.model_validate(CRITERIA_DRAFT), await self._record()

    async def draft_text(self, system: str, user: str) -> Any:
        record = await self._record()
        if self.fail_drafts:
            return "This company is a great investment.", record
        payload = json.loads(user.split("\n\nYour previous draft")[0])
        sentences = []
        for r in payload["criteria_results"]:
            if r["result"] == "pass":
                sentences.append(f"It meets the requirement: {r['label']} [{r['id']}].")
            elif r["result"] == "unknown":
                sentences.append(f"It is not yet known whether: {r['label']} [{r['id']}].")
        return " ".join(sentences), record


def llm_factory(**overrides: Any):  # type: ignore[no-untyped-def]
    def make(*, recorder: Any, cache: Any) -> FakeLlm:
        return FakeLlm(recorder, **overrides)

    return make
