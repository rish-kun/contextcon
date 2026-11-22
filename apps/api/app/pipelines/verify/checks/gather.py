"""Evidence gathering per claim category (CP-21), under the identity guard and budget.

| Category                         | Sources                                                    |
|----------------------------------|------------------------------------------------------------|
| team_size                        | enrich headcount (a profile signal, never a payroll count) |
| leadership_history               | person search at the confirmed company id; career records  |
| funding                          | enrich funding rounds + dated news (web search)            |
| dated_event                      | stored news/articles + targeted web search + page fetch    |
| identity_incorporation, location | stored registry evidence + enriched HQ / founded year      |
| debt_security, litigation        | stored registry evidence only (no dedicated v1 check)      |
| customer_partnership, financials | none in v1: the rules answer cannot_verify + what settles  |

Every record is attached to the confirmed company or person by an identifier, never
by name alone: people by company id (and name, when the claim names them), web pages
by the company's domain, or by its name together with a second identifier (HQ city,
a founder's name, an investor). Pages that only share the name are kept as unattached
sources and never become evidence.

Web queries come from `query.build_query` (company name, domain, a city, one topic
word). Claim text is never sent to a search provider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.crustdata_models import CompanyRecord, FundingRound, PersonProfile, WebSearchHit
from app.db.models import Case
from app.db.models import Evidence as EvidenceRow
from app.db.models import Source as SourceRow
from app.domain.enums import ClaimCategory, SourceReliability
from app.domain.types import Claim, ExtractedFact
from app.extraction.llm import StructuredLlm
from app.pipelines.verify.checks.facts import (
    TextUnit,
    fact_from_field,
    facts_from_text,
)
from app.pipelines.verify.checks.html import html_to_text, relevant_passages
from app.pipelines.verify.checks.query import PublicTerms, UnsafeQuery, build_query
from app.pipelines.verify.checks.sources import (
    NEWS_CLASSES,
    REGISTRY_CLASSES,
    EvidenceStore,
    SourceSpec,
    host_of,
    same_site,
    syndication_origin,
)
from app.rules.compare import contains_phrase, normalize_text, to_date, to_month, to_year

R = SourceReliability

# Same groups CP-19's profile step asks for, so the enrich call is a cache hit.
PROFILE_FIELDS = (
    "basic_info",
    "headcount",
    "funding",
    "people",
    "hiring",
    "locations",
    "taxonomy",
    "news",
)
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
        info = self._profile.basic_info if self._profile and self._profile.basic_info else None
        name = (info.name if info and info.name else None) or self.case.company_name
        domain = (info.primary_domain if info else None) or host_of(self.case.website)
        return PublicTerms(company_name=name, domain=domain)

    def _request(self, **extra: Any) -> dict[str, Any]:
        return {"written_by": WRITER, **extra}

    # --- Provider calls (memoised per check; cached across checks by the client) ---

    async def profile(self) -> CompanyRecord | None:
        if self._profile_loaded:
            return self._profile
        assert self.company_id is not None
        await self.budget(ENRICH_CREDITS)
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
        result, _ = await self.crustdata.search_company_leadership(
            self.company_id, limit=PEOPLE_LIMIT
        )
        self._people = list(result.profiles)
        return self._people

    async def search(self, topic: str, *, city: str | None = None) -> list[WebSearchHit]:
        try:
            query = build_query(self.terms(), topic, city=city)
        except UnsafeQuery as exc:
            self.log(f"web search skipped: {exc}")
            return []
        if query not in self._searches:
            await self.budget(WEB_SEARCH_CREDITS)
            result, _ = await self.crustdata.web_search(query, sources=["news", "web"])
            self._searches[query] = [h for h in result.results if h.url]
        return self._searches[query]

    async def fetch(self, urls: list[str]) -> dict[str, str]:
        if not urls:
            return {}
        await self.budget(WEB_FETCH_CREDITS * len(urls))
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
    ref_prefix: str | None = None  # `domain` or `hq_city`, see sources._REF_BASIS


def attach_hit(
    hit: WebSearchHit, terms: PublicTerms, corroborators: dict[str, list[str]]
) -> Attachment:
    """Attach a web record to the company only with an identifier beyond its name."""
    if same_site(hit.url, terms.domain):
        return Attachment(True, R.COMPANY_ANNOUNCEMENT, ["domain"], ref_prefix="domain")
    text = f"{hit.title or ''}\n{hit.snippet or ''}\n{hit.content or ''}"
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
                    entity_ref=f"{att.ref_prefix}:{env.company_id}",
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
    city = str(comps["operating_city"].value) if "operating_city" in comps else None
    hits = await env.search(topic, city=city)
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
        for component in ("hq_city", "operating_city"):
            if component in comps:
                profile_facts.append(
                    (component, locations.headquarters, "locations.headquarters", "HQ")
                )
    if locations and locations.country and "country" in comps:
        profile_facts.append(("country", locations.country, "locations.country", "HQ"))
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


async def gather_nothing(env: CheckEnv, claim: Claim) -> Gathered:
    return Gathered(entity_ids=[env.company_entity])


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
    ClaimCategory.FINANCIALS: gather_nothing,
    ClaimCategory.OTHER: gather_nothing,
}
