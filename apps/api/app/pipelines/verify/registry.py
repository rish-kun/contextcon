"""`verify.registry`: incorporation date and place, legal name and CIN from public
registry pages (design §6.3 step 1, builder call 9).

No official MCA API is reachable, so one `web_search_live` (location IN) looks for
registry-mirror pages using public lookup terms only (`PublicTerms`: the confirmed
name, domain and CIN; never claim or document text). The top two registry pages are
read with `web_enrich_live`, converted to text, and `extract_facts` pulls the facts
with verbatim spans. A page is `registry` only on the official MCA host; every other
registry host is `registry_mirror`. Pages from other hosts are not read.

Mirrors copy the same MCA record, so their facts share one `origin_key` per fact and
count as one source. A page is attached only when it names the company and matches a
corroborating identifier (domain, CIN, founded year = incorporation year, or HQ city);
otherwise its facts are kept as unattached candidates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.clients.crustdata import failed_urls
from app.domain.enums import ClaimCategory, SourceReliability
from app.extraction import ClaimRef, extract_facts
from app.jobs import StepContext, step_handler
from app.pipelines.verify import common
from app.pipelines.verify.common import (
    REGISTRY,
    ConfirmedEntity,
    PublicTerms,
    host_matches,
    host_of,
    normalize_name,
    parse_human_date,
)

OFFICIAL_HOSTS = ("mca.gov.in",)
MIRROR_HOSTS = (
    "zaubacorp.com",
    "tofler.in",
    "thecompanycheck.com",
    "falconebiz.com",
    "instafinancials.com",
    "companydetails.in",
    "indiafilings.com",
    "opencorporates.com",
    "corpository.com",
    "knowyourgst.com",
    "allcompanydata.com",
    "quickcompany.in",
    "startupindia.gov.in",
    "registrationwala.com",
)
MAX_PAGES = 2

FACT_ALIASES = {
    "legal_name": "legal_name",
    "company_name": "legal_name",
    "name": "legal_name",
    "incorporation_date": "incorporation_date",
    "date_of_incorporation": "incorporation_date",
    "incorporated_on": "incorporation_date",
    "incorporation_place": "incorporation_place",
    "place_of_incorporation": "incorporation_place",
    "registrar_of_companies": "incorporation_place",
    "roc": "incorporation_place",
    "registered_office": "registered_address",
    "registered_address": "registered_address",
    "cin": "cin",
    "corporate_identification_number": "cin",
}


def reliability_for(url: str) -> str | None:
    """`registry` on the official MCA host, `registry_mirror` on a known mirror, else None."""
    host = host_of(url)
    if any(host_matches(host, h) for h in OFFICIAL_HOSTS):
        return SourceReliability.REGISTRY
    if any(host_matches(host, h) for h in MIRROR_HOSTS):
        return SourceReliability.REGISTRY_MIRROR
    return None


def corroborate(entity: ConfirmedEntity, raw: str, text: str, facts: dict[str, str]) -> list[str]:
    """Identifiers on the page that match the confirmed company. Empty → unattached."""
    hay = text.lower()
    raw_lower = raw.lower()
    matched: list[str] = []
    if any(d in raw_lower for d in entity.domains):
        matched.append("domain")
    if entity.cin and entity.cin.lower() in hay:
        matched.append("cin")
    named = normalize_name(entity.name) in normalize_name(text)
    if named:
        inc = parse_human_date(facts.get("incorporation_date", ""))
        if entity.founded_year and inc and inc.year == entity.founded_year:
            matched.append("founded_year")
        if entity.hq_city and entity.hq_city.lower() in hay:
            matched.append("hq_city")
    strong = {"domain", "cin"}
    if not named and not strong & set(matched):
        return []
    return matched


def _claim(entity: ConfirmedEntity) -> ClaimRef:
    return ClaimRef(
        text=(
            f"Registry record of {entity.name}: legal name, date and place of "
            "incorporation, and corporate identification number (CIN)."
        ),
        category=ClaimCategory.IDENTITY_INCORPORATION,
        components={
            "legal_name": entity.name,
            "incorporation_date": "",
            "incorporation_place": "",
            "cin": "",
        },
    )


@step_handler(REGISTRY)
async def registry_evidence(ctx: StepContext) -> dict[str, Any]:
    case = await common.load_case(ctx)
    try:
        entity = ConfirmedEntity.of(case)
        terms = PublicTerms.of(entity)
    except common.IdentityNotConfirmed:
        return common.blocked_output(ctx)

    await ctx.require_budget(1)
    await ctx.set_detail("Searching public registry records")
    client = common.clients.crustdata(ctx)
    try:
        found, _ = await client.web_search(common.registry_query(terms), location="IN")
        urls = [
            hit.url
            for hit in found.results
            if common.readable_url(hit.url) and reliability_for(hit.url) is not None
        ]
        urls = list(dict.fromkeys(urls))[:MAX_PAGES]
        if not urls:
            ctx.result = "No registry pages found"
            return {"pages": 0, "attached": 0}
        await ctx.require_budget(len(urls))
        await ctx.set_detail(f"Reading {len(urls)} registry pages")
        pages, _ = await client.fetch_pages(urls)
    finally:
        await common.close_quietly(client)

    llm = common.clients.llm(ctx)
    attached_pages = 0
    learned: dict[str, str] = {}
    try:
        for page in pages:
            if not page.success or not page.url:
                continue
            reliability = reliability_for(page.url)
            if reliability is None:
                continue
            text = common.html_to_text(page.content)
            facts: dict[str, Any] = {}
            for chunk in common.chunks(text):
                result = await extract_facts(llm, _claim(entity), chunk, source_label=page.url)
                for fact in result.facts:
                    name = FACT_ALIASES.get(fact.name)
                    if name and name not in facts:
                        facts[name] = fact
            values = {k: f.value for k, f in facts.items()}
            matched = corroborate(entity, page.content or "", text, values)
            source = await common.get_or_create_source(
                ctx,
                case,
                provider="web",
                endpoint_or_url=page.url,
                source_class=reliability,
                request={"query_terms": ["name", "cin"] if terms.cin else ["name"]},
                title=page.title,
                publisher=host_of(page.url),
            )
            ref = (
                common.attached_ref(entity.ref, matched)
                if matched
                else common.unattached_ref("no corroborating identifier on the page")
            )
            origin_base = values.get("cin") or normalize_name(entity.name)
            retrieved = datetime.now(UTC).date()
            for name, fact in facts.items():
                inc = parse_human_date(fact.value) if name == "incorporation_date" else None
                await common.upsert_evidence(
                    ctx.session,
                    source,
                    case_id=case.id,
                    origin_key=f"registry:{origin_base}:{name}",
                    entity_ref=ref,
                    field_path=f"registry.{name}",
                    span=fact.span,
                    value=inc.isoformat() if inc else fact.value,
                    as_of=inc or retrieved,
                )
            if matched:
                attached_pages += 1
                for name, value in values.items():
                    learned.setdefault(name, value)
    finally:
        await common.close_quietly(llm)

    missing = failed_urls(urls, pages)
    if learned:
        inc = parse_human_date(learned.get("incorporation_date", ""))
        cin = (learned.get("cin") or "").strip().upper() or None
        common.update_entity(
            case,
            cin=cin if cin and common.CIN_PATTERN.match(cin) else None,
            legal_name=learned.get("legal_name"),
            incorporation_date=inc.isoformat() if inc else None,
            incorporation_place=learned.get("incorporation_place"),
        )
        await ctx.session.flush()
    ctx.result = f"{attached_pages} of {len(urls)} registry pages attached"
    return {"pages": len(urls), "attached": attached_pages, "failed": len(missing)}
