"""Fake Crustdata API (a real `CrustdataClient` over a mock transport, so caching and the
cost ledger run for real) and a scripted LLM for the verify pipeline tests.

All companies are fictional and end in "(fixture)"."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2

from app.clients import CrustdataClient, SlidingWindowRateLimiter
from app.extraction.facts import EvidenceFactsDraft, FactDraft


def company(
    cid: int,
    name: str,
    domain: str | None,
    *,
    confidence: float = 0.95,
    founded: int | None = 2014,
    all_domains: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "confidence_score": confidence,
        "company_data": {
            "crustdata_company_id": cid,
            "basic_info": {
                "crustdata_company_id": cid,
                "name": name,
                "primary_domain": domain,
                "all_domains": all_domains or ([domain] if domain else []),
                "website": f"https://{domain}" if domain else None,
                "professional_network_url": f"https://profiles.example/company/{cid}",
                "year_founded": founded,
                "industries": ["Transportation, Logistics, Supply Chain and Storage"],
            },
        },
    }


def enrich_record(cid: int, name: str, domain: str, *, headcount: int = 420) -> list[dict]:
    return [
        {
            "matched_on": str(cid),
            "match_type": "crustdata_company_id",
            "matches": [
                {
                    "confidence_score": 1.0,
                    "company_data": {
                        "crustdata_company_id": cid,
                        "updated_at": "2026-11-01T00:00:00Z",
                        "basic_info": {
                            "crustdata_company_id": cid,
                            "name": name,
                            "primary_domain": domain,
                            "description": "Warehousing and freight forwarding.",
                            "industries": ["Transportation, Logistics, Supply Chain and Storage"],
                            "year_founded": 2014,
                        },
                        "locations": {"headquarters": "Pune, Maharashtra, India", "country": "IND"},
                        "headcount": {
                            "total": headcount,
                            "timeseries": [
                                {"date": "2025-11-01", "employee_count": 350},
                                {"date": "2026-11-01", "employee_count": headcount},
                            ],
                            "growth_percent": {"yoy": 20.0},
                        },
                        "funding": {
                            "total_investment_usd": 12000000,
                            "last_round_type": "series_a",
                            "last_fundraise_date": "2024-06-10",
                            "milestones": [
                                {
                                    "round_type": "series_a",
                                    "funding_date": "2024-06-10",
                                    "amount_usd": 12000000,
                                    "investors": ["Example Ventures (fixture)"],
                                }
                            ],
                        },
                        "people": {
                            "founders": [
                                {
                                    "name": "Asha Founder (fixture)",
                                    "title": "Co-founder & CEO",
                                    "linkedin_profile_url": "https://profiles.example/in/asha",
                                    "email": "asha@example.test",
                                }
                            ]
                        },
                        "hiring": {"openings_count": 7, "recent_titles_csv": "Ops lead,Driver"},
                    },
                }
            ],
        }
    ]


def page(url: str, title: str, body: str, *, published: str | None = "2026-10-05") -> dict:
    meta = (
        f'<meta property="article:published_time" content="{published}T09:00:00Z">'
        if published
        else ""
    )
    html = (
        f"<html><head><title>{title}</title>{meta}</head><body><nav>Menu</nav>"
        f"<article><h1>{title}</h1>{body}</article><footer>Footer</footer></body></html>"
    )
    return {"success": True, "url": url, "title": title, "content": html, "timestamp": 1}


@dataclass
class FakeCrustdata:
    identify: dict[tuple[str, str], list[dict]] = field(default_factory=dict)
    enrich: dict[int, list[dict]] = field(default_factory=dict)
    # query -> search hits; a missing query returns no hits
    web: dict[str, list[dict]] = field(default_factory=dict)
    web_default: list[dict] = field(default_factory=list)
    pages: dict[str, dict] = field(default_factory=dict)
    companies: list[dict] = field(default_factory=list)
    requests: list[tuple[str, dict]] = field(default_factory=list)

    def calls(self, path: str) -> list[dict]:
        return [body for p, body in self.requests if p == path]

    def _respond(self, path: str, body: dict) -> tuple[Any, float]:
        if path == "/company/identify":
            (kind, values), *_ = [(k, v) for k, v in body.items() if k != "exact_match"]
            matches = self.identify.get((kind, values[0]), [])
            data = [{"matched_on": values[0], "match_type": kind, "matches": matches}]
            return data, 0.2 if matches else 0
        if path == "/company/enrich":
            cid = body["crustdata_company_ids"][0]
            return self.enrich.get(cid, []), 2
        if path == "/web/search/live":
            hits = self.web.get(body["query"], self.web_default)
            return {"success": True, "query": body["query"], "results": hits}, 1
        if path == "/web/enrich/live":
            return [self.pages.get(u, {"success": False, "url": None}) for u in body["urls"]], len(
                body["urls"]
            )
        if path == "/company/search":
            return {"companies": self.companies, "next_cursor": None}, 0.43 * len(self.companies)
        raise AssertionError(f"unexpected path {path}")

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        data, credits = self._respond(request.url.path, body)
        return httpx2.Response(200, json=data, headers={"x-credits-used": str(credits)})

    def factory(self, ctx: Any) -> CrustdataClient:
        async def no_sleep(_: float) -> None:
            return None

        return CrustdataClient(
            "test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle)),
            recorder=ctx.recorder,
            cache=ctx.cache,
            rate_limiter=SlidingWindowRateLimiter({}),
            sleep=no_sleep,
            max_retries=0,
        )


_EVIDENCE = re.compile(r"<evidence>\n(.*)\n</evidence>", re.S)

DEFAULT_RULES: list[tuple[str, str]] = [
    ("cin", r"CIN:?\s*([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})"),
    ("incorporation_date", r"Date of Incorporation:?\s*(\d{1,2} \w+ \d{4})"),
    ("incorporation_place", r"Registrar of Companies:?\s*(RoC[- ]\w+)"),
    ("legal_name", r"Company Name:?\s*([^\n]+?)\s*(?:\n|$)"),
    ("event", r"([^.\n]*\b(?:opens|launch\w*|raised|plans to)\b[^.\n]*\.)"),
]


@dataclass
class FakeLlm:
    """Extracts facts with regexes over the evidence text; every span is verbatim."""

    rules: list[tuple[str, str]] = field(default_factory=lambda: list(DEFAULT_RULES))
    prompts: list[str] = field(default_factory=list)
    transform: Callable[[EvidenceFactsDraft], EvidenceFactsDraft] | None = None

    async def extract_structured(self, system: str, user: str, schema: type) -> tuple[Any, None]:
        self.prompts.append(user)
        m = _EVIDENCE.search(user)
        text = m.group(1) if m else ""
        facts = []
        for name, pattern in self.rules:
            found = re.search(pattern, text)
            if found:
                facts.append(FactDraft(name=name, value=found.group(1), span=found.group(0)))
        draft = EvidenceFactsDraft(speaks_to_claim=bool(facts), facts=facts)
        if self.transform:
            draft = self.transform(draft)
        return draft, None

    async def aclose(self) -> None:
        return None
