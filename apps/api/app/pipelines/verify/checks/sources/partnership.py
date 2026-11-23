"""Partnerships and named customers: the other party's own record first.

Two lookups at most (policy.MAX_LOOKUPS_PER_CLAIM):

1. The counterparty's own site: its partner finder or newsroom
   (`"<company>" site:<partner domain>`) when the partner is a known platform.
2. Press releases: `"<company>" "<platform>" <relationship> press release`.

A counterparty that is not a curated platform is never sent anywhere (it may be a
private customer or a deal code name): its lookup is listed as not run
(`private_counterparty`) and the company's own releases are searched instead.

A page on the platform's own curated hosts (`PartnerSite.record_hosts`, exact
hosts) that names the company with a second identifier is
`counterparty_confirmation` (adequate: Supported). Marketplace listings the company
writes itself are `company_announcement`. No host is trusted by name resemblance
(a lookalike domain is cheap).
The company's own page is `company_announcement`: it counts, but alone it caps the
claim at partially corroborated (`policy.SELF_STATEMENT_CAPPED`). Other pages are
news, attached only with a second identifier.

Only public terms go out: the confirmed company name, a curated platform's public
name (`PartnerSite.name`, never the claim's spelling), fixed words.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.types import Claim
from app.pipelines.verify.checks.gather import CheckEnv, Gathered, Lookup, run_lookups
from app.rules.compare import normalize_text


@dataclass(frozen=True)
class PartnerSite:
    """A platform's own web presence, from this curated table only.

    `name`: the platform's public name, the only counterparty name a lookup sends.
    `search`: the domain searched with `site:`. `record_hosts`: exact hosts whose pages
    the platform itself publishes (partner finder, newsroom): the counterparty's record.
    `listing_hosts`: marketplaces where the company writes its own listing: classed
    company_announcement, so they never make a claim Supported on their own.
    Forum and community subdomains are in neither and read as ordinary pages.
    """

    name: str
    search: str
    record_hosts: tuple[str, ...]
    listing_hosts: tuple[str, ...] = ()


_MICROSOFT = PartnerSite(
    "Microsoft",
    "microsoft.com",
    ("partner.microsoft.com", "news.microsoft.com"),
    ("appsource.microsoft.com", "azuremarketplace.microsoft.com", "marketplace.microsoft.com"),
)
_QLIK = PartnerSite("Qlik", "qlik.com", ("qlik.com", "partners.qlik.com"))
_AWS = PartnerSite("AWS", "aws.amazon.com", ("partners.amazonaws.com",), ("aws.amazon.com",))
_SALESFORCE = PartnerSite(
    "Salesforce", "salesforce.com", ("salesforce.com",), ("appexchange.salesforce.com",)
)

# Keyed by a normalised name the counterparty contains.
PARTNER_SITES: dict[str, PartnerSite] = {
    "microsoft": _MICROSOFT,
    "azure": _MICROSOFT,
    "qlik": _QLIK,
    "qlikview": _QLIK,
    "aws": _AWS,
    "amazon web services": _AWS,
    "google cloud": PartnerSite("Google Cloud", "cloud.google.com", ("cloud.google.com",)),
    "salesforce": _SALESFORCE,
    "tableau": PartnerSite("Tableau", "tableau.com", ("tableau.com",)),
    "sap": PartnerSite("SAP", "sap.com", ("partnerfinder.sap.com", "news.sap.com")),
    "oracle": PartnerSite("Oracle", "oracle.com", ("partner-finder.oracle.com",)),
    "ibm": PartnerSite("IBM", "ibm.com", ("newsroom.ibm.com",)),
    "servicenow": PartnerSite(
        "ServiceNow", "servicenow.com", ("servicenow.com",), ("store.servicenow.com",)
    ),
    "snowflake": PartnerSite("Snowflake", "snowflake.com", ("snowflake.com",)),
    "databricks": PartnerSite("Databricks", "databricks.com", ("databricks.com",)),
    "zebra": PartnerSite("Zebra", "zebra.com", ("zebra.com", "partnerportal.zebra.com")),
    "honeywell": PartnerSite("Honeywell", "honeywell.com", ("honeywell.com",)),
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
    """Two lookups at most. Only a curated platform's public name is ever sent; a
    counterparty that is not in `PARTNER_SITES` has no public provenance (it may be a
    private customer or a code name), so its own lookup is listed as not run
    ("private_counterparty") and the second searches the company's own releases with
    fixed words only. Labels carry the curated name or fixed words, never the claim's."""
    comps = {c.name: str(c.value) for c in claim.components}
    counterparty = comps.get("counterparty")
    words = relationship_words(claim)
    releases = Lookup(label=f"the company's {words} announcements", words=f"{words} press release")
    if not counterparty:
        return [releases]
    site = partner_sites(counterparty)
    if site is None:
        return [
            Lookup(label="the counterparty's own pages", words=words, skip="private_counterparty"),
            releases,
        ]
    focus = tuple(words.split())
    return [
        Lookup(
            label=f"{site.name} partner directory ({site.search})",
            words="",
            site=site.search,
            party_hosts=site.record_hosts,
            listing_hosts=site.listing_hosts,
            focus=(site.name, *focus),
        ),
        Lookup(
            label=f"{site.name} {words} press releases",
            words=f"{words} press release",
            entity=site.name,
            party_hosts=site.record_hosts,
            listing_hosts=site.listing_hosts,
            focus=(site.name, *focus),
        ),
    ]


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    await run_lookups(env, claim, plan(claim), out)
    return out
