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

# Platforms whose partner directories and newsrooms live on their own domain.
# Keyed by a normalised name the counterparty contains; first host is searched.
PARTNER_SITES: dict[str, tuple[str, ...]] = {
    "microsoft": ("microsoft.com",),
    "azure": ("microsoft.com",),
    "qlik": ("qlik.com",),
    "qlikview": ("qlik.com",),
    "aws": ("amazon.com",),
    "amazon web services": ("amazon.com",),
    "google cloud": ("google.com",),
    "salesforce": ("salesforce.com",),
    "tableau": ("tableau.com", "salesforce.com"),
    "sap": ("sap.com",),
    "oracle": ("oracle.com",),
    "ibm": ("ibm.com",),
    "servicenow": ("servicenow.com",),
    "snowflake": ("snowflake.com",),
    "databricks": ("databricks.com",),
    "zebra": ("zebra.com",),
    "honeywell": ("honeywell.com",),
}

# Relationship words a lookup may carry (all in query.LOOKUP_WORDS).
_RELATIONSHIP_WORDS: tuple[tuple[str, str], ...] = (
    ("oem", "oem partner"),
    ("reseller", "reseller"),
    ("alliance", "alliance"),
    ("customer", "customer"),
    ("client", "customer"),
)


def partner_sites(counterparty: str) -> tuple[str, ...]:
    text = f" {normalize_text(counterparty)} "
    keys = sorted((k for k in PARTNER_SITES if f" {k} " in text), key=len, reverse=True)
    return PARTNER_SITES[keys[0]] if keys else ()


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
    hosts = partner_sites(counterparty)
    focus = tuple(words.split())
    first = (
        Lookup(
            label=f"{counterparty} partner directory ({hosts[0]})",
            words="",
            site=hosts[0],
            party_hosts=hosts,
            party_names=(counterparty,),
            focus=(counterparty, *focus),
        )
        if hosts
        else Lookup(
            label=f"{counterparty} announcements",
            words=words,
            entity=counterparty,
            party_names=(counterparty,),
            focus=focus,
        )
    )
    second = Lookup(
        label=f"{counterparty} {words} press releases",
        words=f"{words} press release",
        entity=counterparty,
        party_hosts=hosts,
        party_names=(counterparty,),
        focus=focus,
    )
    return [first, second]


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    await run_lookups(env, claim, plan(claim), out)
    return out
