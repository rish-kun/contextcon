"""Crustdata company records → compact, contact-free funding data → `FundingRecord`s.

Ingestion is a whitelist: only the fields below are kept, so personal contact details
(emails, phone numbers, personal profile links) never reach the database, whatever the
provider returns. `CrustdataClient` already drops email/phone keys from responses; this
is the second line of defence and also drops profile URLs.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from app.clients.crustdata import strip_contact_fields
from app.clients.crustdata_models import CompanyRecord
from app.domain.types import FundingRecord
from app.rules.compare import normalize_text

# Keys dropped from anything cached: personal profile links, and the people group
# (never requested here; dropped if a provider sends it anyway).
_PERSONAL_KEY = re.compile(
    r"profile_url|linkedin|twitter|facebook|instagram|permalink|^people$", re.IGNORECASE
)


def scrub_personal(value: Any) -> Any:
    """Contact fields and personal profile links removed, recursively."""
    value = strip_contact_fields(value)
    if isinstance(value, dict):
        return {k: scrub_personal(v) for k, v in value.items() if not _PERSONAL_KEY.search(k)}
    if isinstance(value, list):
        return [scrub_personal(v) for v in value]
    return value


class ScrubbingCache:
    """Wraps the step's response cache so cached Crustdata bodies hold no personal
    contact details or profile links either (`CrustdataClient` strips only emails and
    phone numbers before caching)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def get(self, key: str) -> Any | None:
        return await self.inner.get(key)

    async def set(self, key: str, value: Any) -> None:
        await self.inner.set(key, scrub_personal(value))


# Investor attributes kept. Profile links (`permalink`, `crunchbase_profile_url`) are
# dropped: for an individual investor they are a personal profile link.
INVESTOR_KEYS = ("name", "uuid", "type")


def parse_date(value: Any) -> dt.date | None:
    if not value or not isinstance(value, str):
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value or None


def _sectors(record: CompanyRecord) -> list[str]:
    tax = record.taxonomy or {}
    found: list[str] = []
    for key in ("professional_network_industries", "categories"):
        v = tax.get(key)
        if isinstance(v, list):
            found += [s for s in v if isinstance(s, str)]
    single = tax.get("professional_network_industry")
    if isinstance(single, str):
        found.append(single)
    if record.basic_info and record.basic_info.industries:
        found += record.basic_info.industries
    seen: dict[str, str] = {}
    for s in found:
        s = " ".join(s.split())
        if s and s.casefold() not in seen:
            seen[s.casefold()] = s
    return list(seen.values())


def _investors(round_: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in round_.get("investors_detailed") or []:
        if not isinstance(item, dict):
            continue
        inv = {k: _clean_str(item.get(k)) for k in INVESTOR_KEYS}
        if not inv["name"] and not inv["uuid"]:
            continue
        out.append(inv)
        if inv["name"]:
            names.add(normalize_text(inv["name"]))
    for name in (round_.get("investors") or []) + (round_.get("lead_investors") or []):
        name = _clean_str(name)
        if name and normalize_text(name) not in names:
            out.append({"name": name, "uuid": None, "type": None})
            names.add(normalize_text(name))
    return out


def compact_company(raw: CompanyRecord | dict[str, Any]) -> dict[str, Any]:
    """The funding view of one company: identity, sectors and dated rounds."""
    data = strip_contact_fields(raw.model_dump() if isinstance(raw, CompanyRecord) else dict(raw))
    record = CompanyRecord.model_validate(data)
    info = record.basic_info
    funding = data.get("funding") if isinstance(data.get("funding"), dict) else {}
    rounds = []
    for i, m in enumerate(funding.get("milestones") or []):
        if not isinstance(m, dict):
            continue
        date = parse_date(m.get("funding_date")) or parse_date(m.get("date"))
        amount = m.get("amount_usd")
        leads = [n for n in (_clean_str(x) for x in m.get("lead_investors") or []) if n]
        rounds.append(
            {
                "index": i,
                "round_type": _clean_str(m.get("round_type")),
                "date": date.isoformat() if date else None,
                "amount_usd": float(amount) if isinstance(amount, int | float) else None,
                "investors": _investors(m),
                "lead_investors": leads,
            }
        )
    company_id = record.crustdata_company_id or (info.crustdata_company_id if info else None)
    return {
        "company_id": company_id,
        "name": (info.name if info else None) or f"Company {company_id}",
        "domain": info.primary_domain if info else None,
        "country": record.locations.country if record.locations else None,
        "headquarters": record.locations.headquarters if record.locations else None,
        "sectors": _sectors(record),
        "rounds": rounds,
    }


def has_dated_rounds(raw: CompanyRecord) -> bool:
    """True when a record already carries dated rounds with investors (no enrich needed)."""
    milestones = raw.funding.milestones if raw.funding else None
    return any(
        (m.funding_date or m.date) and (m.investors or m.investors_detailed)
        for m in milestones or []
    )


def funding_records(companies: list[dict[str, Any]]) -> list[FundingRecord]:
    """One record per (round, investor). A round with no investor yields one unnamed
    record so the rules can exclude it visibly. Rounds need an `evidence_id`."""
    records: list[FundingRecord] = []
    for c in companies:
        for r in c.get("rounds", []):
            evidence_id = r.get("evidence_id")
            if not evidence_id:
                continue
            base = {
                "company_id": str(c["company_id"]),
                "company_name": c["name"],
                "company_sectors": c.get("sectors", []),
                "company_country": c.get("country"),
                "round_type": r.get("round_type"),
                "date": parse_date(r.get("date")),
                "amount_usd": r.get("amount_usd"),
                "evidence_id": evidence_id,
            }
            investors = r.get("investors") or [{}]
            for j, inv in enumerate(investors):
                records.append(
                    FundingRecord(
                        id=f"{c['company_id']}:{r['index']}:{j}",
                        investor_id=inv.get("uuid"),
                        investor_name=inv.get("name"),
                        investor_type=inv.get("type"),
                        **base,
                    )
                )
    return records
