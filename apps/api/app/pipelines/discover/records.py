"""Crustdata company data → sourced field values, `sources` rows and `evidence` rows.

Every value a shortlist card shows, and every value a criterion is judged on, is an
`evidence` row (provider field path + value + as-of date) pointing at a `sources`
row (endpoint, request, retrieved_at, reliability `data_provider`). Headcount and
its growth are labelled estimates; hiring is labelled a signal.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.base import CallRecord, utcnow
from app.db.models import ApiCache, Evidence, Source
from app.domain.enums import SourceReliability
from app.domain.types import CompanyRecord, FieldFact

PROVIDER = "crustdata"
RELIABILITY = SourceReliability.DATA_PROVIDER.value
# The API contract's SourceClass for a data-provider profile.
CONTRACT_SOURCE_CLASS = "data_provider_profile"

ESTIMATE_BASIS = "from professional profiles, not a payroll count"
SIGNAL_BASIS = "open job postings; a hiring signal, not evidence of revenue"

SOURCE_LABELS = {
    "/company/search": "Crustdata company search",
    "/company/enrich": "Crustdata company profile",
    "/job/search": "Crustdata job postings",
}


@dataclass
class FieldValue:
    key: str  # rules / display key, e.g. "locations.country"
    path: str  # provider field path the value was read from
    value: Any
    as_of: dt.date | None = None
    is_estimate: bool = False
    estimate_kind: str | None = None  # "estimate" | "signal"


def parse_date(raw: Any) -> dt.date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _get(data: dict[str, Any] | None, path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def company_id(company: dict[str, Any]) -> int | None:
    cid = company.get("crustdata_company_id") or _get(company, "basic_info.crustdata_company_id")
    return int(cid) if cid is not None else None


def company_name(company: dict[str, Any]) -> str:
    return _get(company, "basic_info.name") or f"Company {company_id(company)}"


def company_domain(company: dict[str, Any]) -> str | None:
    domain = _get(company, "basic_info.primary_domain")
    if not domain:
        return None
    return str(domain).strip().lower().removeprefix("www.") or None


# --- Field extraction ------------------------------------------------------------

# (key, provider paths tried in order). Search returns industries under
# taxonomy.professional_network_industries (a filter alias of basic_info.industries).
_PROFILE_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("name", ("basic_info.name",)),
    ("domain", ("basic_info.primary_domain",)),
    ("description", ("basic_info.description",)),
    ("basic_info.company_type", ("basic_info.company_type",)),
    ("basic_info.year_founded", ("basic_info.year_founded",)),
    (
        "basic_info.industries",
        ("basic_info.industries", "taxonomy.professional_network_industries"),
    ),
    ("taxonomy.professional_network_industry", ("taxonomy.professional_network_industry",)),
    ("taxonomy.categories", ("taxonomy.categories",)),
    ("locations.country", ("locations.country",)),
    ("locations.headquarters", ("locations.headquarters",)),
)
_ESTIMATE_PROFILE_FIELDS = (("basic_info.employee_count_range", "basic_info.employee_count_range"),)


def _profile_values(company: dict[str, Any], as_of: dt.date | None) -> list[FieldValue]:
    out: list[FieldValue] = []
    for key, paths in _PROFILE_FIELDS:
        for path in paths:
            value = _get(company, path)
            if _present(value):
                out.append(FieldValue(key, path, value, as_of))
                break
    for key, path in _ESTIMATE_PROFILE_FIELDS:
        value = _get(company, path)
        if _present(value):
            out.append(FieldValue(key, path, value, as_of, True, "estimate"))
    return out


def search_values(company: dict[str, Any]) -> list[FieldValue]:
    """Fields from a `company_search` row (basic_info, locations, taxonomy). Search
    rows carry no update date, so as_of is unknown."""
    return _profile_values(company, None)


def enrich_values(company: dict[str, Any]) -> list[FieldValue]:
    """Fields from a `company_enrich` match."""
    updated = parse_date(company.get("updated_at"))
    out = _profile_values(company, updated)

    headcount = company.get("headcount") or {}
    series = [p for p in headcount.get("timeseries") or [] if p.get("employee_count") is not None]
    latest = max(series, key=lambda p: p.get("date") or "", default=None)
    hc_as_of = parse_date(latest.get("date")) if latest else updated
    if _present(headcount.get("total")):
        out.append(
            FieldValue(
                "headcount.total", "headcount.total", headcount["total"], hc_as_of, True, "estimate"
            )
        )
    growth = headcount.get("growth_percent") or {}
    for key, names in (
        ("headcount.growth_percent.12m", ("yoy", "12m")),
        ("headcount.growth_percent.6m", ("six_months", "6m")),
    ):
        for name in names:
            if growth.get(name) is not None:
                out.append(
                    FieldValue(
                        key,
                        f"headcount.growth_percent.{name}",
                        growth[name],
                        hc_as_of,
                        True,
                        "estimate",
                    )
                )
                break

    funding = company.get("funding") or {}
    last_date = parse_date(funding.get("last_fundraise_date"))
    for key, path in (
        ("funding.last_round_type", "funding.last_round_type"),
        ("funding.total_investment_usd", "funding.total_investment_usd"),
        ("funding.last_fundraise_date", "funding.last_fundraise_date"),
    ):
        value = _get(company, path)
        if _present(value):
            out.append(FieldValue(key, path, value, last_date or updated))

    hiring = company.get("hiring") or {}
    if hiring.get("openings_count") is not None:
        out.append(
            FieldValue(
                "hiring.openings_count",
                "hiring.openings_count",
                hiring["openings_count"],
                updated,
                True,
                "signal",
            )
        )
    titles = [t.strip() for t in (hiring.get("recent_titles_csv") or "").split(",") if t.strip()]
    if titles:
        out.append(
            FieldValue(
                "hiring.recent_titles",
                "hiring.recent_titles_csv",
                titles[:10],
                updated,
                True,
                "signal",
            )
        )
    return out


def funding_rounds(company: dict[str, Any]) -> list[FieldValue]:
    """Dated rounds only; the milestone date is `funding_date`, else `date`."""
    out: list[FieldValue] = []
    milestones = (company.get("funding") or {}).get("milestones") or []
    for i, m in enumerate(milestones):
        when = parse_date(m.get("funding_date")) or parse_date(m.get("date"))
        if when is None:
            continue
        investors = list(m.get("investors") or []) or [
            d.get("name") for d in m.get("investors_detailed") or [] if d.get("name")
        ]
        value = {
            "round_type": m.get("round_type") or None,
            "date": when.isoformat(),
            "amount_usd": m.get("amount_usd"),
            "investors": investors,
        }
        out.append(FieldValue("funding.round", f"funding.milestones[{i}]", value, when))
    return out


def job_postings(listings: list[dict[str, Any]]) -> list[FieldValue]:
    out: list[FieldValue] = []
    for i, job in enumerate(listings):
        details = job.get("job_details") or {}
        title = details.get("title")
        if not title:
            continue
        added = parse_date((job.get("metadata") or {}).get("date_added"))
        location = job.get("location") or {}
        value = {
            "title": title,
            "date_added": added.isoformat() if added else None,
            "url": details.get("url"),
            "location": location.get("raw") or location.get("city"),
        }
        out.append(FieldValue("hiring.posting", f"job_listings[{i}]", value, added, True, "signal"))
    return out


# --- Sources and evidence rows -------------------------------------------------------


async def retrieved_at(session: AsyncSession, cache: Any, record: CallRecord) -> dt.datetime:
    """When the data was fetched from the provider. A cache replay keeps the time of
    the original fetch, not the time of the replay."""
    if record.from_cache and cache is not None:
        created = await session.scalar(
            select(ApiCache.created_at).where(
                ApiCache.cache_key == cache.storage_key(record.cache_key)
            )
        )
        if created is not None:
            return created
    return record.finished_at or utcnow()


async def add_source(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    endpoint: str,
    request: dict[str, Any],
    record: CallRecord,
    cache: Any,
) -> dict[str, Any]:
    """Insert a `sources` row for one provider call; returns its card reference."""
    when = await retrieved_at(session, cache, record)
    source = Source(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        run_id=run_id,
        provider=PROVIDER,
        endpoint_or_url=endpoint,
        request=request,
        retrieved_at=when,
        source_class=RELIABILITY,
        title=SOURCE_LABELS.get(endpoint, f"Crustdata {endpoint}"),
        publisher="Crustdata",
    )
    session.add(source)
    return source_ref(source.id, endpoint, when)


def source_ref(
    source_id: uuid.UUID | str, endpoint: str, when: dt.datetime | str
) -> dict[str, Any]:
    """`SourceRef` in the API contract's shape (JSON-ready)."""
    return {
        "source_id": str(source_id),
        "provider": PROVIDER,
        "label": SOURCE_LABELS.get(endpoint, f"Crustdata {endpoint}"),
        "url_or_endpoint": endpoint,
        "retrieved_at": when.isoformat() if isinstance(when, dt.datetime) else when,
        "source_class": CONTRACT_SOURCE_CLASS,
        "origin_id": None,
    }


def add_evidence(
    session: AsyncSession,
    *,
    source: dict[str, Any],
    crustdata_company_id: int,
    fv: FieldValue,
) -> dict[str, Any]:
    """Insert one `evidence` row (attached by Crustdata company id). Returns the
    JSON-ready fact the card and the rules use."""
    evidence_id = uuid.uuid4()
    session.add(
        Evidence(
            id=evidence_id,
            source_id=uuid.UUID(source["source_id"]),
            entity_ref=f"crustdata_company:{crustdata_company_id}",
            identity_confidence=1.0,
            field_path=fv.path,
            value=fv.value,
            as_of=fv.as_of,
            origin_key=f"crustdata:{source['url_or_endpoint']}:{crustdata_company_id}:{fv.path}",
        )
    )
    return {
        "key": fv.key,
        "path": fv.path,
        "value": fv.value,
        "evidence_id": str(evidence_id),
        "as_of": fv.as_of.isoformat() if fv.as_of else None,
        "is_estimate": fv.is_estimate,
        "estimate_kind": fv.estimate_kind,
        "source": source,
    }


def company_record(
    crustdata_company_id: int, name: str, facts: dict[str, dict[str, Any]]
) -> CompanyRecord:
    """The rules engine's view of a company: one sourced fact per field key."""
    return CompanyRecord(
        entity_id=str(crustdata_company_id),
        name=name,
        fields={
            key: FieldFact(
                value=f["value"],
                evidence_id=f["evidence_id"],
                as_of=parse_date(f.get("as_of")),
                is_estimate=bool(f.get("is_estimate")),
            )
            for key, f in facts.items()
        },
    )
