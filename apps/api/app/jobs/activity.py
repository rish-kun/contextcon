"""The live activity stream: what a run is doing, as typed, persisted events.

Every event is an `ActivityOut` envelope (`app.api.schemas.runs`) with one of six
kinds: `status` (what the step is doing now), `call` (a Crustdata call returned),
`source` (a page or record was read, or could not be), `model` (a model read or draft
finished), `finding` (a piece of the result exists or changed) and `notice` (a limit,
a widening, a resume). See docs/design/iterations/D-live-run-experience.md §2.

`ActivityEmitter` is `ctx.activity` inside a step. It

- allocates `seq` per run under a per-run advisory lock, in its own short transaction,
  so an event is visible at once, survives a handler rollback, and seq order is
  commit order even when several steps of a run emit at once;
- is fenced on the step's claim token (a worker that lost the lease writes nothing);
- keeps at most one `status` per second per step (the latest wins), and stops storing
  anything but `status` past `CAP` events per run;
- never raises: a lost activity line logs a warning and never fails a step.

Confidentiality (§2.10). Labels and details come only from `TEMPLATES` through
`render`, whose typed slots accept a domain, a public name, a count, a claim category,
a status, a document kind in words or (Discover and Investor runs only) the user's own
filter values. `ctx.set_detail(text)` is the one free-text entry point; its call sites
are audited. Snippets are allowed only in `finding` items, from public web pages or
Crustdata records. URLs lose tracking parameters, and are dropped when they carry
credentials or token-like parameters. Case runs never carry search queries or filters.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.activity import CallReport, current_topic
from app.clients.base import safe_error_code
from app.clients.sanitize import redact_text
from app.db.enums import StepState
from app.db.models import CostEntry, RunActivity, Step

log = logging.getLogger(__name__)


class Kind(StrEnum):
    STATUS = "status"
    CALL = "call"
    SOURCE = "source"
    MODEL = "model"
    FINDING = "finding"
    NOTICE = "notice"


class Subject(StrEnum):
    COMPANY = "company"
    CLAIM = "claim"
    INVESTOR = "investor"
    ROUND = "round"
    IDENTITY = "identity"
    EVENT = "event"
    PEER = "peer"
    ASSESSMENT = "assessment"
    REQUEST_LIST = "request_list"


class NoticeCode(StrEnum):
    SEARCH_WIDENED = "search_widened"
    BUDGET_LOW = "budget_low"
    BUDGET_REACHED = "budget_reached"
    STEP_RESUMED = "step_resumed"
    SERVED_FROM_CACHE = "served_from_cache"
    CALL_RETRIED = "call_retried"
    SOURCE_LIMIT = "source_limit"
    IDENTITY_BLOCKED = "identity_blocked"
    NOTHING_TO_CHECK = "nothing_to_check"
    ACTIVITY_LIMIT = "activity_limit"


# Crustdata paths and model calls → the `call.endpoint` names of the contract.
ENDPOINTS = {
    "/company/identify": "company_identify",
    "/company/search": "company_search",
    "/company/enrich": "company_enrich",
    "/person/search": "person_search",
    "/job/search": "job_search",
    "/web/search/live": "web_search",
    "/web/enrich/live": "web_fetch",
    "messages.parse": "messages",
    "messages.create": "messages",
}
ENDPOINT_WORDS = {
    "company_identify": "Company identify",
    "company_search": "Company search",
    "company_enrich": "Company enrich",
    "person_search": "People search",
    "job_search": "Job search",
    "web_search": "Web search",
    "web_fetch": "Page fetch",
    "messages": "Model call",
}

LABEL_MAX = 120
DETAIL_MAX = 200
TITLE_MAX = 140
SNIPPET_MAX = 200
HIGHLIGHT_MAX = 100
HIGHLIGHTS = 2
ITEMS_MAX = 8
CAP = 2000
STATUS_INTERVAL = 1.0


# --- Sanitisers -----------------------------------------------------------------------------

_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_TRACKING = re.compile(
    r"^(utm_.*|mc_.*|_hs.*|fbclid|gclid|dclid|msclkid|igshid|yclid|ref|ref_src)$"
)
_TOKENISH_NAME = re.compile(
    r"token|key|sig|signature|auth|session|secret|passw|credential|jwt|access|code|otp", re.I
)
_TOKENISH_VALUE = re.compile(r"^[A-Za-z0-9_\-.~+/=]{32,}$")


def clean_text(value: Any, limit: int) -> str | None:
    """Collapse whitespace, redact contact details, cap at `limit` characters."""
    if value is None:
        return None
    text = " ".join(redact_text(str(value)).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clean_domain(value: Any) -> str | None:
    """The host of a URL or a bare domain, lower case, without `www.`; None if invalid."""
    if not value:
        return None
    raw = str(value).strip().lower()
    try:
        host = urlsplit(raw if "//" in raw else f"//{raw}").hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.removeprefix("www.")
    return host if _DOMAIN.match(host) else None


def clean_url(value: Any) -> str | None:
    """An http(s) URL without tracking parameters or a fragment. None when it carries
    credentials or a token-like parameter (the domain is still shown)."""
    if not value:
        return None
    try:
        parts = urlsplit(str(value).strip())
        params = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password or clean_domain(parts.hostname) is None:
        return None
    if any(_TOKENISH_NAME.search(k) or _TOKENISH_VALUE.match(v) for k, v in params):
        return None
    kept = [(k, v) for k, v in params if not _TRACKING.match(k.lower())]
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))
    return url if len(url) <= 2000 else None


def clean_title(value: Any) -> str | None:
    return clean_text(value, TITLE_MAX)


def snippet(value: Any) -> str | None:
    """A ≤200-character excerpt of a *public* page or record (finding items only)."""
    return clean_text(value, SNIPPET_MAX)


# --- Labels: templates with typed slots ----------------------------------------------------


class Label(str):
    """A label or detail built by `render` (or `free_status` for `ctx.set_detail`)."""

    __slots__ = ()


def _words(value: str) -> str:
    return value.replace("_", " ")


def _count(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("count slot needs a number")
    return f"{value:g}" if isinstance(value, float) else str(value)


def _enum_words(values: Iterable[str]) -> Callable[[Any], str]:
    allowed = {str(v) for v in values}

    def check(value: Any) -> str:
        if str(value) not in allowed:
            raise ValueError(f"not an allowed value: {value!r}")
        return _words(str(value))

    return check


def _domain_slot(value: Any) -> str:
    return clean_domain(value) or "a web page"


def _name_slot(value: Any) -> str:
    return clean_text(value, 60) or "the company"


def _filters_slot(value: Any) -> str:
    return clean_text(value, 90) or "your criteria"


def _endpoint_slot(value: Any) -> str:
    return ENDPOINT_WORDS[str(value)]


def _error_slot(value: Any) -> str:
    return _words(safe_error_code(value) or "an error")


def _slot_types() -> dict[str, Callable[[Any], str]]:
    from app.domain.enums import ClaimCategory, ClaimStatus, Disposition

    return {
        "n": _count,
        "m": _count,
        "total": _count,
        "domain": _domain_slot,
        "name": _name_slot,
        "category": _enum_words(ClaimCategory),
        "status": _enum_words(ClaimStatus),
        "disposition": _enum_words(Disposition),
        "doc_kind": _enum_words(DOC_KINDS.values()),
        "filters": _filters_slot,
        "endpoint": _endpoint_slot,
        "error": _error_slot,
        "pass_": _enum_words(("primary", "strict", "supplemental", "widened")),
        "groups": _enum_words(_GROUP_PHRASES),
    }


# File kinds → the document kind in words ("the uploaded presentation"), never a filename.
DOC_KINDS = {
    "pdf": "PDF",
    "pptx": "presentation",
    "ppt": "presentation",
    "docx": "document",
    "doc": "document",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "csv": "spreadsheet",
    "txt": "document",
    "image": "image",
}


def doc_kind(file_kind: str | None) -> str:
    return DOC_KINDS.get((file_kind or "").lower(), "document")


# Steps that read an upload (`verify.claims.extract`). Older rows of these steps kept
# the filename in their label, live detail and result; `public_step_text` rewrites
# them to fixed words and counts whenever they are served.
DOCUMENT_STEP_PREFIX = "claims.extract:"
_DOC_KIND_WORDS = frozenset([*DOC_KINDS.values(), "document"])
_READ_COUNT = re.compile(r"^(\d+) claims? read\b")


def document_step_label(kind: str = "document") -> str:
    return f"Read claims from the uploaded {kind}"


def document_step_result(readable: int, kind: str = "document", *, unreadable: bool = False) -> str:
    text = f"{readable} claim{'s' if readable != 1 else ''} read from the uploaded {kind}"
    return text + ("; unreadable text marked not checked" if unreadable else "")


def _kind_of(text: str | None, prefix: str) -> str | None:
    if text and text.startswith(prefix):
        rest = text[len(prefix) :]
        kind = rest.split(";", 1)[0].strip()
        return kind if kind in _DOC_KIND_WORDS else None
    return None


def public_step_text(
    key: str, label: str, detail: str | None, result: str | None
) -> tuple[str, str | None, str | None]:
    """A step's label, detail and result as the API may show them. Document steps get
    fixed words and counts only (never a filename); other steps are unchanged."""
    if not key.startswith(DOCUMENT_STEP_PREFIX):
        return label, detail, result
    label_kind = _kind_of(label, "Read claims from the uploaded ")
    safe_label = document_step_label(label_kind or "document")
    detail_kind = _kind_of(detail, "Reading the uploaded ")
    safe_detail = None if detail is None else f"Reading the uploaded {detail_kind or 'document'}"
    safe_result = None
    if result is not None:
        count = _READ_COUNT.match(result)
        safe_result = (
            document_step_result(
                int(count.group(1)),
                _kind_of(result.split(" read from ", 1)[-1], "the uploaded ") or "document",
                unreadable="unreadable text" in result,
            )
            if count
            else "Claims read from the uploaded document"
        )
    return safe_label, safe_detail, safe_result


TEMPLATES: dict[str, str] = {
    # status
    "status.resolving_filters": "Resolving filter values",
    "status.searching_companies": "Searching companies ({filters})",
    "status.removing_duplicates": "Removing duplicates and must-have failures",
    "status.enriching": "Enriching {n} companies",
    "status.reading_jobs": "Reading job postings for {name}",
    "status.scoring": "Applying your criteria to {n} companies",
    "status.explaining": "Writing why each company is on the list",
    "status.reading_document": "Reading the uploaded {doc_kind}",
    "status.checking": "Checking: {category}",
    "status.reading_domain": "Reading {domain}",
    "status.assessing": "Applying the screening rules",
    "status.drafting_request": "Drafting the document request",
    "status.reading_rounds": "Reading funding rounds of {n} companies",
    "status.ranking_investors": "Grouping investors and ranking by dated comparable rounds",
    "status.waiting_identity": "Waiting for identity",
    "status.searching_news": "Searching news for {name}",
    "status.reading_pages": "Reading {n} pages",
    "status.looking_up_leadership": "Looking up leadership at the confirmed company",
    "status.reading_record": "Reading the company record",
    "status.comparing_facts": "Comparing {n} facts with the claim",
    # call
    "call.company_identify": "Company identify · {n} candidates",
    "call.company_search": "Company search · {n} companies",
    "call.company_enrich": "Enriched {n} of {total} companies",
    "call.person_search": "People search · {n} people",
    "call.job_search": "Job search · {n} postings",
    "call.web_search": "Web search · {n} results",
    "call.web_fetch": "Fetched {n} of {total} pages",
    "call.failed": "{endpoint} did not return",
    "detail.call_failed": "Crustdata returned {error} after {n} tries",
    "detail.filters": "{filters}",
    "detail.groups": "{groups}",
    # source
    "source.read_domain": "Read {domain}",
    "source.failed_domain": "Could not read {domain}",
    "source.read_record": "Read the record of {name}",
    "source.read_company_record": "Read the company record",
    "source.read_document": "Read the uploaded {doc_kind}",
    # model
    "model.read_domain_for": "Read {domain} for {category}",
    "model.read_record_for": "Read the company record for {category}",
    "model.read_document_for": "Read the uploaded document for {category}",
    "model.read_for": "Read evidence for {category}",
    "model.read_document": "Read the uploaded document",
    "model.read_profile": "Read the business profile",
    "model.read_thesis": "Read the thesis",
    "model.read_article": "Read {domain}",
    "model.explanation": "Drafted why a company is on the list",
    "model.drafted_request": "Drafted the document request",
    "model.read": "Model read finished",
    "model.drafted": "Drafted text",
    "model.failed": "Model call did not return",
    # finding
    "finding.found_companies": "Found {n} companies",
    "finding.dropped_companies": "Dropped {n} companies",
    "finding.dropped_detail": "{n} duplicates · {m} failed a must-have",
    "finding.pass": "{pass_} pass",
    "finding.enriched_company": "Enriched {name}",
    "finding.ranked_companies": "Ranked {n} companies",
    "finding.removed_after_enrichment": "Removed {n} companies after enrichment",
    "finding.explained_company": "Explained {name}",
    "finding.explained_companies": "Explained {n} companies",
    "finding.identity_confirmed": "Identity confirmed",
    "finding.identity_ambiguous": "Identity ambiguous: {n} close candidates",
    "finding.identity_unresolved": "Identity not resolved",
    "finding.claims_queued": "Queued {n} claims for checking",
    "finding.claim_checking": "Checking a claim: {category}",
    "finding.fact_found": "Found a fact for {category}",
    "finding.claim_settled": "Claim settled: {status}",
    "finding.claim_not_checked": "Claim not checked",
    "finding.category": "{category}",
    "finding.dated_event": "Found a dated event",
    "finding.dated_events": "Found {n} dated events",
    "finding.peers": "Found {n} comparable companies",
    "finding.rounds_of": "Read {n} funding rounds of {name}",
    "finding.ranked_investors": "Ranked {n} investors",
    "finding.assessment": "Assessment written: {disposition}",
    "finding.request_list": "Drafted a request for {n} documents",
    "finding.nothing_to_request": "Nothing to request from the seller",
}

NOTICES: dict[NoticeCode, tuple[str, str | None]] = {
    NoticeCode.SEARCH_WIDENED: (
        "Widened the search",
        "The strict filters returned {n} companies; preferences were relaxed",
    ),
    NoticeCode.BUDGET_LOW: ("Credit budget running low", "{n} credits left"),
    NoticeCode.BUDGET_REACHED: (
        "Credit budget reached",
        "What was not read is marked not checked",
    ),
    NoticeCode.STEP_RESUMED: (
        "Resumed after an interruption",
        "Calls already paid for replay from the cache",
    ),
    NoticeCode.SERVED_FROM_CACHE: ("Served from the cache", "No new credits were spent"),
    NoticeCode.CALL_RETRIED: ("Retried a call", "{endpoint} needed {n} tries"),
    NoticeCode.SOURCE_LIMIT: ("More results than the read limit", "Read {n} of {total}"),
    NoticeCode.IDENTITY_BLOCKED: (
        "Stopped at identity",
        "The company could not be matched with confidence",
    ),
    NoticeCode.NOTHING_TO_CHECK: ("Nothing to check", "No checkable claims were found"),
    NoticeCode.ACTIVITY_LIMIT: (
        "Activity log is full",
        "Only status lines are recorded from here",
    ),
}

_SLOT = re.compile(r"\{(\w+)\}")
_SLOT_TYPES: dict[str, Callable[[Any], str]] | None = None


def _fill(template: str, slots: dict[str, Any]) -> str:
    global _SLOT_TYPES
    if _SLOT_TYPES is None:
        _SLOT_TYPES = _slot_types()
    needed = set(_SLOT.findall(template))
    missing = needed - set(slots)
    if missing:
        raise KeyError(f"missing slots {sorted(missing)} for {template!r}")
    values = {name: _SLOT_TYPES[name](slots[name]) for name in needed}
    text = _SLOT.sub(lambda m: values[m.group(1)], template)
    return text[:1].upper() + text[1:]


def render(key: str, **slots: Any) -> Label:
    """The label (or detail) for template `key`, its slots checked by type."""
    limit = DETAIL_MAX if key.startswith("detail.") or key.endswith("_detail") else LABEL_MAX
    return Label(clean_text(_fill(TEMPLATES[key], slots), limit) or key)


def free_status(text: Any) -> Label:
    """A `ctx.set_detail` line as a status label: cleaned, present tense, no ellipsis
    and no trailing period. Call sites pass only public words (audited)."""
    cleaned = clean_text(text, LABEL_MAX) or "Working"
    return Label(cleaned.rstrip(" .…").removesuffix("...") or "Working")


# --- Counts and highlights per Crustdata endpoint ------------------------------------------


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _conditions(filters: Any) -> Iterable[dict[str, Any]]:
    node = _dict(filters)
    if "conditions" in node:
        for child in _list(node["conditions"]):
            yield from _conditions(child)
    elif "field" in node:
        yield node


def _records(data: Any) -> list[dict[str, Any]]:
    """Company records in an identify / enrich response ([{matches: [{company_data}]}])."""
    return [
        _dict(_dict(m).get("company_data"))
        for item in _list(data)
        for m in _list(_dict(item).get("matches"))
    ]


def _company_id(record: dict[str, Any]) -> Any:
    return record.get("crustdata_company_id") or _dict(record.get("basic_info")).get(
        "crustdata_company_id"
    )


def _company_name(record: dict[str, Any]) -> str | None:
    return _dict(record.get("basic_info")).get("name") or record.get("name")


_GROUP_PHRASES = (
    "funding",
    "headcount",
    "hiring",
    "web traffic",
    "funding and headcount",
    "funding, headcount and hiring",
    "funding, headcount and web traffic",
)


def counts_for(
    endpoint: str, body: dict[str, Any] | None, data: Any, seen: set[Any] | None = None
) -> dict[str, int]:
    """The contract's fixed `counts` keys for one successful call (§2.4)."""
    body = body or {}
    if endpoint == "company_identify":
        return {"candidates": len(_records(data))}
    if endpoint == "company_search":
        companies = [_dict(c) for c in _list(_dict(data).get("companies"))]
        ids = [_company_id(c) for c in companies]
        new = [i for i in ids if i is not None and (seen is None or i not in seen)]
        if seen is not None:
            seen.update(new)
        counts = {"returned": len(companies), "new": len(set(new))}
        total = _dict(data).get("total_count")
        if isinstance(total, int):
            counts["total_available"] = total
        return counts
    if endpoint == "company_enrich":
        records = _records(data)

        def has(record: dict[str, Any], *path: str) -> bool:
            value: Any = record
            for key in path:
                value = _dict(value).get(key)
            return bool(value)

        return {
            "requested": len(_list(body.get("crustdata_company_ids"))),
            "returned": len(records),
            "with_funding": sum(
                has(r, "funding", "milestones") or has(r, "funding", "total_investment_usd")
                for r in records
            ),
            "funding_rounds": sum(
                len(_list(_dict(r.get("funding")).get("milestones"))) for r in records
            ),
            "with_investors": sum(has(r, "funding", "investors") for r in records),
            "with_headcount_series": sum(has(r, "headcount", "timeseries") for r in records),
            "with_web_traffic": sum(bool(r.get("web_traffic")) for r in records),
        }
    if endpoint == "person_search":
        profiles = [_dict(p) for p in _list(_dict(data).get("profiles"))]
        ids = {
            c.get("value")
            for c in _conditions(body.get("filters"))
            if str(c.get("field", "")).endswith("current.company_id")
        }

        def current_here(profile: dict[str, Any]) -> bool:
            current = _list(
                _dict(_dict(profile.get("experience")).get("employment_details")).get("current")
            )
            return any(_dict(job).get("crustdata_company_id") in ids for job in current)

        return {"returned": len(profiles), "current_leadership": sum(map(current_here, profiles))}
    if endpoint == "job_search":
        listings = [_dict(j) for j in _list(_dict(data).get("job_listings"))]
        companies = {
            _dict(j.get("company")).get("crustdata_company_id")
            or _dict(_dict(j.get("company")).get("basic_info")).get("company_id")
            for j in listings
        } - {None}
        if not companies:
            companies = {
                c.get("value")
                for c in _conditions(body.get("filters"))
                if "company_id" in str(c.get("field"))
            }
        return {"postings": len(listings), "companies": len(companies) if listings else 0}
    if endpoint == "web_search":
        hits = [_dict(h) for h in _list(_dict(data).get("results"))]
        return {"hits": len(hits), "news_hits": sum(h.get("source") == "news" for h in hits)}
    if endpoint == "web_fetch":
        read = len(_read_pages(data))
        requested = len(_list(body.get("urls")))
        return {"requested": requested, "read": read, "failed": max(0, requested - read)}
    return {}


def _read_pages(data: Any) -> list[dict[str, Any]]:
    return [
        _dict(p)
        for p in _list(data)
        if _dict(p).get("url") and _dict(p).get("success") is not False
    ]


def _round_words(record: dict[str, Any]) -> str | None:
    rounds = [_dict(m) for m in _list(_dict(record.get("funding")).get("milestones"))]
    dated = sorted(
        (r for r in rounds if r.get("date") or r.get("funding_date")),
        key=lambda r: str(r.get("date") or r.get("funding_date")),
    )
    if not dated:
        return None
    last = dated[-1]
    when = str(last.get("date") or last.get("funding_date"))[:7]
    kind = _words(str(last.get("round_type") or "funding round")).title()
    return f"{kind} · {when}"


def highlights_for(endpoint: str, data: Any) -> list[str] | None:
    """≤2 short lines from public record fields: company names, rounds, cities."""
    out: list[str] = []
    if endpoint == "company_enrich":
        for record in _records(data):
            name = _company_name(record)
            rnd = _round_words(record)
            if name and rnd:
                out.append(f"{name} · {rnd}")
    elif endpoint == "company_search":
        for company in _list(_dict(data).get("companies")):
            name = _company_name(_dict(company))
            city = _dict(_dict(company).get("locations")).get("headquarters")
            if name:
                out.append(f"{name} · {city}" if city else name)
    lines = [clean_text(h, HIGHLIGHT_MAX) for h in out[:HIGHLIGHTS]]
    return [h for h in lines if h] or None


def _filters_in_words(body: dict[str, Any]) -> str | None:
    values = []
    for cond in _conditions(body.get("filters")):
        value = cond.get("value")
        if isinstance(value, list):
            values.extend(str(v) for v in value[:3])
        elif value is not None and not isinstance(value, dict):
            values.append(str(value))
    return " · ".join(dict.fromkeys(values)) or None


def _iso_date(value: Any) -> str | None:
    text = str(value or "")[:10]
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


# --- Envelope -----------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def envelope(
    kind: Kind,
    label: Label,
    *,
    detail: Label | None = None,
    progress: tuple[int, int] | None = None,
    source: dict[str, Any] | None = None,
    call: dict[str, Any] | None = None,
    counts: dict[str, int] | None = None,
    highlights: list[str] | None = None,
    items: list[dict[str, Any]] | None = None,
    subject: Subject | None = None,
    code: NoticeCode | None = None,
    ref: dict[str, str] | None = None,
) -> dict[str, Any]:
    """An `ActivityOut` without its run fields (seq, run_id, step_id, step_key)."""
    if not isinstance(label, Label) or (detail is not None and not isinstance(detail, Label)):
        raise TypeError("labels and details come from `render` templates")
    return {
        "kind": str(kind),
        "at": _now(),
        "label": str(label),
        "detail": None if detail is None else str(detail),
        "progress": None
        if progress is None
        else {"done": int(progress[0]), "total": int(progress[1])},
        "source": source,
        "call": call,
        "counts": None
        if counts is None
        else {str(k): int(v) for k, v in counts.items() if v is not None},
        "highlights": highlights or None,
        "items": items[:ITEMS_MAX] if items else None,
        "subject": None if subject is None else str(subject),
        "code": None if code is None else str(code),
        "ref": ref,
    }


def source_ref(
    type_: str,
    *,
    domain: Any = None,
    url: Any = None,
    title: Any = None,
    source_class: str | None = None,
    as_of: Any = None,
    state: str = "read",
    reason: str | None = None,
) -> dict[str, Any]:
    """A `SourceRefOut`. A seller document never has a domain, URL or title other than
    its kind in words."""
    if type_ == "seller_document":
        return {
            "type": type_,
            "domain": None,
            "url": None,
            "title": clean_title(title),
            "source_class": "seller_document",
            "as_of": None,
            "state": state,
            "reason": reason,
        }
    web = type_ == "web_page"
    return {
        "type": type_,
        "domain": clean_domain(domain or url) if web else None,
        "url": clean_url(url) if web else None,
        "title": clean_title(title),
        "source_class": source_class,
        "as_of": _iso_date(as_of),
        "state": state,
        "reason": reason,
    }


def case_safe_source(source: dict[str, Any]) -> dict[str, Any]:
    """A source ref on a case run: no query string on the URL (a search URL can echo
    the terms), and no title on a web page (a results page can echo them too)."""
    out = dict(source)
    if out.get("url"):
        try:
            parts = urlsplit(str(out["url"]))
            out["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        except ValueError:
            out["url"] = None
    if out.get("type") == "web_page":
        out["title"] = None
    return out


def case_safe_event(event: dict[str, Any]) -> dict[str, Any]:
    """`case_safe_source` on an event's source and on any source inside its items."""
    out = dict(event)
    if isinstance(out.get("source"), dict):
        out["source"] = case_safe_source(out["source"])
    if isinstance(out.get("items"), list):
        out["items"] = [
            {**item, "source": case_safe_source(item["source"])}
            if isinstance(item, dict) and isinstance(item.get("source"), dict)
            else item
            for item in out["items"]
        ]
    return out


def claim_ref(claim_id: Any) -> dict[str, str]:
    return {"type": "claim", "id": str(claim_id)}


# --- Emitter ------------------------------------------------------------------------------


def _lock_key(run_id: uuid.UUID) -> int:
    digest = hashlib.sha256(f"run_activities:{run_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


class ActivityEmitter:
    """`ctx.activity`: emits a step's events (see the module docstring)."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession] | None,
        *,
        workspace_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        step_id: uuid.UUID | None = None,
        step_key: str | None = None,
        lease_token: uuid.UUID | None = None,
        case_run: bool = False,
    ) -> None:
        self._sessionmaker = sessionmaker
        self.workspace_id = workspace_id
        self.run_id = run_id
        self.step_id = step_id
        self.step_key = step_key
        self.lease_token = lease_token
        self.case_run = case_run
        self.seen_companies: set[Any] = set()
        self._last_status = -STATUS_INTERVAL
        self._pending: dict[str, Any] | None = None
        self._flush: asyncio.Task[None] | None = None
        self._counters: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return self._sessionmaker is not None and self.run_id is not None

    def bump(self, key: str) -> int:
        """A running count kept for this step (e.g. facts found for one claim)."""
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    # -- the six kinds ---------------------------------------------------------------

    async def status(
        self,
        label: Label | str,
        *,
        progress: tuple[int, int] | None = None,
        ref: dict[str, str] | None = None,
    ) -> None:
        """What the step is doing now. At most one per second; the latest wins."""
        if not self.enabled:
            return
        try:
            text = label if isinstance(label, Label) else free_status(label)
            event = envelope(Kind.STATUS, text, progress=progress, ref=ref or self._ref())
        except Exception:  # noqa: BLE001
            log.warning("activity: bad status", exc_info=True)
            return
        wait = self._last_status + STATUS_INTERVAL - time.monotonic()
        if wait <= 0 and self._flush is None:
            self._last_status = time.monotonic()
            await self.write([event])
            return
        self._pending = event
        if self._flush is None:
            self._flush = asyncio.create_task(self._flush_later(max(wait, 0.0)))

    async def _flush_later(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            event, self._pending = self._pending, None
            self._last_status = time.monotonic()
            self._flush = None
            if event is not None:
                event["at"] = _now()
                await self.write([event])
        except asyncio.CancelledError:
            pass

    async def source(
        self,
        label: Label,
        *,
        source: dict[str, Any],
        detail: Label | None = None,
        progress: tuple[int, int] | None = None,
        ref: dict[str, str] | None = None,
    ) -> None:
        await self._emit(
            Kind.SOURCE, label, detail=detail, source=source, progress=progress, ref=ref
        )

    async def finding(
        self,
        label: Label,
        *,
        subject: Subject,
        items: Sequence[dict[str, Any]] | None = None,
        counts: dict[str, int] | None = None,
        detail: Label | None = None,
        source: dict[str, Any] | None = None,
        progress: tuple[int, int] | None = None,
        ref: dict[str, str] | None = None,
    ) -> None:
        await self._emit(
            Kind.FINDING,
            label,
            subject=subject,
            items=list(items) if items else None,
            counts=counts,
            detail=detail,
            source=source,
            progress=progress,
            ref=ref,
        )

    async def findings(
        self,
        label: Callable[[list[dict[str, Any]]], Label],
        *,
        subject: Subject,
        items: Sequence[dict[str, Any]],
        counts: dict[str, int] | None = None,
        detail: Label | None = None,
    ) -> None:
        """`items` in events of ≤8, each labelled by `label(batch)`, in one write."""
        events = []
        try:
            for i in range(0, len(items), ITEMS_MAX):
                batch = list(items[i : i + ITEMS_MAX])
                events.append(
                    envelope(
                        Kind.FINDING,
                        label(batch),
                        subject=subject,
                        items=batch,
                        counts=counts,
                        detail=detail,
                        ref=self._ref(),
                    )
                )
        except Exception:  # noqa: BLE001
            log.warning("activity: bad findings", exc_info=True)
            return
        await self.write(events)

    async def model(
        self,
        label: Label,
        *,
        counts: dict[str, int] | None = None,
        call: dict[str, Any] | None = None,
        ref: dict[str, str] | None = None,
    ) -> None:
        await self._emit(Kind.MODEL, label, counts=counts, call=call, ref=ref)

    async def notice(
        self, code: NoticeCode, *, ref: dict[str, str] | None = None, **slots: Any
    ) -> None:
        if not self.enabled:
            return
        try:
            label, detail = NOTICES[code]
            event = envelope(
                Kind.NOTICE,
                Label(_fill(label, slots)),
                detail=None if detail is None else Label(_fill(detail, slots)[:DETAIL_MAX]),
                code=code,
                ref=ref or self._ref(),
            )
        except Exception:  # noqa: BLE001
            log.warning("activity: bad notice %s", code, exc_info=True)
            return
        await self.write([event])

    async def _emit(self, kind: Kind, label: Label, **fields: Any) -> None:
        if not self.enabled:
            return
        try:
            fields["ref"] = fields.get("ref") or self._ref()
            event = envelope(kind, label, **fields)
        except Exception:  # noqa: BLE001
            log.warning("activity: bad %s event", kind, exc_info=True)
            return
        await self.write([event])

    def _ref(self) -> dict[str, str] | None:
        ref = current_topic().get("ref")
        return dict(ref) if isinstance(ref, dict) else None

    # -- the clients' hook --------------------------------------------------------------

    async def report(self, report: CallReport) -> None:
        """Recorder hook: one returned call → `call` (+ `source`) or `model` events."""
        if not self.enabled:
            return
        try:
            if report.provider == "anthropic":
                events = [self._model_event(report)]
            else:
                events = self._crustdata_events(report)
        except Exception:  # noqa: BLE001
            log.warning("activity: could not describe a %s call", report.provider, exc_info=True)
            return
        await self.write(events)

    def _call_info(self, report: CallReport, endpoint: str) -> dict[str, Any]:
        credits = None
        if report.provider == "crustdata":
            credits = 0.0 if report.from_cache else report.credits
        return {
            "provider": report.provider,
            "endpoint": endpoint,
            "ok": report.ok,
            "error": safe_error_code(report.error) if not report.ok else None,
            "from_cache": report.from_cache,
            "attempts": max(int(report.attempts or 0), 0 if report.from_cache else 1),
            "duration_ms": report.duration_ms,
            "credits": credits,
            "usd": (0.0 if report.from_cache else report.usd)
            if report.provider == "anthropic"
            else None,
            "credits_total": 0.0,
            "usd_total": 0.0,
        }

    def _crustdata_events(self, report: CallReport) -> list[dict[str, Any]]:
        endpoint = ENDPOINTS.get(report.endpoint)
        if endpoint is None:
            return []
        call = self._call_info(report, endpoint)
        ref = self._ref()
        if not report.ok:
            return [
                envelope(
                    Kind.CALL,
                    render("call.failed", endpoint=endpoint),
                    detail=render("detail.call_failed", error=report.error, n=call["attempts"]),
                    call=call,
                    ref=ref,
                )
            ]
        body, data = report.body or {}, report.data
        counts = counts_for(endpoint, body, data, self.seen_companies)
        n = {
            "company_identify": counts.get("candidates", 0),
            "company_search": counts.get("returned", 0),
            "company_enrich": counts.get("returned", 0),
            "person_search": counts.get("returned", 0),
            "job_search": counts.get("postings", 0),
            "web_search": counts.get("hits", 0),
            "web_fetch": counts.get("read", 0),
        }[endpoint]
        total = counts.get("requested", n)
        label = render(f"call.{endpoint}", n=n, total=total)
        detail = None
        if endpoint == "company_search" and not self.case_run:
            words = _filters_in_words(body)
            detail = render("detail.filters", filters=words) if words else None
        elif endpoint == "company_enrich":
            detail = self._groups_detail(counts)
        events = [
            envelope(
                Kind.CALL,
                label,
                detail=detail,
                call=call,
                counts=counts,
                highlights=highlights_for(endpoint, data),
                ref=ref,
            )
        ]
        events.extend(self._sources(endpoint, body, data, ref))
        return events

    @staticmethod
    def _groups_detail(counts: dict[str, int]) -> Label | None:
        parts = [
            name
            for name, key in (
                ("funding", "with_funding"),
                ("headcount", "with_headcount_series"),
                ("web traffic", "with_web_traffic"),
            )
            if counts.get(key)
        ]
        if not parts:
            return None
        phrase = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        if phrase not in _GROUP_PHRASES:
            return None
        return render("detail.groups", groups=phrase)

    def _sources(
        self, endpoint: str, body: dict[str, Any], data: Any, ref: dict[str, str] | None
    ) -> list[dict[str, Any]]:
        topic = current_topic()
        source_class = topic.get("source_class")
        events: list[dict[str, Any]] = []
        if endpoint == "web_fetch":
            pages = _read_pages(data)
            requested = [str(u) for u in _list(body.get("urls"))]
            read_urls = {p.get("url") for p in pages}
            total = len(requested)
            done = 0
            for page in pages:
                done += 1
                url = page.get("url")
                empty = not str(page.get("content") or "").strip()
                events.append(
                    envelope(
                        Kind.SOURCE,
                        render("source.read_domain", domain=url),
                        source=source_ref(
                            "web_page",
                            url=url,
                            title=page.get("title"),
                            source_class=source_class,
                            state="read",
                            reason="empty" if empty else None,
                        ),
                        progress=(done, total) if total > 1 else None,
                        ref=ref,
                    )
                )
            for url in requested:
                if url in read_urls:
                    continue
                done += 1
                events.append(
                    envelope(
                        Kind.SOURCE,
                        render("source.failed_domain", domain=url),
                        source=source_ref(
                            "web_page", url=url, source_class=source_class, state="failed"
                        ),
                        progress=(done, total) if total > 1 else None,
                        ref=ref,
                    )
                )
        elif endpoint == "company_enrich":
            for record in _records(data):
                name = _company_name(record)
                label = (
                    render("source.read_record", name=name)
                    if name and not self.case_run
                    else render("source.read_company_record")
                )
                events.append(
                    envelope(
                        Kind.SOURCE,
                        label,
                        source=source_ref(
                            "crustdata_record",
                            title=f"{name} · company record" if name else "Company record",
                            source_class=source_class or "data_provider",
                            as_of=record.get("updated_at"),
                        ),
                        ref=ref,
                    )
                )
        return events

    def _model_event(self, report: CallReport) -> dict[str, Any]:
        call = self._call_info(report, "messages")
        topic = current_topic()
        if not report.ok:
            label = render("model.failed")
        else:
            label = _model_label(report.endpoint, topic)
        return envelope(Kind.MODEL, label, call=call, ref=self._ref())

    # -- storage ------------------------------------------------------------------------------

    async def write(self, events: Sequence[dict[str, Any]]) -> list[int]:
        """Append envelopes; returns their seqs ([] if fenced off, capped or failed)."""
        if not events or not self.enabled:
            return []
        assert self._sessionmaker is not None and self.run_id is not None
        if self.case_run:
            events = [case_safe_event(e) for e in events]
        try:
            async with self._sessionmaker() as session:
                return await self._insert(session, list(events))
        except Exception:  # noqa: BLE001 - an activity line must never fail the step
            log.warning("activity: write for run %s failed", self.run_id, exc_info=True)
            return []

    async def _insert(self, session: AsyncSession, events: list[dict[str, Any]]) -> list[int]:
        await session.execute(select(func.pg_advisory_xact_lock(_lock_key(self.run_id))))  # type: ignore[arg-type]
        if self.lease_token is not None and self.step_id is not None:
            live = await session.scalar(
                select(Step.id).where(
                    Step.id == self.step_id,
                    Step.lease_token == self.lease_token,
                    Step.state == StepState.RUNNING,
                    Step.lease_until > func.clock_timestamp(),
                )
            )
            if live is None:
                await session.rollback()
                return []
        last = int(
            await session.scalar(
                select(func.coalesce(func.max(RunActivity.seq), 0)).where(
                    RunActivity.run_id == self.run_id
                )
            )
            or 0
        )
        if last + len(events) > CAP:
            kept = [e for e in events if e["kind"] == Kind.STATUS]
            if last < CAP:
                label, detail = NOTICES[NoticeCode.ACTIVITY_LIMIT]
                kept.append(
                    envelope(
                        Kind.NOTICE,
                        Label(label),
                        detail=Label(detail or ""),
                        code=NoticeCode.ACTIVITY_LIMIT,
                    )
                )
            events = kept
            if not events:
                await session.rollback()
                return []
        if any(e.get("call") for e in events):
            credits, usd = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(CostEntry.credits), 0),
                        func.coalesce(func.sum(CostEntry.usd), 0),
                    ).where(CostEntry.run_id == self.run_id)
                )
            ).one()
            for e in events:
                if e.get("call"):
                    e["call"]["credits_total"] = float(credits or 0)
                    e["call"]["usd_total"] = float(usd or 0)
        seqs = []
        for i, event in enumerate(events, start=1):
            seq = last + i
            payload = {
                "seq": seq,
                "run_id": str(self.run_id),
                "step_id": str(self.step_id) if self.step_id else None,
                "step_key": self.step_key,
                **event,
            }
            session.add(
                RunActivity(
                    workspace_id=self.workspace_id,
                    run_id=self.run_id,
                    step_id=self.step_id,
                    seq=seq,
                    kind=event["kind"],
                    at=datetime.fromisoformat(event["at"].replace("Z", "+00:00")),
                    payload=payload,
                )
            )
            seqs.append(seq)
        await session.commit()
        return seqs

    async def close(self) -> None:
        """End of the step: drop a status still waiting for its slot."""
        if self._flush is not None:
            self._flush.cancel()
            self._flush = None
        self._pending = None


def _model_label(endpoint: str, topic: dict[str, Any]) -> Label:
    purpose = topic.get("purpose")
    category = topic.get("category")
    reading = topic.get("reading")
    if purpose == "claims":
        return render("model.read_document")
    if purpose == "criteria":
        return render("model.read_profile")
    if purpose == "thesis":
        return render("model.read_thesis")
    if purpose == "request":
        return render("model.drafted_request")
    if purpose == "explain":
        return render("model.explanation")
    if category:
        try:
            if reading == "web_page" and topic.get("domain"):
                return render("model.read_domain_for", domain=topic["domain"], category=category)
            if reading == "record":
                return render("model.read_record_for", category=category)
            if reading == "document":
                return render("model.read_document_for", category=category)
            return render("model.read_for", category=category)
        except (ValueError, KeyError):
            pass
    if reading == "web_page" and topic.get("domain"):
        return render("model.read_article", domain=topic["domain"])
    return render("model.drafted" if endpoint == "messages.create" else "model.read")


class NullEmitter(ActivityEmitter):
    """`ctx.activity` outside a worker (tests building a StepContext by hand)."""

    def __init__(self) -> None:
        super().__init__(None)


_current: ContextVar[ActivityEmitter | None] = ContextVar("activity_emitter", default=None)


def set_current_emitter(emitter: ActivityEmitter) -> Any:
    """Make `emitter` the one `current_emitter()` returns in this context (the worker
    sets it for each handler task, so code deep inside a step can emit)."""
    return _current.set(emitter)


def reset_current_emitter(token: Any) -> None:
    _current.reset(token)


def current_emitter() -> ActivityEmitter:
    """The running step's emitter, or a no-op one outside a step."""
    return _current.get() or NullEmitter()
