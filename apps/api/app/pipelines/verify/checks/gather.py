"""Evidence gathering per claim category (CP-21), under the identity guard and budget.

| Category                         | Sources                                                    |
|----------------------------------|------------------------------------------------------------|
| team_size                        | enrich headcount (a profile signal, never a payroll count) |
| leadership_history               | person search at the confirmed company id; career records  |
| funding                          | enrich funding rounds + dated news (web search)            |
| dated_event                      | stored news/articles + targeted web search + page fetch    |
| identity_incorporation, location | stored registry evidence + enriched HQ / founded year      |
| debt_security, litigation        | stored registry evidence only (no dedicated v1 check)      |
| financials                       | one public results search (confirmed name + fixed words)  |
| customer_partnership, compliance,| up to two targeted public lookups, from the category's     |
| intellectual_property            | source module `checks/sources/<kind>.py` (SOURCE_MODULES) |

Every record is attached to the confirmed company or person by an identifier, never
by name alone: people by company id (and name, when the claim names them), web pages
by the company's domain, or by its name together with a second identifier (HQ city,
a founder's name, an investor). Pages that only share the name are kept as unattached
sources and never become evidence.

Web queries come from `query.build_query` with public terms only: the enriched (or
identity-confirmed) company name and domain, the enriched HQ city, one allowlisted
topic word. Claim text, and the name or website typed for the case, are never sent
to a search provider. Targeted lookups (`query.build_lookup`) may add one named
public entity taken from the claim's structured components (the partner, certifier
or mark), checked by `query.clean_entity`, and a `site:` host.

Every lookup is recorded on `Gathered.searched` (what was searched, the query, what
came back), so a result that is not Supported can say "searched: X, Y".
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.crustdata import DEFAULT_ENRICH_FIELDS
from app.clients.crustdata_models import CompanyRecord, FundingRound, PersonProfile, WebSearchHit
from app.db.models import Case
from app.db.models import Evidence as EvidenceRow
from app.db.models import Source as SourceRow
from app.domain.enums import ClaimCategory, IdentityStatus, SourceReliability
from app.domain.types import Claim, ExtractedFact
from app.extraction.llm import StructuredLlm
from app.pipelines.discover.countries import country_name
from app.pipelines.verify.checks import activity as check_activity
from app.pipelines.verify.checks.facts import (
    TextUnit,
    fact_from_field,
    facts_from_text,
)
from app.pipelines.verify.checks.html import html_to_text, relevant_passages
from app.pipelines.verify.checks.query import PublicTerms, UnsafeQuery, build_lookup, build_query
from app.pipelines.verify.checks.sources import (
    NEWS_CLASSES,
    REGISTRY_CLASSES,
    EvidenceStore,
    SourceSpec,
    host_of,
    same_site,
    syndication_origin,
)
from app.rules import policy
from app.rules.compare import contains_phrase, normalize_text, to_date, to_month, to_year

R = SourceReliability

# The same request as CP-19's profile step (`verify.profile`), so it is a cache hit.
PROFILE_FIELDS = DEFAULT_ENRICH_FIELDS
ENRICH_CREDITS = 2.0
PEOPLE_LIMIT = 15
PEOPLE_CREDITS = 0.25 * PEOPLE_LIMIT  # 0.03 + 0.1 per side for `experience`, per result
WEB_SEARCH_CREDITS = 1.0
WEB_FETCH_CREDITS = 1.0  # per page
MAX_HITS = 3
MAX_FETCH = 2
MAX_STORED = 4
MAX_PEOPLE = 3
WRITER = "verify.checks"

IDENTITY_DEPENDENT = frozenset(
    {
        ClaimCategory.IDENTITY_INCORPORATION,
        ClaimCategory.LOCATION,
        ClaimCategory.TEAM_SIZE,
        ClaimCategory.LEADERSHIP_HISTORY,
        ClaimCategory.FUNDING,
        ClaimCategory.DATED_EVENT,
    }
)

Budget = Callable[[float], Awaitable[None]]


def company_ref(company_id: int | str) -> str:
    """Stored reference for a record tied to the company by its Crustdata id."""
    return f"crustdata:company:{company_id}"


def person_ref(person_id: int | str) -> str:
    """Stored and rule-side reference for a person found by Crustdata id."""
    return f"crustdata:person:{person_id}"


def attached_to_company(entity_ref: str | None, company_id: int | None) -> bool:
    if not entity_ref or company_id is None:
        return False
    cid = str(company_id)
    return entity_ref == cid or entity_ref.rsplit(":", 1)[-1] == cid


@dataclass
class Gathered:
    facts: list[ExtractedFact] = field(default_factory=list)
    sources_read: list[SourceRow] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    llm_calls: int = 0
    rejected: int = 0
    notes: list[str] = field(default_factory=list)
    read_ref: str | None = None  # entity reference for "read, said nothing" markers
    # One entry per public lookup: {"label", "query", "results": [{"url", "title",
    # "source_class", "attached"}], "skipped": reason | None}. Public terms only.
    searched: list[dict[str, Any]] = field(default_factory=list)

    def read(self, source: SourceRow, ref: str | None = None) -> None:
        self.read_ref = self.read_ref or ref
        if all(s.id != source.id for s in self.sources_read):
            self.sources_read.append(source)


@dataclass
class CheckEnv:
    """What one claim check works with. Paid calls go through `budget` first."""

    session: AsyncSession
    case: Case
    crustdata: Any
    llm: StructuredLlm
    budget: Budget
    store: EvidenceStore
    log: Callable[[str], None] = lambda _m: None
    _profile: CompanyRecord | None = None
    _profile_loaded: bool = False
    _people: list[PersonProfile] | None = None
    _searches: dict[str, list[WebSearchHit]] = field(default_factory=dict)

    @property
    def company_id(self) -> int | None:
        cid = self.case.crustdata_company_id
        try:
            return int(cid) if cid is not None else None
        except ValueError:
            return None

    @property
    def company(self) -> str:
        """Stored entity reference for records tied by the Crustdata company id."""
        return company_ref(self.company_id or self.case.id)

    @property
    def company_entity(self) -> str:
        """The rules' id for the confirmed company (claims attach facts to it)."""
        return str(self.company_id or self.case.id)

    def terms(self) -> PublicTerms:
        """Public lookup terms from independently sourced identity fields only: the
        enriched record's name and domain, else the record identity was confirmed on.
        Never the name or website typed for the case, never claim text. Empty before
        identity is confirmed (no search is then possible)."""
        if self.case.identity_status != IdentityStatus.CONFIRMED:
            return PublicTerms(company_name="")
        info = self._profile.basic_info if self._profile and self._profile.basic_info else None
        entity = (self.case.identity_identifiers or {}).get("entity") or {}
        domains = [d for d in entity.get("domains") or [] if isinstance(d, str) and d]
        name = (info.name if info and info.name else None) or entity.get("name") or ""
        domain = (info.primary_domain if info else None) or (
            host_of(domains[0]) or domains[0] if domains else None
        )
        return PublicTerms(company_name=str(name), domain=domain)

    def hq_city(self) -> str | None:
        """The HQ city from the enriched record (call after `profile()`)."""
        return _hq_city(self._profile)

    def public_name(self) -> str:
        """The confirmed public entity name for activity lines; "the company" before."""
        if self.case.identity_status != IdentityStatus.CONFIRMED:
            return "the company"
        return self.terms().company_name or "the company"

    def _request(self, **extra: Any) -> dict[str, Any]:
        return {"written_by": WRITER, **extra}

    # --- Provider calls (memoised per check; cached across checks by the client) ---

    async def profile(self) -> CompanyRecord | None:
        if self._profile_loaded:
            return self._profile
        assert self.company_id is not None
        await self.budget(ENRICH_CREDITS)
        await check_activity.status("status.reading_record")
        results, _ = await self.crustdata.enrich_company(self.company_id, fields=PROFILE_FIELDS)
        record = None
        for result in results or []:
            for match in result.matches:
                data = match.company_data
                if data.crustdata_company_id in (None, self.company_id):
                    record = data
                    break
            if record is not None:
                break
        self._profile, self._profile_loaded = record, True
        return record

    async def leadership(self) -> list[PersonProfile]:
        if self._people is not None:
            return self._people
        assert self.company_id is not None
        await self.budget(PEOPLE_CREDITS)
        await check_activity.status("status.looking_up_leadership")
        result, _ = await self.crustdata.search_company_leadership(
            self.company_id, limit=PEOPLE_LIMIT
        )
        self._people = list(result.profiles)
        return self._people

    async def search(self, topic: str, *, hq_city: bool = False) -> list[WebSearchHit]:
        """A web search on public terms and one allowlisted topic word. The only place
        may be the enriched HQ city: a city named in a claim is the seller's words."""
        if self.case.identity_status != IdentityStatus.CONFIRMED or self.company_id is None:
            self.log("web search skipped: identity not confirmed")
            return []
        await self.profile()  # the public name, domain and HQ come from the record
        try:
            query = build_query(self.terms(), topic, city=self.hq_city() if hq_city else None)
        except UnsafeQuery as exc:
            self.log(f"web search skipped: {exc}")
            return []
        if query not in self._searches:
            await self.budget(WEB_SEARCH_CREDITS)
            await check_activity.status("status.searching_news", name=self.public_name())
            result, _ = await self.crustdata.web_search(query, sources=["news", "web"])
            self._searches[query] = [h for h in result.results if h.url]
        return self._searches[query]

    def deny_terms(self) -> tuple[str, ...]:
        """Words a lookup must never carry: the name and website typed for the case
        (possibly a deal code name), unless they are the confirmed public name."""
        terms = self.terms()
        if self.case.website and same_site(self.case.website, terms.domain):
            return ()  # the analyst typed the real website: the typed name is not a code name
        public = terms.company_name.casefold()
        typed = [self.case.company_name or "", host_of(self.case.website) or ""]
        return tuple(t for t in typed if t and t.casefold() != public)

    async def lookup_search(self, query: str, what: str) -> list[WebSearchHit]:
        """One paid web search for a targeted lookup (memoised per check)."""
        if query not in self._searches:
            await self.budget(WEB_SEARCH_CREDITS)
            await check_activity.status(
                "status.searching_public", what=what, name=self.public_name()
            )
            result, _ = await self.crustdata.web_search(query, sources=["web", "news"])
            self._searches[query] = [h for h in result.results if h.url]
        return self._searches[query]

    async def fetch(self, urls: list[str]) -> dict[str, str]:
        if not urls:
            return {}
        await self.budget(WEB_FETCH_CREDITS * len(urls))
        if len(urls) == 1:
            await check_activity.status("status.reading_domain", domain=urls[0])
        else:
            await check_activity.status("status.reading_pages", n=len(urls))
        pages, _ = await self.crustdata.fetch_pages(urls)
        return {p.url: p.content or "" for p in pages if p.success and p.url}

    # --- Source rows ---------------------------------------------------------------

    async def profile_source(self, reliability: SourceReliability, label: str) -> SourceRow:
        return await self.store.source(
            SourceSpec(
                provider="crustdata",
                endpoint_or_url="/company/enrich",
                reliability=reliability,
                label=label,
                request=self._request(
                    crustdata_company_ids=[self.company_id],
                    fields=list(PROFILE_FIELDS),
                    matched_on=["crustdata_company_id"],
                ),
            )
        )


# --- Helpers ---------------------------------------------------------------------


def _as_of(value: Any) -> date | None:
    if value is None:
        return None
    d = to_date(value)
    if d is not None:
        return d
    month = to_month(value)
    return date(month[0], month[1], 1) if month else None


def _components(claim: Claim) -> dict[str, Any]:
    return {c.name: c for c in claim.components}


def _hq_city(record: CompanyRecord | None) -> str | None:
    hq = record.locations.headquarters if record and record.locations else None
    return hq.split(",")[0].strip() if hq else None


def hit_date(hit: WebSearchHit) -> date | None:
    extra = hit.model_extra or {}
    meta = hit.metadata if isinstance(hit.metadata, dict) else {}
    for key in ("date", "published_date", "publish_date", "published_at", "article_publish_date"):
        value = extra.get(key) or meta.get(key)
        if isinstance(value, str | int | float):
            parsed = _as_of(str(value))
            if parsed:
                return parsed
    return None


@dataclass(frozen=True)
class Attachment:
    attached: bool
    reliability: SourceReliability
    matched_on: list[str]
    reason: str | None = None
    ref_prefix: str | None = None  # `domain` or `hq_city`: `crustdata:<key>:<id>`


EXCHANGE_HOSTS = ("nseindia.com", "bseindia.com")


def is_exchange(url: str | None) -> bool:
    host = (host_of(url) or "").casefold()
    return any(host == h or host.endswith("." + h) for h in EXCHANGE_HOSTS)


def attach_hit(
    hit: WebSearchHit, terms: PublicTerms, corroborators: dict[str, list[str]]
) -> Attachment:
    """Attach a web record to the company only with an identifier beyond its name."""
    if same_site(hit.url, terms.domain):
        return Attachment(True, R.COMPANY_ANNOUNCEMENT, ["domain"], ref_prefix="domain")
    text = f"{hit.title or ''}\n{hit.snippet or ''}\n{hit.content or ''}"
    if is_exchange(hit.url) and contains_phrase(text, terms.company_name):
        # An exchange filing copy (unaudited results are not audited statements).
        return Attachment(True, R.REGISTRY_MIRROR, ["name", "exchange"], ref_prefix="domain")
    if terms.domain and terms.domain.casefold() in text.casefold():
        return Attachment(True, R.NEWS, ["domain"], ref_prefix="domain")
    if contains_phrase(text, terms.company_name):
        # The second identifier must appear outside the name ("Pune" in "Pune
        # Warehousing" is not an HQ city).
        rest = f" {normalize_text(text)} ".replace(f" {normalize_text(terms.company_name)} ", " ")
        for kind, values in corroborators.items():
            if any(v and contains_phrase(rest, v) for v in values):
                return Attachment(True, R.NEWS, ["name", kind], ref_prefix=kind)
        return Attachment(
            False,
            R.NEWS,
            [],
            "names the company but shows no second identifier (domain or HQ city)",
        )
    return Attachment(False, R.NEWS, [], "does not name the company")


async def _hit_units(
    env: CheckEnv, hits: list[WebSearchHit], query_topic: str, *, fetch: bool
) -> list[TextUnit]:
    record = await env.profile()
    terms = env.terms()
    # Only identifiers the policy accepts (`policy.CORROBORATING_IDENTIFIERS`).
    corroborators = {"hq_city": [c for c in [_hq_city(record)] if c]}
    attached: list[tuple[WebSearchHit, Attachment, SourceRow]] = []
    for hit in hits:
        att = attach_hit(hit, terms, corroborators)
        source = await env.store.source(
            SourceSpec(
                provider="web",
                endpoint_or_url=hit.url or "",
                reliability=att.reliability,
                label=hit.title or host_of(hit.url) or "web page",
                publisher=host_of(hit.url),
                request=env._request(
                    topic=query_topic, matched_on=att.matched_on, entity_name=terms.company_name
                ),
                origin_key=syndication_origin(hit.title, hit.url),
                attached=att.attached,
                unattached_reason=att.reason,
            )
        )
        if att.attached:
            attached.append((hit, att, source))
        else:
            env.log(f"unattached web record {host_of(hit.url)}: {att.reason}")
    attached = attached[:MAX_HITS]
    pages: dict[str, str] = {}
    if fetch and attached:
        pages = await env.fetch([h.url for h, _, _ in attached[:MAX_FETCH] if h.url])
    units: list[TextUnit] = []
    for hit, att, source in attached:
        html = pages.get(hit.url or "")
        text = ""
        if html:
            text = relevant_passages(
                html_to_text(html), [terms.company_name, terms.domain or "", query_topic]
            )
        if not text.strip():
            text = "\n".join(t for t in (hit.title, hit.snippet) if t)
        if text.strip():
            units.append(
                TextUnit(
                    source=source,
                    text=text,
                    entity_ref=f"crustdata:{att.ref_prefix}:{env.company_id}",
                    as_of=hit_date(hit),
                    label=f"web page ({host_of(hit.url)})",
                )
            )
    return units


async def stored_units(env: CheckEnv, classes: frozenset[str]) -> list[TextUnit]:
    """Evidence other steps stored for this case (registry pages, news), attached to
    the confirmed company. Rows written by claim checks themselves are skipped."""
    rows = await env.session.execute(
        select(EvidenceRow, SourceRow)
        .join(SourceRow, SourceRow.id == EvidenceRow.source_id)
        .where(
            EvidenceRow.case_id == env.case.id,
            SourceRow.source_class.in_(classes),
            EvidenceRow.scrubbed_at.is_(None),
        )
        .order_by(EvidenceRow.as_of.desc().nulls_last(), EvidenceRow.created_at)
    )
    units: list[TextUnit] = []
    seen: set[str] = set()
    for ev, src in rows.all():
        if (src.request or {}).get("written_by") == WRITER:
            continue
        if not attached_to_company(ev.entity_ref, env.company_id):
            continue
        text = ev.span
        if not text and ev.field_path and isinstance(ev.value, str | int | float):
            text = f"{ev.field_path.replace('_', ' ')}: {ev.value}"
        if not text or text in seen:
            continue
        seen.add(text)
        units.append(
            TextUnit(
                source=src,
                text=text,
                entity_ref=ev.entity_ref,  # keeps how the other step attached it
                as_of=ev.as_of,
                label=src.title or src.source_class,
            )
        )
        if len(units) >= MAX_STORED:
            break
    return units


async def _read_units(env: CheckEnv, claim: Claim, units: list[TextUnit], out: Gathered) -> None:
    out.read_ref = out.read_ref or env.company
    for unit in units:
        out.read(unit.source, env.company)
        batch = await facts_from_text(env.store, env.llm, claim, unit)
        out.facts.extend(batch.facts)
        out.llm_calls += batch.llm_calls
        out.rejected += batch.rejected


# --- Categories ----------------------------------------------------------------


async def gather_team_size(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    comps = _components(claim)
    record = await env.profile()
    source = await env.profile_source(
        R.PROFESSIONAL_PROFILE_SIGNAL, "Profile-based headcount estimate"
    )
    out.read(source, env.company)
    headcount = record.headcount if record else None
    if headcount is None:
        return out
    series = [p for p in headcount.timeseries or [] if p.date and p.employee_count is not None]
    latest = max(series, key=lambda p: p.date or "") if series else None
    as_of = _as_of(latest.date) if latest else _as_of(record.updated_at if record else None)
    if "employee_count" in comps and headcount.total is not None:
        out.facts.append(
            await fact_from_field(
                env.store,
                source,
                entity_ref=env.company,
                component="employee_count",
                value=headcount.total,
                field_path="headcount.total",
                as_of=as_of,
            )
        )
    growth = (headcount.growth_percent or {}).get("yoy")
    if "headcount_growth_pct" in comps and growth is not None:
        out.facts.append(
            await fact_from_field(
                env.store,
                source,
                entity_ref=env.company,
                component="headcount_growth_pct",
                value=round(float(growth), 2),
                field_path="headcount.growth_percent.yoy",
                as_of=as_of,
            )
        )
    return out


_ROLE_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("founder", ("founder",)),
    ("ceo", ("ceo", "chief executive")),
    ("chief executive", ("ceo", "chief executive")),
    ("cto", ("cto", "chief technology")),
    ("chief technology", ("cto", "chief technology")),
    ("cfo", ("cfo", "chief financial")),
    ("chief financial", ("cfo", "chief financial")),
    ("coo", ("coo", "chief operating")),
    ("chief operating", ("coo", "chief operating")),
    ("managing director", ("managing director",)),
]


def _names_match(claimed: str, actual: str | None) -> bool:
    a, b = set(normalize_text(claimed).split()), set(normalize_text(actual or "").split())
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return small <= big and (len(small) >= 2 or a == b)


def _positions(profile: PersonProfile) -> list[Any]:
    details = profile.experience.employment_details if profile.experience else None
    return [*(details.current if details else []), *(details.past if details else [])]


def at_company(profile: PersonProfile, company_id: int) -> list[Any]:
    return [p for p in _positions(profile) if p.crustdata_company_id == company_id]


def select_people(
    claim: Claim, people: list[PersonProfile], company_id: int
) -> list[PersonProfile]:
    """People at the confirmed company id; by name when the claim names someone,
    else by the role the claim names (founder, CEO, ...). Never by name alone."""
    comps = _components(claim)
    here = [p for p in people if p.crustdata_person_id is not None and at_company(p, company_id)]
    if "person_name" in comps:
        name = str(comps["person_name"].value)
        return [
            p for p in here if _names_match(name, p.basic_profile.name if p.basic_profile else None)
        ]
    text = normalize_text(claim.text)
    for word, title_words in _ROLE_WORDS:
        if f" {normalize_text(word)} " in f" {text} ":
            return [
                p
                for p in here
                if any(
                    any(contains_phrase(pos.title or "", t) for t in title_words)
                    for pos in at_company(p, company_id)
                )
            ][:MAX_PEOPLE]
    return []


def _years(pos: Any) -> str:
    start = to_year(pos.start_date) if pos.start_date else None
    end = to_year(pos.end_date) if pos.end_date else None
    if start is None and end is None:
        return ""
    return f" ({start or '?'} - {end or 'present'})"


def career_lines(profile: PersonProfile, company_id: int) -> list[tuple[str, bool]]:
    name = profile.basic_profile.name if profile.basic_profile else None
    lines: list[tuple[str, bool]] = [(f"Name: {name}", False)] if name else []
    for pos in _positions(profile):
        title = pos.title or "Role not stated"
        employer = pos.name or "employer not stated"
        lines.append(
            (f"{title} at {employer}{_years(pos)}", pos.crustdata_company_id == company_id)
        )
    return lines


async def gather_leadership(env: CheckEnv, claim: Claim) -> Gathered:
    assert env.company_id is not None
    out = Gathered()
    people = await env.leadership()
    search_source = await env.store.source(
        SourceSpec(
            provider="crustdata",
            endpoint_or_url="/person/search",
            reliability=R.PROFESSIONAL_PROFILE_SIGNAL,
            label="Leadership search (professional profiles)",
            request=env._request(
                company_id=env.company_id, limit=PEOPLE_LIMIT, matched_on=["crustdata_company_id"]
            ),
        )
    )
    matched = select_people(claim, people, env.company_id)
    if not matched:
        out.read(search_source, env.company)
        out.entity_ids = [env.company_entity]
        out.notes.append("no leader at the confirmed company matches the claim")
        return out
    units: list[TextUnit] = []
    for profile in matched[:MAX_PEOPLE]:
        pid = profile.crustdata_person_id
        name = profile.basic_profile.name if profile.basic_profile else None
        lines = career_lines(profile, env.company_id)
        source = await env.store.source(
            SourceSpec(
                provider="crustdata",
                endpoint_or_url="/person/search",
                reliability=R.PROFESSIONAL_PROFILE_SIGNAL,
                label=f"Professional record: {name or pid}",
                request=env._request(
                    crustdata_person_id=pid,
                    entity_name=name,
                    matched_on=["crustdata_company_id"]
                    + (["person_name"] if "person_name" in _components(claim) else ["title"]),
                ),
                origin_key=f"person:{pid}",
            )
        )
        units.append(
            TextUnit(
                source=source,
                text="\n".join(line for line, _ in lines),
                entity_ref=person_ref(pid),  # type: ignore[arg-type]
                label="professional record",
                career_lines=lines,
            )
        )
    out.entity_ids = [u.entity_ref for u in units]
    await _read_units(env, claim, units, out)
    return out


def _round_date(m: FundingRound) -> str | None:
    return m.funding_date or m.date


def select_milestone(
    claim: Claim, milestones: list[FundingRound]
) -> tuple[int, FundingRound] | None:
    """The one round the claim is about, or None (the record is then silent on it)."""
    comps = _components(claim)
    dated = [(i, m) for i, m in enumerate(milestones) if _round_date(m)]
    if not dated:
        return None
    year = None
    if "round_date" in comps:
        month = to_month(comps["round_date"].value)
        year = month[0] if month else to_year(comps["round_date"].value)
    elif "round_year" in comps:
        year = to_year(comps["round_year"].value)
    candidates = dated
    if year is not None:
        candidates = [(i, m) for i, m in dated if to_year(_round_date(m)) == year]
        if not candidates:
            return None
    if "round_type" in comps:
        typed = [
            (i, m)
            for i, m in candidates
            if m.round_type and contains_phrase(m.round_type, comps["round_type"].value)
        ]
        if typed:
            candidates = typed
        elif year is None:
            return None
    return max(candidates, key=lambda t: _round_date(t[1]) or "")


def _round_summary(m: FundingRound) -> str:
    parts = [m.round_type or "round", f"on {_round_date(m)}"]
    if m.amount_usd:
        parts.append(f"USD {int(m.amount_usd)}")
    investors = [n for n in (m.investors or []) if n]
    if investors:
        parts.append("investors: " + ", ".join(investors))
    return " ".join(parts)


async def gather_funding(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    comps = _components(claim)
    record = await env.profile()
    source = await env.profile_source(R.DATA_PROVIDER, "Funding record")
    out.read(source, env.company)
    milestones = list(record.funding.milestones or []) if record and record.funding else []
    picked = select_milestone(claim, milestones)
    if picked is not None:
        i, m = picked
        span = _round_summary(m)
        when = _round_date(m)
        month = to_month(when)
        values: dict[str, Any] = {
            "raised": True,
            "round_year": to_year(when),
            "round_date": f"{month[0]:04d}-{month[1]:02d}" if month else None,
            "round_type": m.round_type,
            "amount_usd": int(m.amount_usd) if m.amount_usd else None,
        }
        if "investor" in comps:
            values["investor"] = next(
                (n for n in m.investors or [] if contains_phrase(n, comps["investor"].value)), None
            )
        for component in comps:
            value = values.get(component)
            if value is None:
                continue
            out.facts.append(
                await fact_from_field(
                    env.store,
                    source,
                    entity_ref=env.company,
                    component=component,
                    value=value,
                    field_path=f"funding.milestones[{i}].{component}",
                    span=span,
                    as_of=_as_of(when),
                )
            )
    hits = await env.search("funding")
    await _read_units(env, claim, await _hit_units(env, hits, "funding", fetch=False), out)
    return out


_EVENT_TOPICS = (
    ("warehouse", "warehouse"),
    ("facility", "facility"),
    ("plant", "plant"),
    ("factory", "plant"),
    ("hub", "hub"),
    ("office", "office"),
    ("launch", "launch"),
    ("acqui", "acquisition"),
    ("partner", "partnership"),
)


def event_topic(claim: Claim) -> str:
    comps = _components(claim)
    text = f"{comps['event'].value if 'event' in comps else ''} {claim.text}".casefold()
    for word, topic in _EVENT_TOPICS:
        if word in text:
            return topic
    return "expansion"


async def gather_dated_event(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    comps = _components(claim)
    units = await stored_units(env, NEWS_CLASSES)
    topic = event_topic(claim)
    # Narrow by the enriched HQ city when the claim is about a place; the claim's own
    # city never goes into the query.
    hits = await env.search(topic, hq_city="operating_city" in comps)
    units += await _hit_units(env, hits, topic, fetch=True)
    await _read_units(env, claim, units, out)
    return out


async def gather_identity_location(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    comps = _components(claim)
    await _read_units(env, claim, await stored_units(env, REGISTRY_CLASSES), out)
    record = await env.profile()
    if not record:
        return out
    locations, info = record.locations, record.basic_info
    profile_facts: list[tuple[str, Any, str, str]] = []
    if locations and locations.headquarters:
        # `headquarters` is a free-text address ("DLF QE, Haryana, India"). An address
        # that does not name the claimed city does not directly conflict with it, so
        # it is a fact only when it names the city; otherwise the profile was read
        # and is silent on the question.
        for component in ("hq_city", "operating_city"):
            if component in comps and contains_phrase(
                locations.headquarters, comps[component].value
            ):
                profile_facts.append(
                    (component, locations.headquarters, "locations.headquarters", "HQ")
                )
    if locations and locations.country and "country" in comps:
        # The provider stores an ISO code ("IND"); compared as text with a claimed
        # "India" it read as a contradiction. An unknown code is not a fact.
        country = country_name(locations.country)
        if country:
            profile_facts.append(("country", country, "locations.country", "HQ"))
    if info and info.year_founded and "incorporation_year" in comps:
        profile_facts.append(
            ("incorporation_year", info.year_founded, "basic_info.year_founded", "founded year")
        )
    if profile_facts or any(c in comps for c in ("hq_city", "country", "incorporation_year")):
        source = await env.profile_source(R.DATA_PROVIDER, "Company profile")
        out.read(source, env.company)
        for component, value, path, _ in profile_facts:
            out.facts.append(
                await fact_from_field(
                    env.store,
                    source,
                    entity_ref=env.company,
                    component=component,
                    value=value,
                    field_path=path,
                    as_of=_as_of(record.updated_at),
                )
            )
    return out


async def gather_registry_only(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    if env.company_id is not None and env.case.identity_status == "confirmed":
        await _read_units(env, claim, await stored_units(env, REGISTRY_CLASSES), out)
    return out


async def gather_financials(env: CheckEnv, claim: Claim) -> Gathered:
    """One public results search for a listed company: the confirmed name plus fixed
    words. The top 1-2 pages are read, the company's own site and the exchanges
    first; facts come through the same verbatim-span extraction as every check."""
    out = Gathered(entity_ids=[env.company_entity])
    hits = await env.search("results")
    terms = env.terms()

    def rank(hit: WebSearchHit) -> int:
        if same_site(hit.url, terms.domain):
            return 0
        return 1 if is_exchange(hit.url) else 2

    hits = sorted(hits, key=rank)[:MAX_FETCH]
    units = await _hit_units(env, hits, "results", fetch=True)
    await _read_units(env, claim, units, out)
    return out


async def gather_nothing(env: CheckEnv, claim: Claim) -> Gathered:
    return Gathered(entity_ids=[env.company_entity])


# --- Targeted public lookups (policy 2026-11-22.6) ---------------------------------


@dataclass(frozen=True)
class Lookup:
    """One targeted public search planned by a category source module.

    `words` come from `query.LOOKUP_WORDS`; `entity` is one public name from the
    claim's structured components (partner, certifier, mark), never claim wording.
    A page on one of `party_hosts` (exact host names, never any subdomain: user
    content lives on subdomains such as forums) is the other party's own record (partner
    directory, certifier register, trademark registry mirror) and gets `party_class`.
    """

    label: str  # shown as "searched: <label>"
    words: str
    entity: str | None = None
    site: str | None = None
    party_hosts: tuple[str, ...] = ()
    party_class: SourceReliability = R.COUNTERPARTY_CONFIRMATION
    # Exact hosts where the company publishes about itself on another party's site
    # (marketplace listings): bound like any page, classed company_announcement.
    listing_hosts: tuple[str, ...] = ()
    focus: tuple[str, ...] = ()  # words that pick the relevant passages of a fetched page
    quote_entity: bool = True  # False for a standard's name ("ISO 27001")


def classify_hit(
    hit: WebSearchHit,
    terms: PublicTerms,
    corroborators: dict[str, list[str]],
    lookup: Lookup,
    page_text: str = "",
) -> Attachment:
    """Attach a lookup result to the company. The other party's own page must name
    the company AND carry a second identifier (its domain or HQ city), like any page;
    then it is the other party's record (`lookup.party_class`). The company's own site
    is checked first: it is never the other party, whatever the lookup says."""
    if same_site(hit.url, terms.domain):
        return attach_hit(hit, terms, corroborators)
    on_party = on_party_site(hit.url, lookup, terms)
    listing = _on_hosts(hit.url, lookup.listing_hosts)
    if on_party or listing:
        cls, how = (
            (lookup.party_class, "party_site") if on_party else (R.COMPANY_ANNOUNCEMENT, "listing")
        )
        probe = hit.model_copy(update={"url": "", "content": f"{hit.content or ''}\n{page_text}"})
        att = attach_hit(probe, terms, corroborators)
        if att.attached:
            return Attachment(True, cls, [how, *att.matched_on], None, att.ref_prefix)
        return Attachment(False, cls, [], att.reason)
    if page_text and not same_site(hit.url, terms.domain):
        hit = hit.model_copy(update={"content": f"{hit.content or ''}\n{page_text}"})
    return attach_hit(hit, terms, corroborators)


def _on_hosts(url: str | None, hosts: tuple[str, ...]) -> bool:
    host = host_of(url)
    return bool(host) and host in {h.casefold().removeprefix("www.") for h in hosts}


def on_party_site(url: str | None, lookup: Lookup, terms: PublicTerms | None = None) -> bool:
    """Is this page on the other party's own site? Curated exact hosts only (a host
    that merely carries the party's name may be a lookalike), and never the
    company's own domain."""
    if terms is not None and same_site(url, terms.domain):
        return False
    return _on_hosts(url, lookup.party_hosts)


def _names_company(hit: WebSearchHit, terms: PublicTerms) -> bool:
    text = f"{hit.title or ''}\n{hit.snippet or ''}\n{hit.content or ''}"
    return same_site(hit.url, terms.domain) or contains_phrase(text, terms.company_name)


async def run_lookups(env: CheckEnv, claim: Claim, lookups: list[Lookup], out: Gathered) -> None:
    """Run at most `policy.MAX_LOOKUPS_PER_CLAIM` lookups: one search each and at most
    one page fetch, then verbatim-span extraction as every check. Each is recorded on
    `out.searched`. A lookup the budget refuses is skipped; if every lookup was
    refused, `BudgetExceeded` propagates and the claim reads Not checked (budget)."""
    from app.jobs import BudgetExceeded

    lookups = lookups[: policy.MAX_LOOKUPS_PER_CLAIM]
    if env.case.identity_status != IdentityStatus.CONFIRMED or env.company_id is None:
        for lookup in lookups:
            out.searched.append(
                {"label": lookup.label, "query": None, "results": [], "skipped": "identity"}
            )
        return
    record = await env.profile()
    terms, deny = env.terms(), env.deny_terms()
    corroborators = {"hq_city": [c for c in [_hq_city(record)] if c]}
    units: list[TextUnit] = []
    ran, refused = 0, 0
    for lookup in lookups:
        entry: dict[str, Any] = {
            "label": lookup.label,
            "query": None,
            "results": [],
            "skipped": None,
        }
        out.searched.append(entry)
        try:
            query = build_lookup(
                terms,
                lookup.words,
                entity=lookup.entity,
                site=lookup.site,
                deny=deny,
                quote_entity=lookup.quote_entity,
            )
        except UnsafeQuery as exc:
            entry["skipped"] = "unsafe_query"
            env.log(f"lookup skipped ({lookup.label}): {exc}")
            continue
        entry["query"] = query
        try:
            hits = (await env.lookup_search(query, lookup.label))[:MAX_HITS]
            ran += 1
            # The one page worth reading: the other party's own page first, then the
            # company's, and only one that names the company.
            ranked = sorted(
                (h for h in hits if _names_company(h, terms)),
                key=lambda h: (
                    0 if on_party_site(h.url, lookup, terms) else 1,
                    0 if same_site(h.url, terms.domain) else 1,
                ),
            )
            pages: dict[str, str] = {}
            if ranked and ranked[0].url:
                try:
                    urls = [h.url for h in ranked[: policy.MAX_FETCH_PER_LOOKUP] if h.url]
                    fetched = await env.fetch(urls)
                    pages = {u: html_to_text(h) for u, h in fetched.items()}
                except BudgetExceeded:
                    env.log(f"page fetch skipped ({lookup.label}): budget")
        except BudgetExceeded:
            entry["skipped"] = "budget"
            refused += 1
            continue
        for hit in hits:
            page = pages.get(hit.url or "", "")
            att = classify_hit(hit, terms, corroborators, lookup, page)
            source = await env.store.source(
                SourceSpec(
                    provider="web",
                    endpoint_or_url=hit.url or "",
                    reliability=att.reliability,
                    label=hit.title or host_of(hit.url) or "web page",
                    publisher=host_of(hit.url),
                    request=env._request(
                        lookup=lookup.label,
                        query=query,
                        matched_on=att.matched_on,
                        entity_name=terms.company_name,
                    ),
                    origin_key=syndication_origin(hit.title, hit.url),
                    attached=att.attached,
                    unattached_reason=att.reason,
                )
            )
            entry["results"].append(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "source_class": att.reliability.value,
                    "attached": att.attached,
                }
            )
            if not att.attached:
                env.log(f"unattached lookup record {host_of(hit.url)}: {att.reason}")
                continue
            text = ""
            if page:
                focus = [terms.company_name, terms.domain or "", lookup.entity or "", *lookup.focus]
                text = relevant_passages(page, [f for f in focus if f])
            if not text.strip():
                text = "\n".join(t for t in (hit.title, hit.snippet) if t)
            if text.strip():
                units.append(
                    TextUnit(
                        source=source,
                        text=text,
                        entity_ref=f"crustdata:{att.ref_prefix}:{env.company_id}",
                        as_of=hit_date(hit),
                        label=f"web page ({host_of(hit.url)})",
                    )
                )
    if lookups and ran == 0 and refused:
        raise BudgetExceeded()
    await _read_units(env, claim, units, out)


# --- Per-category public source modules ----------------------------------------
# A module `checks/sources/<module>.py` defines
# `async def gather(env: CheckEnv, claim: Claim) -> Gathered`, usually by planning
# `Lookup`s and calling `run_lookups`. One line per module here; imported lazily
# because the modules import this one.
SOURCE_MODULES: dict[str, str] = {
    "partnership": "partnership",
    "compliance": "compliance",
}


def source_kind(claim: Claim) -> str:
    """Which source module a claim goes to: its category, except that a customer
    count with no named customer is `customers`, and other customer and partner
    claims are `partnership`."""
    if claim.category is ClaimCategory.CUSTOMER_PARTNERSHIP:
        names = {c.name for c in claim.components}
        if names & {"customer_count", "country_count"} and "counterparty" not in names:
            return "customers"
        return "partnership"
    return claim.category.value


def gatherer_for(claim: Claim) -> Callable[[CheckEnv, Claim], Awaitable[Gathered]]:
    module = SOURCE_MODULES.get(source_kind(claim))
    if module is not None:
        return importlib.import_module(f"{__package__}.sources.{module}").gather
    return GATHERERS[claim.category]


GATHERERS: dict[ClaimCategory, Callable[[CheckEnv, Claim], Awaitable[Gathered]]] = {
    ClaimCategory.TEAM_SIZE: gather_team_size,
    ClaimCategory.LEADERSHIP_HISTORY: gather_leadership,
    ClaimCategory.FUNDING: gather_funding,
    ClaimCategory.DATED_EVENT: gather_dated_event,
    ClaimCategory.IDENTITY_INCORPORATION: gather_identity_location,
    ClaimCategory.LOCATION: gather_identity_location,
    ClaimCategory.DEBT_SECURITY: gather_registry_only,
    ClaimCategory.LITIGATION: gather_registry_only,
    ClaimCategory.CUSTOMER_PARTNERSHIP: gather_nothing,
    ClaimCategory.FINANCIALS: gather_financials,
    ClaimCategory.COMPLIANCE: gather_nothing,  # until checks/sources/compliance.py
    ClaimCategory.INTELLECTUAL_PROPERTY: gather_nothing,  # until its source module
    ClaimCategory.OTHER: gather_nothing,
}
