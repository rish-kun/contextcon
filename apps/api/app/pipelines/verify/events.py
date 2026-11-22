"""`verify.events`: recent dated events about the confirmed company (design §6.3 step 7).

One `web_search_live` news search built from public terms only (the confirmed name and
domain together), then `web_enrich_live` reads the top articles. For each article:

- the publish date comes from the page's own metadata (or the search hit's date);
- the article is attached only when it corroborates the entity: the company's domain
  (in the text or a link), its profile URL or CIN, or its name together with its HQ
  city. A name alone is not enough; such articles stay unattached candidates;
- syndicated copies (same headline, or same opening text) share one `origin_key` and
  produce one event;
- a company announcement (published on the company's own domain or a press-release
  wire) is recorded as an announcement: source class `company_announcement` and
  stage `announced`, never as proof the thing happened.

`extract_facts` reads the event description with a verbatim span; when it finds none,
the event is the dated article itself (kind `news`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import delete, select

from app.clients.crustdata import failed_urls
from app.db.models import Event, Evidence
from app.domain.enums import ClaimCategory, SourceReliability
from app.extraction import ClaimRef, extract_facts, span_in
from app.jobs import StepContext, step_handler
from app.pipelines.verify import common
from app.pipelines.verify.common import (
    EVENTS,
    ConfirmedEntity,
    PublicTerms,
    host_matches,
    host_of,
    normalize_name,
)

MAX_ARTICLES = 4
PRESS_WIRES = (
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
    "newswire.com",
    "einpresswire.com",
    "prlog.org",
    "accesswire.com",
)
ORIGIN_PREFIX = "article:"

_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("funding", re.compile(r"\b(rais\w*|funding|series [a-h]\b|invest\w*|crore round)", re.I)),
    ("acquisition", re.compile(r"\b(acquir\w*|acquisition|merger|buys?)\b", re.I)),
    ("facility", re.compile(r"\b(warehouse|facility|hub|plant|fulfil+ment cent\w*|depot)\b", re.I)),
    ("launch", re.compile(r"\b(launch\w*|unveil\w*|introduc\w*)\b", re.I)),
    ("expansion", re.compile(r"\b(expan\w*|enters?|new market|opens?)\b", re.I)),
    ("partnership", re.compile(r"\b(partner\w*|tie[- ]up|collaborat\w*|alliance)\b", re.I)),
    (
        "leadership",
        re.compile(r"\b(appoint\w*|names? .* (ceo|cfo|coo)|steps down|joins as)\b", re.I),
    ),
    ("results", re.compile(r"\b(revenue|profit|loss|results|ipo|listing)\b", re.I)),
)
_ANNOUNCED = re.compile(
    r"\b(plans? to|will (open|launch|set up|expand)|to open|announc\w*)\b", re.I
)
_TITLE_SEPARATOR = re.compile(r"\s+[|–—]\s+|\s+-\s+")


def origin_key(title: str | None, text: str) -> str:
    """Same headline (publisher suffix removed) or same opening text → same origin."""
    parts = _TITLE_SEPARATOR.split(title or "")
    if len(parts) > 1 and len(parts[-1]) <= 60:  # "Headline | Publisher"
        parts = parts[:-1]
    head = normalize_name(" ".join(parts))
    basis = head if len(head) >= 20 else normalize_name(text[:400])
    return ORIGIN_PREFIX + hashlib.sha256(basis.encode()).hexdigest()[:20]


def event_kind(*texts: str | None) -> str:
    joined = " ".join(t for t in texts if t)
    for kind, pattern in _KINDS:
        if pattern.search(joined):
            return kind
    return "news"


def corroborate(entity: ConfirmedEntity, raw: str, text: str, url: str = "") -> list[str]:
    """Identifiers in the article that match the confirmed company. Empty → unattached.
    A page hosted on the company's own domain corroborates by domain."""
    raw_lower, hay = raw.lower(), text.lower()
    host = host_of(url)
    matched: list[str] = []
    if any(d in raw_lower or d in hay or host_matches(host, d) for d in entity.domains):
        matched.append("domain")
    if entity.profile_url and common.normalize_url(entity.profile_url) in raw_lower:
        matched.append("profile_url")
    if entity.cin and entity.cin.lower() in hay:
        matched.append("cin")
    named = normalize_name(entity.name) in normalize_name(text)
    if named and entity.hq_city and entity.hq_city.lower() in hay:
        matched.extend(["name", "hq_city"])
    return matched


def is_announcement(url: str, entity: ConfirmedEntity) -> bool:
    host = host_of(url)
    return any(host_matches(host, d) for d in (*entity.domains, *PRESS_WIRES))


def _claim(entity: ConfirmedEntity) -> ClaimRef:
    return ClaimRef(
        text=(
            f"Dated events about {entity.name}: launches, expansions, new facilities, "
            "funding, partnerships, acquisitions or leadership changes."
        ),
        category=ClaimCategory.DATED_EVENT,
        components={"event": "", "stage": "", "date": ""},
    )


@dataclass
class Article:
    url: str
    title: str | None
    publisher: str | None
    published: date | None
    date_markup: str | None
    origin: str
    matched: list[str]
    announcement: bool
    event_text: str | None
    span: str | None
    stage: str | None
    kind: str


def _hit_date(hit: Any) -> date | None:
    meta = hit.metadata if isinstance(hit.metadata, dict) else {}
    for key in ("date", "published_date", "publish_date", "published_at"):
        parsed = common.parse_date(meta.get(key)) or _human(meta.get(key))
        if parsed:
            return parsed
    return None


def _human(value: Any) -> date | None:
    return common.parse_human_date(value) if isinstance(value, str) else None


async def _read(
    ctx: StepContext, llm: Any, entity: ConfirmedEntity, page: Any, hit: Any
) -> Article | None:
    if not page.success or not page.url:
        return None
    raw = page.content or ""
    text = common.html_to_text(raw)
    if not text:
        return None
    published, markup = common.published_date(raw)
    if published is None and hit is not None:
        published = _hit_date(hit)
    matched = corroborate(entity, raw, text, page.url)
    announcement = is_announcement(page.url, entity)
    event_text = span = stage = None
    if matched:
        for chunk in common.chunks(text):
            result = await extract_facts(llm, _claim(entity), chunk, source_label=page.url)
            by_name = {f.name: f for f in result.facts}
            fact = by_name.get("event") or (result.facts[0] if result.facts else None)
            if fact is not None:
                event_text, span = fact.value, fact.span
                stage_fact = by_name.get("stage")
                stage = stage_fact.value.lower() if stage_fact else None
                break
    title = page.title or (hit.title if hit is not None else None)
    if span is None and title and span_in(title, text):
        span = title
    if announcement or (span and _ANNOUNCED.search(span)):
        stage = "announced"
    return Article(
        url=page.url,
        title=title,
        publisher=host_of(page.url),
        published=published,
        date_markup=markup,
        origin=origin_key(title, text),
        matched=matched,
        announcement=announcement,
        event_text=event_text,
        span=span,
        stage=stage if stage in {"announced", "planned", "operating", "completed"} else None,
        kind=event_kind(event_text, title),
    )


@step_handler(EVENTS)
async def dated_events(ctx: StepContext) -> dict[str, Any]:
    case = await common.load_case(ctx)
    try:
        entity = ConfirmedEntity.of(case)
    except common.IdentityNotConfirmed:
        return common.blocked_output(ctx)
    terms = PublicTerms.of(entity)
    location = "IN" if (entity.country or "").lower() in {"india", "in", "ind"} else None

    await ctx.require_budget(1)
    await ctx.set_detail("Searching news about the company")
    client = common.clients.crustdata(ctx)
    try:
        found, _ = await client.web_search(
            common.news_query(terms), sources=["news"], location=location
        )
        hits = {}
        for hit in found.results:
            if hit.url and hit.url not in hits:
                hits[hit.url] = hit
        urls = list(hits)[:MAX_ARTICLES]
        if not urls:
            ctx.result = "No news found"
            return {"articles": 0, "events": 0}
        await ctx.require_budget(len(urls))
        await ctx.set_detail(f"Reading {len(urls)} articles")
        pages, _ = await client.fetch_pages(urls)
    finally:
        await common.close_quietly(client)

    llm = common.clients.llm(ctx)
    articles: list[Article] = []
    try:
        for page in pages:
            article = await _read(ctx, llm, entity, page, hits.get(page.url or ""))
            if article is not None:
                articles.append(article)
    finally:
        await common.close_quietly(llm)

    # Re-runs replace this step's events (evidence rows upsert on their keys).
    article_evidence = select(Evidence.id).where(
        Evidence.case_id == case.id, Evidence.origin_key.startswith(ORIGIN_PREFIX)
    )
    await ctx.session.execute(
        delete(Event).where(Event.case_id == case.id, Event.evidence_id.in_(article_evidence))
    )

    first_by_origin: dict[str, tuple[Article, Any]] = {}
    unattached = 0
    for article in articles:
        source_class = (
            SourceReliability.COMPANY_ANNOUNCEMENT
            if article.announcement
            else SourceReliability.NEWS
        )
        source = await common.get_or_create_source(
            ctx,
            case,
            provider="web",
            endpoint_or_url=article.url,
            source_class=source_class,
            request={"query_terms": ["name", "domain"] if terms.domain else ["name"]},
            title=article.title,
            publisher=article.publisher,
        )
        attached = bool(article.matched) and article.published is not None
        if article.matched and article.published is None:
            ref = common.unattached_ref("no publish date")
        elif not article.matched:
            ref = common.unattached_ref("no corroborating identifier in the article")
        else:
            ref = common.attached_ref(entity.ref, article.matched)
        evidence_id = await common.upsert_evidence(
            ctx.session,
            source,
            case_id=case.id,
            origin_key=article.origin,
            entity_ref=ref,
            field_path=None,
            span=article.span,
            value={
                "title": article.title,
                "event": article.event_text,
                "kind": article.kind,
                "stage": article.stage,
                "published": article.published.isoformat() if article.published else None,
                "date_markup": article.date_markup,
                "url": article.url,
                "publisher": article.publisher,
                "announcement": article.announcement,
            },
            as_of=article.published,
        )
        if not attached:
            unattached += 1
            continue
        seen = first_by_origin.get(article.origin)
        if seen is None or (article.published or date.max) < (seen[0].published or date.max):
            first_by_origin[article.origin] = (article, evidence_id)

    for article, evidence_id in first_by_origin.values():
        assert article.published is not None
        ctx.session.add(
            Event(
                case_id=case.id,
                event_date=article.published,
                title=(article.event_text or article.title or "Article")[:1000],
                kind=article.kind,
                stage=article.stage,
                evidence_id=evidence_id,
            )
        )
    await ctx.session.flush()
    missing = failed_urls(urls, pages)
    ctx.result = f"{len(first_by_origin)} dated events from {len(articles)} articles" + (
        f"; {unattached} not attached" if unattached else ""
    )
    return {
        "articles": len(articles),
        "events": len(first_by_origin),
        "unattached": unattached,
        "failed": len(missing),
    }
