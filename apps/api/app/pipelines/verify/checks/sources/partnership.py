"""Partnerships and named customers: the other party's own record first.

Two lookups at most (policy.MAX_LOOKUPS_PER_CLAIM):

1. The counterparty's own site: its partner finder or newsroom
   (`"<company>" site:<partner domain>`) when the partner is a known platform, else
   `"<company>" "<counterparty>" <relationship>`.
2. Press releases on either side: `"<company>" "<counterparty>" <relationship>`.

A page on the platform's own curated hosts (`PartnerSite.record_hosts`, exact
hosts) that names the company with a second identifier is
`counterparty_confirmation` (adequate: Supported). Marketplace listings the company
writes itself are `company_announcement`. For other counterparties no host is
trusted by name alone (a lookalike domain is cheap), so their pages are news.
The company's own page is `company_announcement`: it counts, but alone it caps the
claim at partially corroborated (`policy.SELF_STATEMENT_CAPPED`). Other pages are
news, attached only with a second identifier.

Only public terms go out: the confirmed company name, the counterparty named in the
claim's structured components (checked by `query.clean_entity`), fixed words.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.types import Claim
from app.pipelines.verify.checks.gather import CheckEnv, Gathered, Lookup, run_lookups
from app.rules.compare import normalize_text


@dataclass(frozen=True)
class PartnerSite:
    """A platform's own web presence.

    `search`: the domain searched with `site:`. `record_hosts`: exact hosts whose pages
    the platform itself publishes (partner finder, newsroom): the counterparty's record.
    `listing_hosts`: marketplaces where the company writes its own listing: classed
    company_announcement, so they never make a claim Supported on their own.
    Forum and community subdomains are in neither and read as ordinary pages.
    """

    search: str
    record_hosts: tuple[str, ...]
    listing_hosts: tuple[str, ...] = ()


_MICROSOFT = PartnerSite(
    "microsoft.com",
    ("partner.microsoft.com", "news.microsoft.com"),
    ("appsource.microsoft.com", "azuremarketplace.microsoft.com", "marketplace.microsoft.com"),
)
_QLIK = PartnerSite("qlik.com", ("qlik.com", "partners.qlik.com"))
_AWS = PartnerSite("aws.amazon.com", ("partners.amazonaws.com",), ("aws.amazon.com",))
_SALESFORCE = PartnerSite("salesforce.com", ("salesforce.com",), ("appexchange.salesforce.com",))

# Keyed by a normalised name the counterparty contains.
PARTNER_SITES: dict[str, PartnerSite] = {
    "microsoft": _MICROSOFT,
    "azure": _MICROSOFT,
    "qlik": _QLIK,
    "qlikview": _QLIK,
    "aws": _AWS,
    "amazon web services": _AWS,
    "google cloud": PartnerSite("cloud.google.com", ("cloud.google.com",)),
    "salesforce": _SALESFORCE,
    "tableau": PartnerSite("tableau.com", ("tableau.com",)),
    "sap": PartnerSite("sap.com", ("partnerfinder.sap.com", "news.sap.com")),
    "oracle": PartnerSite("oracle.com", ("partner-finder.oracle.com",)),
    "ibm": PartnerSite("ibm.com", ("newsroom.ibm.com",)),
    "servicenow": PartnerSite("servicenow.com", ("servicenow.com",), ("store.servicenow.com",)),
    "snowflake": PartnerSite("snowflake.com", ("snowflake.com",)),
    "databricks": PartnerSite("databricks.com", ("databricks.com",)),
    "zebra": PartnerSite("zebra.com", ("zebra.com", "partnerportal.zebra.com")),
    "honeywell": PartnerSite("honeywell.com", ("honeywell.com",)),
}

# Relationship words a lookup may carry (all in query.LOOKUP_WORDS).
_RELATIONSHIP_WORDS: tuple[tuple[str, str], ...] = (
    ("oem", "oem partner"),
    ("reseller", "reseller"),
    ("alliance", "alliance"),
    ("customer", "customer"),
    ("client", "customer"),
)


def partner_sites(counterparty: str) -> PartnerSite | None:
    text = f" {normalize_text(counterparty)} "
    keys = sorted((k for k in PARTNER_SITES if f" {k} " in text), key=len, reverse=True)
    return PARTNER_SITES[keys[0]] if keys else None


def relationship_words(claim: Claim) -> str:
    comps = {c.name: str(c.value) for c in claim.components}
    text = normalize_text(comps.get("relationship", ""))
    for word, words in _RELATIONSHIP_WORDS:
        if word in text.split():
            return words
    return "partner"


def plan(claim: Claim) -> list[Lookup]:
    comps = {c.name: str(c.value) for c in claim.components}
    counterparty = comps.get("counterparty")
    words = relationship_words(claim)
    if not counterparty:
        return [Lookup(label="the company's partner announcements", words=words)]
    site = partner_sites(counterparty)
    record = site.record_hosts if site else ()
    listing = site.listing_hosts if site else ()
    focus = tuple(words.split())
    first = (
        Lookup(
            label=f"{counterparty} partner directory ({site.search})",
            words="",
            site=site.search,
            party_hosts=record,
            listing_hosts=listing,
            focus=(counterparty, *focus),
        )
        if site
        else Lookup(
            label=f"{counterparty} announcements",
            words=words,
            entity=counterparty,
            focus=focus,
        )
    )
    second = Lookup(
        label=f"{counterparty} {words} press releases",
        words=f"{words} press release",
        entity=counterparty,
        party_hosts=record,
        listing_hosts=listing,
        focus=focus,
    )
    return [first, second]


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    await run_lookups(env, claim, plan(claim), out)
    return out
