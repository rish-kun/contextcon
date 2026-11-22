"""Shared plumbing for the verify steps: clients, case loading, identity guard,
sources and evidence rows, public web queries, and HTML to text.

Conventions:
- `sources.source_class` stores `app.domain.enums.SourceReliability` values; the API
  maps them to the contract's `SourceClass` (see `app.api.cases_sections`).
- `evidence.entity_ref` says which entity a row is attached to: `crustdata:<id>` when
  the Crustdata id itself ties it (profile, identify), or `crustdata:<keys>:<id>` when
  other identifiers did (e.g. `crustdata:domain+hq_city:123` for a news article). Both
  end in `:<id>`, which is what `app.pipelines.evaluate.inputs` matches on. Rows that
  could not be corroborated are kept as `unattached:<reason>` (visible in Sources,
  never fed to a status, criterion or memo line).
- Every write is keyed so a re-run of a step upserts instead of duplicating:
  a source by (case, provider, endpoint/url, class, request), evidence by
  (source, origin_key).
"""

from __future__ import annotations

import html
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import CrustdataClient, LLMClient
from app.db.enums import IdentityStatus
from app.db.models import Case, Evidence, Source
from app.jobs import StepContext

# --- Step keys and handler names (keys equal handler names) -------------------

IDENTITY = "verify.identity"
PROFILE = "verify.profile"
REGISTRY = "verify.registry"
EVENTS = "verify.events"
COMPARABLES = "verify.comparables"

IDENTITY_UNRESOLVED = "identity unresolved"

# --- Clients (swappable in tests) ---------------------------------------------


def _default_crustdata(ctx: StepContext) -> Any:
    return CrustdataClient.from_settings(recorder=ctx.recorder, cache=ctx.cache)


def _default_llm(ctx: StepContext) -> Any:
    return LLMClient.from_settings(recorder=ctx.recorder, cache=ctx.cache)


@dataclass
class ClientFactories:
    """How steps get their clients. Tests replace these with fakes."""

    crustdata: Callable[[StepContext], Any] = _default_crustdata
    llm: Callable[[StepContext], Any] = _default_llm


clients = ClientFactories()


async def close_quietly(client: Any) -> None:
    closer = getattr(client, "aclose", None)
    if closer is not None:
        await closer()


# --- Case and identity guard ----------------------------------------------------


class IdentityNotConfirmed(Exception):
    """An identity-dependent step was asked to run before identity is confirmed."""


async def load_case(ctx: StepContext) -> Case:
    if ctx.run.case_id is None:
        raise LookupError("verify steps need a case run")
    case = await ctx.session.get(Case, ctx.run.case_id, populate_existing=True)
    if case is None or case.workspace_id != ctx.run.workspace_id:
        raise LookupError("case not found in this workspace")
    return case


def require_confirmed(case: Case) -> int:
    """The confirmed Crustdata id, or raise: identity-dependent work is blocked."""
    if case.identity_status != IdentityStatus.CONFIRMED or case.crustdata_company_id is None:
        raise IdentityNotConfirmed(IDENTITY_UNRESOLVED)
    return int(case.crustdata_company_id)


def blocked_output(ctx: StepContext) -> dict[str, Any]:
    ctx.result = "Not run: identity unresolved"
    return {"blocked": IDENTITY_UNRESOLVED}


@dataclass(frozen=True)
class ConfirmedEntity:
    """What the case knows about the confirmed company: the identifiers later
    records must match before they are attached (identity guard, design §5.4)."""

    crustdata_company_id: int
    name: str
    domains: tuple[str, ...] = ()
    profile_url: str | None = None
    hq_city: str | None = None
    country: str | None = None
    founded_year: int | None = None
    cin: str | None = None

    @classmethod
    def of(cls, case: Case) -> ConfirmedEntity:
        cid = require_confirmed(case)
        entity = dict((case.identity_identifiers or {}).get("entity") or {})
        domains = [normalize_domain(d) for d in entity.get("domains") or []]
        return cls(
            crustdata_company_id=cid,
            name=str(entity.get("name") or case.company_name),
            domains=tuple(d for d in dict.fromkeys(domains) if d),
            profile_url=entity.get("profile_url"),
            hq_city=entity.get("hq_city"),
            country=entity.get("country"),
            founded_year=entity.get("founded_year"),
            cin=entity.get("cin"),
        )

    @property
    def domain(self) -> str | None:
        return self.domains[0] if self.domains else None

    @property
    def ref(self) -> str:
        return f"crustdata:{self.crustdata_company_id}"


def update_entity(case: Case, **values: Any) -> None:
    """Merge newly learned identifiers (HQ, founded year, CIN…) into the case."""
    identifiers = dict(case.identity_identifiers or {})
    entity = dict(identifiers.get("entity") or {})
    for key, value in values.items():
        if value not in (None, "", []):
            entity[key] = value
    identifiers["entity"] = entity
    case.identity_identifiers = identifiers


# --- Entity references ----------------------------------------------------------


def attached_ref(entity_ref: str, matched_on: Iterable[str]) -> str:
    keys = [k for k in dict.fromkeys(matched_on) if k != "crustdata_company_id"]
    if not keys:
        return entity_ref
    prefix, _, cid = entity_ref.rpartition(":")
    return f"{prefix}:{'+'.join(keys)}:{cid}"


def unattached_ref(reason: str) -> str:
    return f"unattached:{reason}"[:500]


@dataclass(frozen=True)
class ParsedRef:
    attached: bool
    entity: str | None
    matched_on: list[str] = field(default_factory=list)
    reason: str | None = None


def parse_ref(entity_ref: str) -> ParsedRef:
    if entity_ref.startswith("unattached:"):
        return ParsedRef(False, None, [], entity_ref.removeprefix("unattached:"))
    parts = entity_ref.split(":")
    if len(parts) == 3:
        return ParsedRef(True, f"{parts[0]}:{parts[2]}", parts[1].split("+"))
    basis = ["crustdata_company_id"] if parts[0] == "crustdata" else []
    return ParsedRef(True, entity_ref, basis)


# --- Sources and evidence -------------------------------------------------------


async def get_or_create_source(
    ctx: StepContext,
    case: Case,
    *,
    provider: str,
    endpoint_or_url: str,
    source_class: str,
    request: dict[str, Any] | None = None,
    title: str | None = None,
    publisher: str | None = None,
) -> Source:
    return await ensure_source(
        ctx.session,
        case,
        ctx.run.id,
        provider=provider,
        endpoint_or_url=endpoint_or_url,
        source_class=source_class,
        request=request,
        title=title,
        publisher=publisher,
    )


async def find_source(
    session: AsyncSession,
    case: Case,
    *,
    provider: str,
    endpoint_or_url: str,
    source_class: str,
    request: dict[str, Any],
) -> Source | None:
    stmt = select(Source).where(
        Source.case_id == case.id,
        Source.provider == provider,
        Source.endpoint_or_url == endpoint_or_url,
        Source.source_class == source_class,
        Source.request == request,
    )
    return (await session.execute(stmt)).scalars().first()


async def ensure_source(
    session: AsyncSession,
    case: Case,
    run_id: uuid.UUID | None,
    *,
    provider: str,
    endpoint_or_url: str,
    source_class: str,
    request: dict[str, Any] | None = None,
    title: str | None = None,
    publisher: str | None = None,
) -> Source:
    request = request or {}
    source = await find_source(
        session,
        case,
        provider=provider,
        endpoint_or_url=endpoint_or_url,
        source_class=source_class,
        request=request,
    )
    if source is None:
        source = Source(
            workspace_id=case.workspace_id,
            case_id=case.id,
            run_id=run_id,
            provider=provider,
            endpoint_or_url=endpoint_or_url,
            source_class=source_class,
            request=request,
            title=title,
            publisher=publisher,
        )
        session.add(source)
        await session.flush()
    else:
        source.retrieved_at = datetime.now(UTC)
        source.run_id = run_id or source.run_id
        if title:
            source.title = title
        if publisher:
            source.publisher = publisher
    return source


async def upsert_evidence(
    session: AsyncSession,
    source: Source,
    *,
    case_id: uuid.UUID,
    origin_key: str,
    entity_ref: str,
    value: Any = None,
    field_path: str | None = None,
    span: str | None = None,
    as_of: date | None = None,
    identity_confidence: float | None = None,
) -> uuid.UUID:
    values = {
        "case_id": case_id,
        "entity_ref": entity_ref[:500],
        "field_path": field_path,
        "span": span,
        "value": value,
        "as_of": as_of,
        "identity_confidence": identity_confidence,
    }
    stmt = (
        insert(Evidence)
        .values(id=uuid.uuid4(), source_id=source.id, origin_key=origin_key[:1000], **values)
        .on_conflict_do_update(
            index_elements=[Evidence.source_id, Evidence.origin_key], set_=values
        )
        .returning(Evidence.id)
    )
    return (await session.execute(stmt)).scalar_one()


# --- Values ---------------------------------------------------------------------

_DATE_PREFIX = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


def parse_date(value: Any) -> date | None:
    """`2024-03-01`, `2024-03-01T…`, `2024-03` or Unix seconds → date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 10**11 else value
        try:
            return datetime.fromtimestamp(seconds, UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    m = _DATE_PREFIX.search(str(value))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    except ValueError:
        return None


_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_DMY_TEXT = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+([A-Za-z]{3,9})[,\s\-/]+(\d{4})")
_MDY_TEXT = re.compile(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")
_DMY_NUM = re.compile(r"(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})")


def parse_human_date(value: str) -> date | None:
    """ISO, `12 March 2014`, `March 12, 2014` or `12-03-2014` (day first, as in India)."""
    iso = parse_date(value) if re.match(r"^\s*\d{4}-\d{2}", value) else None
    if iso:
        return iso
    try:
        if m := _DMY_TEXT.search(value):
            month = _MONTHS.get(m.group(2).lower())
            if month:
                return date(int(m.group(3)), month, int(m.group(1)))
        if m := _MDY_TEXT.search(value):
            month = _MONTHS.get(m.group(1).lower())
            if month:
                return date(int(m.group(3)), month, int(m.group(2)))
        if m := _DMY_NUM.search(value):
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def normalize_domain(value: str | None) -> str | None:
    """`https://www.Example.com/about` → `example.com`."""
    if not value:
        return None
    raw = value.strip().lower()
    if "://" not in raw:
        raw = "http://" + raw
    host = urlsplit(raw).hostname or ""
    host = host.removeprefix("www.")
    return host or None


def host_of(url: str | None) -> str | None:
    return normalize_domain(url) if url else None


def host_matches(host: str | None, domain: str) -> bool:
    return bool(host) and (host == domain or host.endswith("." + domain))  # type: ignore[union-attr]


def normalize_name(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower().rstrip("/")
    raw = re.sub(r"^https?://", "", raw)
    return raw.removeprefix("www.") or None


# --- Public lookup terms (confidentiality, design §7) -------------------------

_TERM_OK = re.compile(r"^[\w .,&'()\-/]+$", re.UNICODE)
CIN_PATTERN = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")


@dataclass(frozen=True)
class PublicTerms:
    """The only values a web query may contain: the confirmed company's public name,
    its domain and its CIN. Built from the case's confirmed identity, never from claim
    or document text."""

    name: str
    domain: str | None = None
    cin: str | None = None

    @classmethod
    def of(cls, entity: ConfirmedEntity) -> PublicTerms:
        return cls(name=entity.name, domain=entity.domain, cin=entity.cin)

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 120 or not _TERM_OK.match(self.name):
            raise ValueError("public name term rejected")
        if self.domain is not None and normalize_domain(self.domain) != self.domain:
            raise ValueError("public domain term rejected")
        if self.cin is not None and not CIN_PATTERN.match(self.cin):
            raise ValueError("public CIN term rejected")


def _quoted(term: str) -> str:
    return '"' + term.replace('"', "") + '"'


def registry_query(terms: PublicTerms) -> str:
    """Registry-mirror lookup (builder call 9)."""
    if terms.cin:
        return f"{_quoted(terms.cin)} {_quoted(terms.name)}"
    return f"{_quoted(terms.name)} CIN incorporated"


def news_query(terms: PublicTerms) -> str:
    """News about the confirmed company: name and domain together."""
    if terms.domain:
        return f"{_quoted(terms.name)} {terms.domain}"
    return _quoted(terms.name)


# --- HTML to text (builder call 10) -------------------------------------------

_DROP_TAGS = frozenset({"script", "style", "nav", "footer", "noscript", "svg", "template", "head"})
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}
)
MAX_CHUNK_CHARS = 40_000


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_TAGS:
            self.depth += 1
        elif tag in _BLOCK_TAGS and not self.depth:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self.depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_TAGS and self.depth:
            self.depth -= 1
        elif tag in _BLOCK_TAGS and not self.depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.depth:
            self.parts.append(data)


def html_to_text(content: str | None) -> str:
    """Visible text of a page: script, style, nav and footer dropped, whitespace
    collapsed (one line per block)."""
    if not content:
        return ""
    if "<" not in content:
        return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(content)).strip()
    parser = _TextParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed HTML: keep what was parsed
        pass
    text = "".join(parser.parts)
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def chunks(text: str, size: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split long text on line boundaries. Every chunk is processed; nothing is cut."""
    if len(text) <= size:
        return [text] if text else []
    out: list[str] = []
    current: list[str] = []
    length = 0
    for line in text.split("\n"):
        while len(line) > size:
            if current:
                out.append("\n".join(current))
                current, length = [], 0
            out.append(line[:size])
            line = line[size:]
        if length + len(line) + 1 > size and current:
            out.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        out.append("\n".join(current))
    return out


_META_DATE = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)=[\"'](?:article:published_time|og:published_time|"
    r"datePublished|publish[-_]?date|pubdate|date)[\"'][^>]*content=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_META_DATE_REV = re.compile(
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*(?:property|name|itemprop)=[\"']"
    r"(?:article:published_time|og:published_time|datePublished|publish[-_]?date|pubdate)[\"']",
    re.IGNORECASE,
)
_JSONLD_DATE = re.compile(r"\"datePublished\"\s*:\s*\"([^\"]+)\"")


def published_date(raw_html: str | None) -> tuple[date | None, str | None]:
    """Publish date from the page's own metadata, with the exact markup it came from."""
    if not raw_html:
        return None, None
    for pattern in (_META_DATE, _META_DATE_REV, _JSONLD_DATE):
        m = pattern.search(raw_html)
        if m:
            parsed = parse_date(m.group(1))
            if parsed is not None:
                return parsed, m.group(0)[:300]
    return None, None
