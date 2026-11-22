"""Company lookup before a case opens: which companies match a typed name.

`company/identify` by name first (0.2 credits per match); when it finds fewer than two,
one natural-language `company/search` (limit 8) widens the list. Results are deduped by
Crustdata id, ranked exact-name / primary-domain matches first, then by headcount, and
cached per workspace and query.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Query

from app.api._base import fixtures_enabled, make_router
from app.api.schemas.common import ApiModel
from app.auth.deps import WorkspaceId
from app.clients.base import InMemoryRecorder
from app.clients.crustdata import CrustdataClient
from app.clients.crustdata_models import CompanyBasicInfo

router = make_router(prefix="/companies", tags=["companies"])

SEARCH_LIMIT = 8
CACHE_MAX = 512
DESCRIPTION_CHARS = 200


class CompanyCandidateOut(ApiModel):
    crustdata_id: int
    name: str
    domain: str | None = None
    description: str | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    founded_year: int | None = None
    headcount: int | None = None
    industry: str | None = None
    listed: bool = False


class CompanyLookupOut(ApiModel):
    query: str
    candidates: list[CompanyCandidateOut]
    credits_used: float = 0


def make_lookup_client() -> Callable[[Any], CrustdataClient]:
    def build(recorder: Any) -> CrustdataClient:
        return CrustdataClient.from_settings(recorder=recorder)

    return build


ClientFactory = Annotated[Callable[[Any], CrustdataClient], Depends(make_lookup_client)]

# Per (workspace, normalized query). Never shared across workspaces.
_cache: dict[tuple[uuid.UUID | None, str], CompanyLookupOut] = {}


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _truncate(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= DESCRIPTION_CHARS else text[: DESCRIPTION_CHARS - 1] + "…"


def _listed(*blobs: Any) -> bool:
    for blob in blobs:
        if isinstance(blob, dict):
            for key, value in blob.items():
                if value and any(t in str(key).lower() for t in ("ticker", "exchange")):
                    return True
    return False


def _candidate(
    cid: int | None,
    info: CompanyBasicInfo | None,
    *,
    hq: Any = None,
    country: str | None = None,
    headcount: int | None = None,
    extra: tuple[Any, ...] = (),
) -> CompanyCandidateOut | None:
    if cid is None or info is None or not info.name:
        return None
    city = str(hq).split(",")[0].strip() if hq else None
    return CompanyCandidateOut(
        crustdata_id=int(cid),
        name=info.name,
        domain=info.primary_domain,
        description=_truncate(info.description),
        hq_city=city or None,
        hq_country=country,
        founded_year=info.year_founded,
        headcount=headcount,
        industry=(info.industries or [None])[0],
        listed=_listed(info.model_dump(), *extra),
    )


def rank(query: str, candidates: list[CompanyCandidateOut]) -> list[CompanyCandidateOut]:
    q = _norm(query)

    def exact(c: CompanyCandidateOut) -> bool:
        stem = _norm((c.domain or "").split(".")[0])
        return _norm(c.name) == q or (bool(stem) and stem == q)

    return sorted(candidates, key=lambda c: (not exact(c), -(c.headcount or 0)))


async def lookup(client: CrustdataClient, query: str) -> list[CompanyCandidateOut]:
    found: dict[int, CompanyCandidateOut] = {}
    results, _ = await client.identify_company(names=[query])
    for result in results:
        for match in result.matches:
            data = match.company_data
            c = _candidate(
                data.crustdata_company_id, data.basic_info, extra=(data.social_profiles,)
            )
            if c is not None and c.crustdata_id not in found:
                found[c.crustdata_id] = c
    if len(found) < 2:
        search, _ = await client.search_companies(query=query, limit=SEARCH_LIMIT)
        for rec in search.companies:
            loc = rec.locations
            c = _candidate(
                rec.crustdata_company_id
                or (rec.basic_info.crustdata_company_id if rec.basic_info else None),
                rec.basic_info,
                hq=loc.headquarters if loc else None,
                country=loc.country if loc else None,
                headcount=rec.headcount.total if rec.headcount else None,
                extra=(rec.metadata, rec.taxonomy),
            )
            if c is None:
                continue
            prior = found.get(c.crustdata_id)
            if prior is None:
                found[c.crustdata_id] = c
            else:  # search carries location and headcount that identify lacks
                found[c.crustdata_id] = prior.model_copy(
                    update={
                        k: v
                        for k, v in c.model_dump().items()
                        if getattr(prior, k) in (None, False)
                    }
                )
    return rank(query, list(found.values()))


def _fixture(query: str) -> CompanyLookupOut:
    rows = [
        CompanyCandidateOut(
            crustdata_id=631394,
            name="Acme Robotics",
            domain="acmerobotics.com",
            description="Warehouse picking robots for mid-size distributors.",
            hq_city="Austin",
            hq_country="USA",
            founded_year=2019,
            headcount=140,
            industry="Industrial Automation",
        ),
        CompanyCandidateOut(
            crustdata_id=118220,
            name="Acme Corp",
            domain="acme.com",
            description="Diversified manufacturer of consumer and industrial goods.",
            hq_city="Chicago",
            hq_country="USA",
            founded_year=1948,
            headcount=12000,
            industry="Manufacturing",
            listed=True,
        ),
    ]
    return CompanyLookupOut(query=query, candidates=rank(query, rows))


@router.get("/lookup", response_model=CompanyLookupOut)
async def lookup_companies(
    workspace_id: WorkspaceId,
    make_client: ClientFactory,
    q: Annotated[str, Query(min_length=1, max_length=200)],
) -> CompanyLookupOut:
    """Companies matching a typed name, each with a short description, to pick from
    before a case opens."""
    query = " ".join(q.split())
    if fixtures_enabled():
        return _fixture(query)
    key = (workspace_id, query.lower())
    if key in _cache:
        return _cache[key].model_copy(update={"credits_used": 0})
    recorder = InMemoryRecorder()
    client = make_client(recorder)
    try:
        candidates = await lookup(client, query)
    finally:
        await client.aclose()
    credits = sum(float(r.credits_used or 0) for r in recorder.final())
    out = CompanyLookupOut(query=query, candidates=candidates, credits_used=credits)
    if len(_cache) >= CACHE_MAX:  # drop the oldest entry; dicts keep insertion order
        _cache.pop(next(iter(_cache)))
    _cache[key] = out
    return out
