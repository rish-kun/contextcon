"""Crustdata company records → compact, contact-free funding data → `FundingRecord`s.

Ingestion is an allowlist: only the fields below are kept, so personal contact details
(emails, phone numbers, personal profile links) never reach the database, whatever the
provider returns. `CrustdataClient` already allowlists each endpoint and redacts emails;
this is the investor-specific second line, applied before anything is cached and to
every cache hit (the cache is shared, so a hit may have been stored by another caller):

- investors keep only `name`, `uuid` and `type`; rounds keep only the funding fields;
  profile links (`permalink`, `crunchbase_profile_url`) and the `people` group go;
- a retained identity value (an investor name, uuid or type, a round type, a name in
  `investors` / `lead_investors`) that holds a contact value — a URL, an email, a phone
  number — is dropped, not stored as a name.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from app.clients.crustdata import strip_contact_fields
from app.clients.crustdata_models import CompanyRecord
from app.documents.redact import regex_redactor
from app.domain.types import FundingRecord

# Keys dropped from anything cached: personal profile links, and the people group
# (never requested here; dropped if a provider sends it anyway).
_PERSONAL_KEY = re.compile(
    r"profile_url|linkedin|twitter|facebook|instagram|permalink|^people$", re.IGNORECASE
)

# A link in any form: with a scheme, `www.`, or a host followed by a path.
_URL = re.compile(r"(?i)(?:\b[a-z][a-z0-9+.-]*://|\bwww\.|\b[a-z0-9-]+(?:\.[a-z0-9-]+)+/)\S*")
# A run of phone characters holding at least 9 digits ("+919876543210", "98765-43210").
_PHONE_RUN = re.compile(r"\+?\(?\d[\d\s().-]{7,}\d")
_UUID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")


# What the client's sanitizer leaves where it redacted a contact value.
_REDACTED = "[redacted:"


def is_contact_value(value: str) -> bool:
    """True when a string holds a URL, an email address or a phone number (or the
    placeholder left where one was redacted: it is not a name either)."""
    if _REDACTED in value or _URL.search(value):
        return True
    if regex_redactor(value)[1]:
        return True
    return any(sum(ch.isdigit() for ch in m.group()) >= 9 for m in _PHONE_RUN.finditer(value))


def scrub_personal(value: Any) -> Any:
    """Contact fields and personal profile links removed, recursively."""
    value = strip_contact_fields(value)
    if isinstance(value, dict):
        return {k: scrub_personal(v) for k, v in value.items() if not _PERSONAL_KEY.search(k)}
    if isinstance(value, list):
        return [scrub_personal(v) for v in value]
    return value


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value or None


def identity(value: Any) -> str | None:
    """A name or label to retain, or None if empty or it holds a contact value."""
    text = _clean_str(value)
    return None if text is None or is_contact_value(text) else text


def _investor_id(value: Any) -> str | None:
    text = _clean_str(value)
    if text is None or not _UUID.match(text) or not any(ch.isalpha() for ch in text):
        return None  # a provider id has letters; an all-digit "id" may be a phone number
    return text


def names(value: Any) -> list[str]:
    """Investor names from a list, or from a comma-separated string (Crustdata returns
    `lead_investors` both ways). Contact values are dropped."""
    items = value.split(",") if isinstance(value, str) else value or []
    if not isinstance(items, list):
        return []
    return [n for n in (identity(x) for x in items) if n]


# Investor attributes kept. Profile links (`permalink`, `crunchbase_profile_url`) are
# dropped: for an individual investor they are a personal profile link.
INVESTOR_KEYS = ("name", "uuid", "type")


def allow_investor(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    inv = {
        "name": identity(item.get("name")),
        "uuid": _investor_id(item.get("uuid")),
        "type": identity(item.get("type")),
    }
    return inv if inv["name"] or inv["uuid"] else None


def _allow_round(m: Any) -> dict[str, Any] | None:
    if not isinstance(m, dict):
        return None
    out: dict[str, Any] = {
        "round_type": identity(m.get("round_type")),
        "date": _clean_str(m.get("date")),
        "funding_date": _clean_str(m.get("funding_date")),
        "amount_usd": m.get("amount_usd") if isinstance(m.get("amount_usd"), int | float) else None,
        "investors": names(m.get("investors")),
        "lead_investors": names(m.get("lead_investors")),
        "investors_detailed": [
            i for i in (allow_investor(x) for x in m.get("investors_detailed") or []) if i
        ],
    }
    return out


def allow_company(value: Any) -> Any:
    """One company record under the investor allowlist. Company fields other callers
    read stay (minus profile links and contact keys); the funding group is rebuilt
    from the funding allowlist."""
    if not isinstance(value, dict):
        return value
    out = scrub_personal({k: v for k, v in value.items() if k != "funding"})
    funding = value.get("funding")
    if isinstance(funding, dict):
        kept = scrub_personal(
            {
                k: v
                for k, v in funding.items()
                if k not in ("investors", "investors_detailed", "milestones")
            }
        )
        kept["investors"] = names(funding.get("investors"))
        kept["investors_detailed"] = [
            i for i in (allow_investor(x) for x in funding.get("investors_detailed") or []) if i
        ]
        # Positions are kept (None for a malformed entry): evidence keys use the index.
        kept["milestones"] = [_allow_round(m) for m in funding.get("milestones") or []]
        out["funding"] = kept
    return out


def sanitize_body(body: Any) -> Any:
    """A `/company/search` or `/company/enrich` body under the investor allowlist."""
    if isinstance(body, dict) and isinstance(body.get("companies"), list):
        return {**scrub_personal(body), "companies": [allow_company(c) for c in body["companies"]]}
    if isinstance(body, list):
        out = []
        for result in body:
            if not isinstance(result, dict):
                continue
            matches = []
            for match in result.get("matches") or []:
                if isinstance(match, dict):
                    clean = scrub_personal({k: v for k, v in match.items() if k != "company_data"})
                    clean["company_data"] = allow_company(match.get("company_data"))
                    matches.append(clean)
            rest = scrub_personal({k: v for k, v in result.items() if k != "matches"})
            out.append({**rest, "matches": matches})
        return out
    return scrub_personal(body)


def sanitize_cached(value: Any) -> Any:
    """A cached response (``{"body": ..., "http_status": ..., ...}``) made safe."""
    if isinstance(value, dict) and "body" in value:
        return {
            **scrub_personal({k: v for k, v in value.items() if k != "body"}),
            "body": sanitize_body(value["body"]),
        }
    return sanitize_body(value)


class ScrubbingCache:
    """Wraps the step's response cache: what is stored, and every hit read back (the
    cache is shared, so a hit may come from another caller), passes the investor
    allowlist (`CrustdataClient` stores its own endpoint allowlist only)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def get(self, key: str) -> Any | None:
        value = await self.inner.get(key)
        return None if value is None else sanitize_cached(value)

    async def set(self, key: str, value: Any) -> None:
        await self.inner.set(key, sanitize_cached(value))


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
    """The round's detailed investors, then its plain-name mentions.

    A plain mention joins a detailed investor only through the provider's own link: the
    identical name string listed in the same round's `investors_detailed` (Crustdata's
    `investors` is that list's name column). A mention that matches only after
    normalising (case, punctuation, legal suffixes) stays its own investor without an
    id, so the ranking keeps it and flags it as a possible duplicate instead of
    dropping it.
    """
    out: list[dict[str, Any]] = []
    linked: set[str] = set()
    for item in round_.get("investors_detailed") or []:
        inv = allow_investor(item)
        if inv is None:
            continue
        out.append(inv)
        if inv["name"]:
            linked.add(inv["name"])
    for name in names(round_.get("investors")) + names(round_.get("lead_investors")):
        if name not in linked:
            out.append({"name": name, "uuid": None, "type": None})
            linked.add(name)
    return out


def compact_company(raw: CompanyRecord | dict[str, Any]) -> dict[str, Any]:
    """The funding view of one company: identity, sectors and dated rounds."""
    data = allow_company(raw.model_dump() if isinstance(raw, CompanyRecord) else dict(raw))
    # Funding is read from the raw dict below: provider shapes vary (string or list).
    record = CompanyRecord.model_validate({k: v for k, v in data.items() if k != "funding"})
    info = record.basic_info
    funding = data.get("funding") if isinstance(data.get("funding"), dict) else {}
    rounds = []
    for i, m in enumerate(funding.get("milestones") or []):
        if not isinstance(m, dict):
            continue
        date = parse_date(m.get("funding_date")) or parse_date(m.get("date"))
        amount = m.get("amount_usd")
        leads = names(m.get("lead_investors"))
        rounds.append(
            {
                "index": i,
                "round_type": identity(m.get("round_type")),
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
