"""Scripted provider clients for pipeline tests. No network, no credits."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.clients.crustdata_models import (
    EnrichResult,
    PersonSearchResult,
    WebPage,
    WebSearchResult,
)
from tests.extraction.fakes import FakeLlm


@dataclass
class RoutedLlm:
    """Answers `extract_structured` by schema name, through a responder per schema.

    A responder gets `(system, user)` and returns a dict for the schema. Every call
    is recorded with the full user text, so tests can assert what reached the model.
    """

    responders: dict[str, Any] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def extract_structured(self, system: str, user: str, schema: type[Any]) -> Any:
        name = schema.__name__
        self.calls.append((name, user))
        responder = self.responders.get(name)
        if responder is None:
            defaults = {
                "PiiDraft": {"items": []},
                "NormaliseDraft": {"claims": []},
                "EvidenceFactsDraft": {"speaks_to_claim": False, "facts": []},
                "ClaimsDraft": {"claims": []},
            }
            if name not in defaults:
                raise AssertionError(f"RoutedLlm: no responder for {name}")
            return defaults[name], {"n": len(self.calls)}
        value = responder(system, user) if callable(responder) else responder
        return value, {"n": len(self.calls)}

    def users(self, schema_name: str) -> list[str]:
        return [u for n, u in self.calls if n == schema_name]


def claims_draft(*claims: dict) -> dict:
    return {"claims": list(claims)}


def evidence_block(user: str) -> str:
    return user.split("<evidence>\n", 1)[1].rsplit("\n</evidence>", 1)[0]


def claim_block(user: str) -> dict:
    return json.loads(user.split("<claim>\n", 1)[1].split("\n</claim>", 1)[0])


@dataclass
class FakeCrustdata:
    """Records every call with its parameters; answers from canned data."""

    enrich: dict[str, Any] | None = None
    people: list[dict[str, Any]] = field(default_factory=list)
    search_hits: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pages: dict[str, str] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail: dict[str, Exception] = field(default_factory=dict)

    def _call(self, name: str, **params: Any) -> None:
        self.calls.append((name, params))
        if name in self.fail:
            raise self.fail[name]

    async def enrich_company(self, ids: Any, *, fields: Any = ()) -> Any:
        self._call("enrich_company", ids=ids, fields=list(fields))
        if self.enrich is None:
            return [], None
        data = {"matches": [{"confidence_score": 1.0, "company_data": self.enrich}]}
        return [EnrichResult.model_validate(data)], None

    async def search_company_leadership(self, company_id: int, **kw: Any) -> Any:
        self._call("search_company_leadership", company_id=company_id, **kw)
        return PersonSearchResult.model_validate({"profiles": self.people}), None

    async def web_search(self, query: str, **kw: Any) -> Any:
        self._call("web_search", query=query, **kw)
        topic = next((t for t in self.search_hits if t in query), None)
        hits = self.search_hits.get(topic, []) if topic else []
        return WebSearchResult.model_validate({"success": True, "results": hits}), None

    async def fetch_pages(self, urls: list[str], **kw: Any) -> Any:
        self._call("fetch_pages", urls=list(urls))
        pages = [
            WebPage(success=True, url=u, title="", content=self.pages[u])
            for u in urls
            if u in self.pages
        ]
        return pages, None

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


@dataclass
class FakeFactory:
    llm_client: Any = None
    crustdata_client: Any = None

    def crustdata(self, ctx: Any) -> Any:
        return self.crustdata_client

    def llm(self, ctx: Any, *, delete_after: Any) -> Any:
        return self.llm_client


__all__ = ["FakeCrustdata", "FakeFactory", "FakeLlm", "RoutedLlm"]
