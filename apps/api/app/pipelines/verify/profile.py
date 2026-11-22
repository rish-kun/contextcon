"""`verify.profile`: the public profile of the confirmed company (design §6.3 step 2).

One `company_enrich` call by the confirmed Crustdata id (2 credits). Every field becomes
an evidence row with its source and an as-of date: business, industry, locations,
founded year, headcount and its time series (a signal from professional profiles, not a
payroll count), funding rounds with dates, key people and hiring. The enrich record is
attached on the Crustdata id, so it corroborates itself; a record for any other id is
discarded.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.clients.crustdata import DEFAULT_ENRICH_FIELDS
from app.clients.crustdata_models import CompanyRecord
from app.domain.enums import SourceReliability
from app.jobs import StepContext, step_handler
from app.pipelines.verify import common
from app.pipelines.verify.common import PROFILE, ConfirmedEntity, normalize_name, parse_date
from app.rules.company_type import classify_company

ENRICH_CREDITS = 2

# Which source class each part of the enrich record is (the API maps these to chips).
PARTS: dict[str, str] = {
    "profile": SourceReliability.DATA_PROVIDER,
    "funding": SourceReliability.DATA_PROVIDER,
    "people": SourceReliability.DATA_PROVIDER,
    "headcount": SourceReliability.PROFESSIONAL_PROFILE_SIGNAL,
    "hiring": SourceReliability.PROFESSIONAL_PROFILE_SIGNAL,
}


def _hq_city(headquarters: str | None) -> str | None:
    if not headquarters:
        return None
    return headquarters.split(",")[0].strip() or None


def _person(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Enrich `people.*` entries: `{crustdata_person_id, basic_profile{name,
    current_title}, social_handles{professional_network_identifier{profile_url}}}`
    (seen live), with flat `name`/`title` keys accepted too."""
    basic = raw.get("basic_profile") or {}
    handles = (raw.get("social_handles") or {}).get("professional_network_identifier") or {}
    name = basic.get("name") or raw.get("name") or raw.get("full_name")
    if not name:
        return None
    return {
        "name": name,
        "person_id": raw.get("crustdata_person_id"),
        "title": basic.get("current_title") or raw.get("title") or raw.get("current_title"),
        "profile_url": handles.get("profile_url")
        or raw.get("linkedin_profile_url")
        or raw.get("profile_url"),
    }


def profile_rows(record: CompanyRecord, retrieved: date) -> list[dict[str, Any]]:
    """(part, field_path, value, as_of, key) for every profile fact present. Pure."""
    as_of = parse_date(record.updated_at) or retrieved
    rows: list[dict[str, Any]] = []

    def add(part: str, path: str, value: Any, when: date | None = None, key: str = "") -> None:
        if value in (None, "", [], {}):
            return
        rows.append(
            {"part": part, "field_path": path, "value": value, "as_of": when or as_of, "key": key}
        )

    info = record.basic_info
    if info:
        add("profile", "basic_info.name", info.name)
        add("profile", "basic_info.primary_domain", info.primary_domain)
        add("profile", "basic_info.website", info.website)
        add("profile", "basic_info.professional_network_url", info.professional_network_url)
        add("profile", "basic_info.description", info.description)
        add("profile", "basic_info.industries", info.industries)
        add("profile", "basic_info.year_founded", info.year_founded)
        add("profile", "basic_info.company_type", info.company_type)
        add("profile", "basic_info.employee_count_range", info.employee_count_range)
    loc = record.locations
    if loc:
        add("profile", "locations.headquarters", loc.headquarters)
        add("profile", "locations.country", loc.country)
        add("profile", "locations.all_office_addresses", loc.all_office_addresses)
    taxonomy = record.taxonomy or {}
    add(
        "profile",
        "taxonomy.professional_network_industry",
        taxonomy.get("professional_network_industry"),
    )
    add("profile", "taxonomy.categories", taxonomy.get("categories"))

    hc = record.headcount
    if hc:
        points = [
            {"date": p.date, "employee_count": p.employee_count}
            for p in hc.timeseries or []
            if p.date and p.employee_count is not None
        ]
        points.sort(key=lambda p: p["date"])
        latest = parse_date(points[-1]["date"]) if points else None
        add("headcount", "headcount.total", hc.total, latest)
        add("headcount", "headcount.timeseries", points, latest)
        yoy = (hc.growth_percent or {}).get("yoy")
        add("headcount", "headcount.growth_percent.yoy", yoy, latest)

    funding = record.funding
    if funding:
        add("funding", "funding.total_investment_usd", funding.total_investment_usd)
        last_round_at = parse_date(funding.last_fundraise_date)
        add("funding", "funding.last_round_type", funding.last_round_type, last_round_at)
        add("funding", "funding.num_funding_rounds", funding.num_funding_rounds)
        for i, round_ in enumerate(funding.milestones or []):
            when = parse_date(round_.funding_date or round_.date)
            value = {
                "round_type": round_.round_type,
                "date": when.isoformat() if when else None,
                "amount_usd": round_.amount_usd,
                "investors": list(round_.investors or []),
                "lead_investors": list(round_.lead_investors or []),
            }
            # Undated rounds are kept but never shown as dated (as_of stays None).
            rows.append(
                {
                    "part": "funding",
                    "field_path": f"funding.milestones[{i}]",
                    "value": value,
                    "as_of": when,
                    "key": f"{round_.round_type}:{value['date']}:{round_.amount_usd}",
                }
            )

    people = record.people
    if people:
        for group in ("founders", "cxos"):
            for raw in getattr(people, group) or []:
                person = _person(raw)
                if person:
                    add(
                        "people",
                        f"people.{group}",
                        person,
                        key=normalize_name(person["name"]),
                    )

    hiring = record.hiring
    if hiring:
        add("hiring", "hiring.openings_count", hiring.openings_count)
        add("hiring", "hiring.recent_titles_csv", hiring.recent_titles_csv)
    return rows


@step_handler(PROFILE)
async def build_profile(ctx: StepContext) -> dict[str, Any]:
    case = await common.load_case(ctx)
    try:
        entity = ConfirmedEntity.of(case)
    except common.IdentityNotConfirmed:
        return common.blocked_output(ctx)
    cid = entity.crustdata_company_id

    await ctx.require_budget(ENRICH_CREDITS)
    await ctx.set_detail("Reading the company record")
    client = common.clients.crustdata(ctx)
    try:
        results, _ = await client.enrich_company(cid, fields=DEFAULT_ENRICH_FIELDS)
    finally:
        await common.close_quietly(client)

    record = next(
        (m.company_data for r in results for m in r.matches if _record_id(m.company_data) == cid),
        None,
    )
    if record is None:
        ctx.result = "No company record returned for the confirmed id"
        return {"fields": 0}

    retrieved = datetime.now(UTC).date()
    rows = profile_rows(record, retrieved)
    sources: dict[str, Any] = {}
    entity_ref = common.attached_ref(entity.ref, ["crustdata_company_id"])
    for row in rows:
        part = row["part"]
        if part not in sources:
            sources[part] = await common.get_or_create_source(
                ctx,
                case,
                provider="crustdata",
                endpoint_or_url="/company/enrich",
                source_class=PARTS[part],
                request={"crustdata_company_ids": [cid], "part": part},
                title=f"Company record: {part}",
                publisher="Crustdata",
            )
        suffix = f":{row['key']}" if row["key"] else ""
        await common.upsert_evidence(
            ctx.session,
            sources[part],
            case_id=case.id,
            origin_key=f"crustdata:enrich:{cid}:{row['field_path']}{suffix}",
            entity_ref=entity_ref,
            field_path=row["field_path"],
            value=row["value"],
            as_of=row["as_of"],
            identity_confidence=1.0,
        )

    info = record.basic_info
    loc = record.locations
    founded = info.year_founded if info else None
    headcount = record.headcount.total if record.headcount else None
    stage = record.funding.last_round_type if record.funding else None
    decision = classify_company(founded, headcount, stage, retrieved)
    case.company_type = decision.company_type.value
    common.update_entity(
        case,
        hq_city=_hq_city(loc.headquarters if loc else None),
        headquarters=loc.headquarters if loc else None,
        country=loc.country if loc else None,
        founded_year=founded,
        headcount=headcount,
        industry=_top_industry(record),
        categories=list((record.taxonomy or {}).get("categories") or []),
        key_people=_key_people(record),
        company_type_reason=decision.reason,
        domains=list(
            dict.fromkeys(
                [
                    *entity.domains,
                    *(
                        [common.normalize_domain(info.primary_domain)]
                        if info and info.primary_domain
                        else []
                    ),
                ]
            )
        ),
    )
    await ctx.session.flush()
    ctx.result = f"{len(rows)} profile facts; {decision.company_type.value}"
    return {"fields": len(rows), "company_type": decision.company_type.value}


def _key_people(record: CompanyRecord) -> list[str]:
    """Founder and CXO full names: distinguishing attributes for later attachments."""
    names: list[str] = []
    if record.people:
        for raw in [*(record.people.founders or []), *(record.people.cxos or [])]:
            person = _person(raw)
            if person and len(person["name"].split()) >= 2:
                names.append(person["name"])
    return list(dict.fromkeys(names))[:12]


def _record_id(record: CompanyRecord) -> int | None:
    if record.crustdata_company_id is not None:
        return record.crustdata_company_id
    return record.basic_info.crustdata_company_id if record.basic_info else None


def _top_industry(record: CompanyRecord) -> str | None:
    if record.basic_info and record.basic_info.industries:
        return record.basic_info.industries[0]
    taxonomy = record.taxonomy or {}
    industries = taxonomy.get("professional_network_industries") or []
    return taxonomy.get("professional_network_industry") or (industries[0] if industries else None)
