"""Client factories for the discover steps, replaceable in tests.

Inside a step every paid call goes through the step's recorder (cost ledger, charged
to the discovery run) and cache (a resumed step replays instead of paying again).
Autocomplete is free and unmetered, so it runs on a client without a recorder.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.clients.crustdata import CrustdataClient
from app.clients.llm import LLMClient

AUTOCOMPLETE = "/company/search/autocomplete"


def _crustdata(*, recorder: Any, cache: Any) -> CrustdataClient:
    return CrustdataClient.from_settings(recorder=recorder, cache=cache)


def _llm(*, recorder: Any, cache: Any) -> Any:
    return LLMClient.from_settings(recorder=recorder, cache=cache)


@dataclass
class Factories:
    crustdata: Callable[..., CrustdataClient] = _crustdata
    llm: Callable[..., Any] = _llm


factories = Factories()


@contextmanager
def use(
    *,
    crustdata: Callable[..., CrustdataClient] | None = None,
    llm: Callable[..., Any] | None = None,
):  # type: ignore[no-untyped-def]
    """Temporarily swap the factories (tests)."""
    old = Factories(factories.crustdata, factories.llm)
    if crustdata is not None:
        factories.crustdata = crustdata
    if llm is not None:
        factories.llm = llm
    try:
        yield factories
    finally:
        factories.crustdata, factories.llm = old.crustdata, old.llm


async def autocomplete(
    client: CrustdataClient, field: str, query: str, limit: int = 10
) -> list[str]:
    """Stored values of a categorical company field (free endpoint).

    `CrustdataClient` has no public method for it yet; this uses the client's own
    transport so auth, retries and the response cache still apply.
    """
    data, _ = await client._post(AUTOCOMPLETE, {"field": field, "query": query, "limit": limit})
    suggestions = (data or {}).get("suggestions") or []
    return [s["value"] for s in suggestions if isinstance(s, dict) and s.get("value")]
