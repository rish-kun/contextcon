"""`verify.financials`: public financial figures for the confirmed company (design §6.4,
H-proofgate §5.3 financials playbook).

Runs for every case once identity is confirmed, after the profile and registry steps,
and makes at most two public lookups. Each lookup is either a web search plus a read of
the top two qualifying pages, or a re-read of registry pages the registry step already
found. The second lookup runs only when the first found no figures.

- **Listed** (CIN starting with `L`, a stock symbol or IPO date on the Crustdata record,
  or provider company type "Public Company"): exchange filings and investor-relations
  results pages, from `"<name>" quarterly results revenue FY27`, then
  `"<name>" annual results revenue FY26`.
- **Unlisted, Indian**: the registry pages already found, then one registry-mirror
  search on the CIN and name for the revenue band, net worth and last filed year.
- **Unknown**: the results search first (it would find an exchange filing if one
  exists), then the registry-mirror search for an Indian company.

Queries carry only public lookup terms: the confirmed public name, CIN, a fiscal-year
label and fixed words (`assert_public` checks the finished query). Seller text never
reaches a search provider. Each figure is stored with its verbatim quote, its period
("Q2 FY27", "FY24"), its unit (crore, lakh, million) and the identifiers that bind the
page to the company; a page without a corroborating identifier is kept unattached and
never used. What was searched is recorded on the case, so "nothing found" can say where.
Re-running the step upserts the same rows and replaces the search record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select

from app.db.models import Case, Evidence, Source
from app.domain.enums import ClaimCategory, SourceReliability
from app.extraction import ClaimRef, extract_facts
from app.jobs import StepContext, step_handler
from app.pipelines.verify import common
from app.pipelines.verify.common import (
    FINANCIALS,
    ConfirmedEntity,
    PublicTerms,
    host_matches,
    host_of,
    normalize_name,
)
from app.pipelines.verify.registry import corroborate, reliability_for
from app.rules import financials as fin
from app.rules.compare import contains_phrase

MAX_LOOKUPS = 2
MAX_PAGES = 2
EXCHANGE_HOSTS = ("nseindia.com", "bseindia.com")

# Fixed words per lookup. Nothing else but the public name, CIN and an FY label.
QUERY_WORDS = {
    "results": "quarterly results revenue",
    "annual": "annual results revenue",
    "registry_search": "revenue net worth balance sheet",
}
_TOKEN = re.compile(r"[\w.'&-]+", re.UNICODE)
_FY_TOKEN = re.compile(r"^fy\d{2}$", re.I)

# Extracted fact names → the financial components the rules know.
FACT_ALIASES = {
    "revenue": "revenue",
    "revenue_from_operations": "revenue",
    "total_revenue": "revenue",
    "turnover": "revenue",
    "net_sales": "revenue",
    "profit": "profit",
    "net_profit": "profit",
    "pat": "profit",
    "profit_after_tax": "profit",
    "ebitda": "ebitda",
    "net_worth": "net_worth",
    "networth": "net_worth",
    "revenue_band": "revenue_band",
    "turnover_band": "revenue_band",
}
TEXT_COMPONENTS = frozenset({"revenue_band"})


# --- Listing ---------------------------------------------------------------------


def listing_status(entity: dict[str, Any]) -> tuple[str, str, str | None]:
    """(listed | unlisted | unknown, basis in words, signal), free signals first
    (H-proofgate §5.2). The signal says how strong "listed" is: `cin`, `stock_symbol`
    and `ipo_date` are records of a listing; `company_type` is only a provider label,
    enough to plan an exchange search but not to trust the company's own site."""
    cin = str(entity.get("cin") or "").strip().upper()
    if cin.startswith("L"):
        return "listed", f"CIN {cin} begins with L (listed company)", "cin"
    symbols = [s for s in entity.get("stock_symbols") or [] if s]
    if symbols:
        shown = ", ".join(map(str, symbols[:3]))
        return "listed", f"stock symbol {shown} on the company record", "stock_symbol"
    if entity.get("ipo_date"):
        return "listed", f"IPO date {entity['ipo_date']} on the company record", "ipo_date"
    ctype = str(entity.get("provider_company_type") or "")
    if "public" in ctype.casefold():
        return "listed", f'company type "{ctype}" on the company record', "company_type"
    if cin.startswith("U"):
        return "unlisted", f"CIN {cin} begins with U (unlisted company)", "cin"
    return "unknown", "no CIN, stock symbol or public company type on record", None


def is_indian(entity: dict[str, Any]) -> bool:
    country = str(entity.get("country") or "").strip().casefold()
    return bool(entity.get("cin")) or country in {"ind", "in", "india"}


def plan_lookups(listing: str, india: bool, registry_pages: bool) -> list[str]:
    if listing == "listed":
        plan = ["results", "annual"]
    elif listing == "unlisted":
        plan = (["registry_pages"] if registry_pages else []) + (
            ["registry_search"] if india else ["results"]
        )
    else:
        plan = ["results", "registry_search" if india else "annual"]
    return plan[:MAX_LOOKUPS]


# --- Queries ---------------------------------------------------------------------


def _quoted(term: str) -> str:
    return '"' + term.replace('"', "") + '"'


def financials_query(terms: PublicTerms, kind: str, today: date) -> str:
    fy = fin.indian_fy(today)
    parts: list[str] = []
    if kind == "registry_search" and terms.cin:
        parts.append(_quoted(terms.cin))
    parts += [_quoted(terms.name), QUERY_WORDS[kind]]
    if kind == "results":
        parts.append(fin.fy_label(fy))
    elif kind == "annual":
        parts.append(fin.fy_label(fy - 1))
    query = " ".join(parts)
    assert_public(query, terms)
    return query


def assert_public(query: str, terms: PublicTerms) -> None:
    """Every token is the public name, the CIN, an FY label or a fixed word."""
    allowed = {
        t.casefold()
        for part in (terms.name, terms.cin or "", *QUERY_WORDS.values())
        for t in _TOKEN.findall(part)
    }
    extra = [
        t for t in _TOKEN.findall(query) if t.casefold() not in allowed and not _FY_TOKEN.match(t)
    ]
    if extra:
        raise ValueError("financials query contains terms that are not public lookup terms")


# --- Pages -----------------------------------------------------------------------


def is_exchange(url: str | None) -> bool:
    host = host_of(url)
    return any(host_matches(host, h) for h in EXCHANGE_HOSTS)


MIN_SYMBOL = 3


def _symbols(raw: dict[str, Any]) -> list[str]:
    """`NSE:ACMEFRT` → `ACMEFRT`; at least three characters, matched as a whole token
    and only on an exchange's own pages."""
    out = []
    for s in raw.get("stock_symbols") or []:
        sym = str(s).split(":")[-1].strip()
        if len(sym) >= MIN_SYMBOL:
            out.append(sym)
    return out


def _own_site(url: str, entity: ConfirmedEntity) -> bool:
    """The company's primary domain only, not every domain a record lists."""
    return bool(entity.domain) and host_matches(host_of(url), entity.domain or "")


def _mentions_domain(raw: str, domain: str) -> bool:
    """The domain as a whole host name in the page, not inside a longer one."""
    pattern = r"(?<![\w.-])(?:www\.)?" + re.escape(domain) + r"(?![\w-]|\.[a-z])"
    return re.search(pattern, raw, re.IGNORECASE) is not None


def page_class(url: str, entity: ConfirmedEntity, kind: str) -> str | None:
    """Which pages a lookup reads, and what each is: exchange filings and the company's
    own site for the results searches, registry hosts for the registry lookups."""
    if kind in ("registry_pages", "registry_search"):
        return reliability_for(url)
    if is_exchange(url):
        return SourceReliability.REGISTRY_MIRROR  # filed results: reported, not audited
    if _own_site(url, entity):
        return SourceReliability.COMPANY_ANNOUNCEMENT
    return None


def bind_page(
    entity: ConfirmedEntity,
    raw_entity: dict[str, Any],
    url: str,
    raw: str,
    text: str,
    reliability: str,
) -> list[str]:
    """Identifiers on the page that tie it to the confirmed company. Empty → unattached.
    A name alone never binds."""
    if reliability in (SourceReliability.REGISTRY, SourceReliability.REGISTRY_MIRROR) and (
        not is_exchange(url)
    ):
        return corroborate(entity, raw, text, {})
    if _own_site(url, entity):
        return ["domain"]
    if not contains_phrase(text, entity.public_name or entity.name):
        return []
    matched: list[str] = []
    if entity.cin and entity.cin.lower() in text.lower():
        matched.append("cin")
    if any(_mentions_domain(raw, d) for d in entity.domains):
        matched.append("domain")
    tokens = set(_TOKEN.findall(text))
    if is_exchange(url) and any(s in tokens for s in _symbols(raw_entity)):
        matched.append("stock_symbol")
    return matched


@dataclass
class Figure:
    component: str
    value: str
    span: str
    period: fin.Period | None
    period_quote: str | None
    amount: fin.Amount | None
    unit_quote: str | None


def read_figures(facts: list[Any], text: str, title: str | None) -> list[Figure]:
    """Financial facts from one page, each with its period and unit. A bare number takes
    the unit of the heading above it ("₹ in crore"); the period comes from the quote,
    else the text just before it, else the page title."""
    out: list[Figure] = []
    for f in facts:
        component = FACT_ALIASES.get(f.name)
        if component is None:
            continue
        start = f.start if f.start is not None else max(0, text.find(f.span))
        before = text[max(0, start - 600) : start]
        period, period_quote = None, None
        for where in (f.span, before[-300:], before, title or ""):
            period = fin.parse_period(where)
            if period is not None:
                period_quote = where if where in (f.span, title) else where.strip()[-160:]
                break
        amount, unit_quote = None, None
        if component not in TEXT_COMPONENTS:
            amount = fin.parse_amount(f.value)
            if amount is None:
                continue
            if amount.unit is None:
                note = fin.unit_note(text[max(0, start - 3000) : start]) or fin.unit_note(text)
                if note is not None:
                    amount, unit_quote = fin.scale_bare(amount, note), note[2]
        out.append(Figure(component, f.value, f.span, period, period_quote, amount, unit_quote))
    return out


def _claim(entity: ConfirmedEntity) -> ClaimRef:
    return ClaimRef(
        text=(
            f"Reported financial results of {entity.public_name or entity.name}: revenue "
            "(revenue from operations or turnover), profit after tax, EBITDA, net worth and "
            "any revenue or turnover band, each for the period it is stated for."
        ),
        category=ClaimCategory.FINANCIALS,
        components={"revenue": "", "profit": "", "ebitda": "", "net_worth": "", "revenue_band": ""},
    )


@dataclass
class Lookup:
    kind: str
    query: str | None = None
    urls: list[str] = field(default_factory=list)
    hits: int = 0
    read: list[str] = field(default_factory=list)
    figures: int = 0

    def describe(self) -> str:
        hosts = ", ".join(dict.fromkeys(host_of(u) or u for u in self.read))
        found = f"; {self.figures} figure(s)" if self.figures else "; no figures"
        if self.kind == "registry_pages":
            return f"registry pages already found ({hosts or 'none readable'}){found}"
        what = f"web search {self.query}"
        if not self.urls:
            return f"{what}: no filing, results or registry pages among {self.hits} result(s)"
        return f"{what}: read {hosts or 'no page could be fetched'}{found}"


async def _known_registry_urls(ctx: StepContext, case: Case) -> list[str]:
    """Registry pages `verify.registry` attached to the company."""
    rows = await ctx.session.execute(
        select(Source.endpoint_or_url)
        .join(Evidence, Evidence.source_id == Source.id)
        .where(
            Source.case_id == case.id,
            Source.provider == "web",
            Source.source_class.in_(
                [SourceReliability.REGISTRY, SourceReliability.REGISTRY_MIRROR]
            ),
            ~Evidence.entity_ref.startswith("unattached:"),
            Evidence.field_path.startswith("registry."),
        )
        .order_by(Source.endpoint_or_url)
    )
    urls = [u for u in dict.fromkeys(rows.scalars()) if common.readable_url(u)]
    return [u for u in urls if reliability_for(u) is not None][:MAX_PAGES]


@step_handler(FINANCIALS)
async def financials_evidence(ctx: StepContext) -> dict[str, Any]:
    case = await common.load_case(ctx)
    try:
        entity = ConfirmedEntity.of(case)
        terms = PublicTerms.of(entity)
    except common.IdentityNotConfirmed:
        return common.blocked_output(ctx)

    raw_entity = dict((case.identity_identifiers or {}).get("entity") or {})
    listing, basis, signal = listing_status(raw_entity)
    registry_urls = await _known_registry_urls(ctx, case)
    today = datetime.now(UTC).date()
    plan = plan_lookups(listing, is_indian(raw_entity), bool(registry_urls))

    client = common.clients.crustdata(ctx)
    llm = common.clients.llm(ctx)
    lookups: list[Lookup] = []
    total = 0
    try:
        for kind in plan:
            lookup = Lookup(kind)
            lookups.append(lookup)
            if kind == "registry_pages":
                lookup.urls = registry_urls
            else:
                lookup.query = financials_query(terms, kind, today)
                await ctx.require_budget(1)
                await ctx.set_detail("Searching public financial filings")
                found, _ = await client.web_search(
                    lookup.query, location="IN" if kind == "registry_search" else None
                )
                lookup.hits = len(found.results)
                ranked = sorted(
                    (h for h in found.results if common.readable_url(h.url)),
                    key=lambda h: 0 if is_exchange(h.url) else 1,
                )
                lookup.urls = list(
                    dict.fromkeys(
                        h.url for h in ranked if page_class(h.url, entity, kind) is not None
                    )
                )[:MAX_PAGES]
            if lookup.urls:
                await ctx.require_budget(len(lookup.urls))
                await ctx.set_detail(f"Reading {len(lookup.urls)} financial pages")
                pages, _ = await client.fetch_pages(lookup.urls)
                for page in pages:
                    if page.success and page.url:
                        lookup.read.append(page.url)
                        lookup.figures += await _store_page(
                            ctx, case, entity, raw_entity, llm, page, kind
                        )
            total += lookup.figures
            if total:
                break
    finally:
        await common.close_quietly(client)
        await common.close_quietly(llm)

    common.update_entity(
        case,
        financials={
            "listing": listing,
            "listing_basis": basis,
            "listing_signal": signal,
            "searched": [lk.describe() for lk in lookups],
            "searched_at": datetime.now(UTC).isoformat(),
        },
    )
    await ctx.session.flush()
    ctx.result = f"{total} financial figures from {len(lookups)} lookups ({listing})"
    return {"listing": listing, "lookups": len(lookups), "figures": total, "on": today.isoformat()}


async def _store_page(
    ctx: StepContext,
    case: Case,
    entity: ConfirmedEntity,
    raw_entity: dict[str, Any],
    llm: Any,
    page: Any,
    kind: str,
) -> int:
    """Extract, bind and store one page's figures. Returns how many were attached."""
    reliability = page_class(page.url, entity, kind)
    if reliability is None:
        return 0
    text = common.html_to_text(page.content)
    facts = []
    for chunk in common.chunks(text):
        result = await extract_facts(llm, _claim(entity), chunk, source_label=page.url)
        offset = text.find(chunk)
        for f in result.facts:
            if f.start is not None and offset >= 0:
                f.start += offset
            facts.append(f)
    figures = read_figures(facts, text, page.title)
    if not figures:
        return 0
    matched = bind_page(entity, raw_entity, page.url, page.content or "", text, reliability)
    ref = (
        common.attached_ref(entity.ref, matched)
        if matched
        else common.unattached_ref("no corroborating identifier on the page")
    )
    source = await common.get_or_create_source(
        ctx,
        case,
        provider="web",
        endpoint_or_url=page.url,
        source_class=reliability,
        request={
            "purpose": "financials",
            "query_terms": ["name", "cin"] if entity.cin else ["name"],
        },
        title=page.title,
        publisher=host_of(page.url),
    )
    retrieved = datetime.now(UTC).date()
    for fig in figures:
        label = fig.period.label if fig.period else "undated"
        await common.upsert_evidence(
            ctx.session,
            source,
            case_id=case.id,
            origin_key=f"financials:{fig.component}:{label}:{normalize_name(fig.value)}",
            entity_ref=ref,
            field_path=f"financials.{fig.component}",
            span=fig.span,
            value={
                "component": fig.component,
                "value": fig.value,
                "period": fig.period.label if fig.period else None,
                "period_end": fig.period.end.isoformat() if fig.period else None,
                "period_months": fig.period.months if fig.period else None,
                "period_quote": fig.period_quote,
                "amount": fig.amount.value if fig.amount else None,
                "currency": fig.amount.currency if fig.amount else None,
                "unit": fig.amount.unit if fig.amount else None,
                "unit_quote": fig.unit_quote,
            },
            as_of=fig.period.end if fig.period else retrieved,
        )
    return len(figures) if matched else 0
