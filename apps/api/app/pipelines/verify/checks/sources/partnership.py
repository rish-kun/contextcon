"""Partnerships and named customers: the other party's own record first.

Two lookups at most (policy.MAX_LOOKUPS_PER_CLAIM):

1. The counterparty's own site: its partner directory, marketplace or newsroom
   (`"<company>" site:<partner domain>`) when the partner is a known platform, else
   `"<company>" "<counterparty>" <relationship>` with the counterparty's own pages
   recognised by host.
2. Press releases on either side: `"<company>" "<counterparty>" <relationship>`.

A page on the counterparty's site that names the company with a second identifier
is `counterparty_confirmation` (adequate: Supported). The company's own page is
`company_announcement`: it counts, but alone it caps the claim at partially
corroborated (`policy.SELF_STATEMENT_CAPPED`). Other pages are news, attached only
with a second identifier.

Only public terms go out: the confirmed company name, the counterparty named in the
claim's structured components (checked by `query.clean_entity`), fixed words.
"""

from __future__ import annotations

from app.domain.types import Claim
from app.pipelines.verify.checks.gather import CheckEnv, Gathered, Lookup, run_lookups
from app.rules.compare import normalize_text

# Platforms whose partner directories and newsrooms live on their own domain:
# (domain searched with `site:`, exact hosts whose pages are the platform's own
# record). Exact hosts only: forums and community Q&A on other subdomains carry
# user content and are read as ordinary pages.
PARTNER_SITES: dict[str, tuple[str, tuple[str, ...]]] = {
    "microsoft": (
        "microsoft.com",
        (
            "appsource.microsoft.com",
            "azuremarketplace.microsoft.com",
            "partner.microsoft.com",
            "news.microsoft.com",
        ),
    ),
    "azure": (
        "microsoft.com",
        ("appsource.microsoft.com", "azuremarketplace.microsoft.com", "partner.microsoft.com"),
    ),
    "qlik": ("qlik.com", ("qlik.com", "partners.qlik.com")),
    "qlikview": ("qlik.com", ("qlik.com", "partners.qlik.com")),
    "aws": ("aws.amazon.com", ("partners.amazonaws.com", "aws.amazon.com")),
    "amazon web services": ("aws.amazon.com", ("partners.amazonaws.com", "aws.amazon.com")),
    "google cloud": ("cloud.google.com", ("cloud.google.com",)),
    "salesforce": ("salesforce.com", ("appexchange.salesforce.com", "salesforce.com")),
    "sap": ("sap.com", ("partnerfinder.sap.com", "news.sap.com", "sap.com")),
    "oracle": ("oracle.com", ("partner-finder.oracle.com", "oracle.com")),
    "ibm": ("ibm.com", ("ibm.com", "newsroom.ibm.com")),
    "servicenow": ("servicenow.com", ("store.servicenow.com", "servicenow.com")),
    "snowflake": ("snowflake.com", ("snowflake.com",)),
    "databricks": ("databricks.com", ("databricks.com",)),
    "zebra": ("zebra.com", ("zebra.com", "partnerportal.zebra.com")),
    "honeywell": ("honeywell.com", ("honeywell.com",)),
}

# Relationship words a lookup may carry (all in query.LOOKUP_WORDS).
_RELATIONSHIP_WORDS: tuple[tuple[str, str], ...] = (
    ("oem", "oem partner"),
    ("reseller", "reseller"),
    ("alliance", "alliance"),
    ("customer", "customer"),
    ("client", "customer"),
)


def partner_sites(counterparty: str) -> tuple[str, tuple[str, ...]] | None:
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
    known = partner_sites(counterparty)
    hosts = known[1] if known else ()
    # A known platform's record is on its curated hosts only; otherwise a host whose
    # registrable name is the counterparty's ("tatasteel.com") is its own site.
    names = () if known else (counterparty,)
    focus = tuple(words.split())
    first = (
        Lookup(
            label=f"{counterparty} partner directory ({known[0]})",
            words="",
            site=known[0],
            party_hosts=hosts,
            party_names=names,
            focus=(counterparty, *focus),
        )
        if known
        else Lookup(
            label=f"{counterparty} announcements",
            words=words,
            entity=counterparty,
            party_names=names,
            focus=focus,
        )
    )
    second = Lookup(
        label=f"{counterparty} {words} press releases",
        words=f"{words} press release",
        entity=counterparty,
        party_hosts=hosts,
        party_names=names,
        focus=focus,
    )
    return [first, second]


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    await run_lookups(env, claim, plan(claim), out)
    return out
