"""Web search queries from public lookup terms only (spec §7).

A query is built from a `PublicTerms` value (the company's name and domain as the
public profile records them, and optionally a city) plus one topic word from a
fixed allowlist. There is deliberately no way to pass claim text in: confidential
wording from a seller's deck never reaches a search provider. `assert_public` is a
last check on the finished query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOPICS: dict[str, str] = {
    "funding": "funding",
    "facility": "facility",
    "warehouse": "warehouse",
    "launch": "launch",
    "expansion": "expansion",
    "office": "office",
    "plant": "plant",
    "hub": "hub",
    "acquisition": "acquisition",
    "partnership": "partnership",
    # Listed-company financials: fixed words only, never the claim's wording.
    "results": "quarterly results revenue",
}

_CITY = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,39}$")
_TOKEN = re.compile(r"[\w.'-]+", re.UNICODE)


class UnsafeQuery(ValueError):
    """A query would carry something other than public lookup terms."""


@dataclass(frozen=True)
class PublicTerms:
    company_name: str
    domain: str | None = None

    def allowed_tokens(self, city: str | None = None) -> set[str]:
        parts = [self.company_name, self.domain or "", city or "", *TOPICS.values()]
        return {t.casefold() for p in parts for t in _TOKEN.findall(p)}


def clean_city(city: str | None) -> str | None:
    """A city is a short place name; anything else is not a lookup term."""
    if not city:
        return None
    city = " ".join(city.split()).strip(" ,.")
    if not _CITY.match(city) or len(city.split()) > 3:
        return None
    return city


def build_query(terms: PublicTerms, topic: str, *, city: str | None = None) -> str:
    if topic not in TOPICS:
        raise UnsafeQuery(f"topic {topic!r} is not on the allowlist")
    name = " ".join(terms.company_name.split())
    if not name:
        raise UnsafeQuery("no company name")
    parts = [f'"{name}"', TOPICS[topic]]
    place = clean_city(city)
    if place:
        parts.append(place)
    query = " ".join(parts)
    assert_public(query, terms, city=place)
    return query


def assert_public(
    query: str,
    terms: PublicTerms,
    *,
    city: str | None = None,
    extra_terms: tuple[str, ...] = (),
) -> None:
    allowed = terms.allowed_tokens(city)
    allowed |= {t.casefold() for p in extra_terms for t in _TOKEN.findall(p)}
    extra = [t for t in _TOKEN.findall(query) if t.casefold() not in allowed]
    if extra:
        raise UnsafeQuery("query contains terms that are not public lookup terms")


# --- Targeted lookups (claim-category source modules, since policy 2026-11-22.6) ---
#
# A targeted lookup may also carry ONE named public entity from the claim's
# structured components (the partner, certifier or trademark), never the claim's
# wording, plus fixed words from `LOOKUP_WORDS` and an optional `site:` host.

LOOKUP_WORDS: frozenset[str] = frozenset(
    {
        "partner",
        "partners",
        "partnership",
        "oem",
        "reseller",
        "alliance",
        "customer",
        "customers",
        "client",
        "clients",
        "case study",
        "certified",
        "certification",
        "certificate",
        "iso",
        "trademark",
        "registered",
        "owner",
        "press release",
    }
)
_ENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &.+/:'-]{0,59}$")
_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def clean_entity(value: str | None, *, deny: tuple[str, ...] = ()) -> str | None:
    """A short public organisation, standard or mark name, or None.

    Refused: anything long or with sentence punctuation (that is seller wording), and
    anything sharing a word with `deny` (the name and website typed for the case,
    which may be a deal code name)."""
    if not value:
        return None
    name = " ".join(str(value).split()).strip(" ,.;")
    if not _ENTITY.match(name) or len(name.split()) > 6:
        return None
    words = {t.casefold() for t in _TOKEN.findall(name)}
    denied = {t.casefold() for d in deny for t in _TOKEN.findall(d or "") if len(t) > 2}
    if words & denied:
        return None
    return name


def build_lookup(
    terms: PublicTerms,
    words: str,
    *,
    entity: str | None = None,
    site: str | None = None,
    deny: tuple[str, ...] = (),
    quote_entity: bool = True,
) -> str:
    """`"<company>" ["<entity>"] <words> [site:<host>]`, public terms only. A
    standard's name goes unquoted (`quote_entity=False`): "ISO 27001" as a phrase
    would miss "ISO/IEC 27001"."""
    name = " ".join(terms.company_name.split())
    if not name:
        raise UnsafeQuery("no company name")
    allowed_words = {t for w in LOOKUP_WORDS for t in w.split()}
    if words and not set(words.split()) <= allowed_words:
        raise UnsafeQuery(f"lookup words {words!r} are not on the allowlist")
    parts = [f'"{name}"']
    extra: list[str] = list(LOOKUP_WORDS)
    if entity is not None:
        clean = clean_entity(entity, deny=deny)
        if clean is None:
            raise UnsafeQuery("the named entity is not a short public name")
        if clean.casefold() != name.casefold():
            parts.append(f'"{clean}"' if quote_entity else clean)
            extra.append(clean)
    if words:
        parts.append(words)
    if site:
        host = site.casefold().removeprefix("www.")
        if not _HOST.match(host):
            raise UnsafeQuery("site is not a host name")
        parts.append(f"site:{host}")
        extra += ["site", host]
    query = " ".join(parts)
    assert_public(query, terms, extra_terms=tuple(extra))
    return query
