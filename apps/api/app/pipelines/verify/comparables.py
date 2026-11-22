"""`verify.comparables`: a few fair peers, or "No fair comparison found"
(design §6.6, builder call 23).

The basis is the subject's own profile: same top industry, same HQ country and a
headcount within ×0.5–×2 of the subject's (headcount is a signal, so the band is
generous on purpose). One bounded `company_search` with those filters (limit 10).
Returned peers are re-checked on country and headcount; the subject itself is dropped.
Fewer than two fair peers → no comparables, and the step output records the basis that
was tried. Each peer gets one sourced, dated observation.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete

from app.db.models import Comparable
from app.domain.enums import SourceReliability
from app.jobs import StepContext, step_handler
from app.pipelines.verify import common
from app.pipelines.verify.common import COMPARABLES, ConfirmedEntity

SEARCH_LIMIT = 10
MAX_PEERS = 5
MIN_PEERS = 2
# "Same activity": the top industry is coarse (seen live: it puts airlines and railways
# next to a parcel carrier), so a peer must also share activity categories with the
# subject: at least MIN_SHARED_CATEGORIES, and at least half of the smaller list.
MIN_SHARED_CATEGORIES = 2
MIN_CATEGORY_OVERLAP = 0.5
# 0.03 base + 0.2 headcount filter + 0.2 headcount and 0.1 taxonomy returned, per result.
SEARCH_CREDITS_ESTIMATE = round(SEARCH_LIMIT * 0.53, 2)
NO_FAIR = "No fair comparison found"


def basis_for(case_entity: dict[str, Any]) -> dict[str, Any] | None:
    industry = case_entity.get("industry")
    country = case_entity.get("country")
    headcount = case_entity.get("headcount")
    if not industry or not country or not headcount:
        return None
    lo, hi = math.ceil(headcount * 0.5), math.floor(headcount * 2)
    return {
        "categories": list(case_entity.get("categories") or []),
        "industry": industry,
        "country": country,
        "subject_headcount": headcount,
        "headcount_min": lo,
        "headcount_max": hi,
        "headcount_band": f"{lo}-{hi} (x0.5 to x2 of {headcount}, estimate)",
    }


def search_filters(basis: dict[str, Any]) -> dict[str, Any]:
    return {
        "op": "and",
        "conditions": [
            {"field": "basic_info.industries", "type": "in", "value": [basis["industry"]]},
            {"field": "locations.country", "type": "=", "value": basis["country"]},
            {"field": "headcount.total", "type": "=>", "value": basis["headcount_min"]},
            {"field": "headcount.total", "type": "=<", "value": basis["headcount_max"]},
        ],
    }


def same_activity(ours: list[str], theirs: list[str]) -> bool:
    a, b = {c.lower() for c in ours}, {c.lower() for c in theirs}
    if not a or not b:
        return False
    shared = len(a & b)
    return shared >= MIN_SHARED_CATEGORIES and shared >= MIN_CATEGORY_OVERLAP * min(len(a), len(b))


def fair_peers(companies: list[Any], basis: dict[str, Any], subject_id: int) -> list[Any]:
    peers = []
    for company in companies:
        cid = company.crustdata_company_id or (
            company.basic_info.crustdata_company_id if company.basic_info else None
        )
        headcount = company.headcount.total if company.headcount else None
        country = company.locations.country if company.locations else None
        if cid is None or cid == subject_id or headcount is None:
            continue
        if not basis["headcount_min"] <= headcount <= basis["headcount_max"]:
            continue
        if country and country.lower() != str(basis["country"]).lower():
            continue
        if basis.get("categories") and not same_activity(
            basis["categories"], (company.taxonomy or {}).get("categories") or []
        ):
            continue
        peers.append(company)
    peers.sort(key=lambda c: abs(math.log(c.headcount.total / basis["subject_headcount"])))
    return peers[:MAX_PEERS]


@step_handler(COMPARABLES)
async def comparables(ctx: StepContext) -> dict[str, Any]:
    case = await common.load_case(ctx)
    try:
        entity = ConfirmedEntity.of(case)
    except common.IdentityNotConfirmed:
        return common.blocked_output(ctx)
    await ctx.session.execute(delete(Comparable).where(Comparable.case_id == case.id))

    basis = basis_for(dict((case.identity_identifiers or {}).get("entity") or {}))
    if basis is None:
        ctx.result = f"{NO_FAIR}: industry, country or headcount unknown"
        return {
            "peers": 0,
            "no_fair_comparison": f"{NO_FAIR}: the profile lacks an industry, "
            "HQ country or headcount to compare on",
            "basis": None,
        }

    await ctx.require_budget(SEARCH_CREDITS_ESTIMATE)
    await ctx.set_detail("Searching for comparable companies")
    filters = search_filters(basis)
    client = common.clients.crustdata(ctx)
    try:
        found, _ = await client.search_companies(
            filters=filters,
            limit=SEARCH_LIMIT,
            fields=["crustdata_company_id", "basic_info", "locations", "headcount", "taxonomy"],
        )
    finally:
        await common.close_quietly(client)

    peers = fair_peers(found.companies, basis, entity.crustdata_company_id)
    if len(peers) < MIN_PEERS:
        reason = (
            f"{NO_FAIR}: {len(peers)} companies matched {basis['industry']}, "
            f"{basis['country']}, headcount {basis['headcount_band']}"
            + (" and shared activity categories" if basis.get("categories") else "")
        )
        ctx.result = reason
        return {"peers": 0, "no_fair_comparison": reason, "basis": basis}

    source = await common.get_or_create_source(
        ctx,
        case,
        provider="crustdata",
        endpoint_or_url="/company/search",
        source_class=SourceReliability.DATA_PROVIDER,
        request={"filters": filters, "limit": SEARCH_LIMIT, "part": "comparables"},
        title="Comparable companies",
        publisher="Crustdata",
    )
    retrieved = datetime.now(UTC).date()
    for peer in peers:
        cid = peer.crustdata_company_id or peer.basic_info.crustdata_company_id
        name = (peer.basic_info.name if peer.basic_info else None) or str(cid)
        hq = peer.locations.headquarters if peer.locations else None
        observation = f"Headcount about {peer.headcount.total} (estimate)" + (
            f", HQ {hq}" if hq else ""
        )
        evidence_id = await common.upsert_evidence(
            ctx.session,
            source,
            case_id=case.id,
            origin_key=f"crustdata:search:{cid}:headcount.total",
            entity_ref=common.attached_ref(f"crustdata:{cid}", ["crustdata_company_id"]),
            field_path="headcount.total",
            value={
                "name": name,
                "headcount": peer.headcount.total,
                "headquarters": hq,
                "country": peer.locations.country if peer.locations else None,
                "observation": observation,
            },
            as_of=common.parse_date(peer.updated_at) or retrieved,
        )
        ctx.session.add(
            Comparable(
                case_id=case.id,
                crustdata_company_id=str(cid),
                name=name[:500],
                basis=basis,
                evidence_id=evidence_id,
            )
        )
    await ctx.session.flush()
    ctx.result = f"{len(peers)} fair peers"
    return {"peers": len(peers), "basis": basis}
