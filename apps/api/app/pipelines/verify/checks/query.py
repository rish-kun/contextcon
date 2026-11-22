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


def assert_public(query: str, terms: PublicTerms, *, city: str | None = None) -> None:
    allowed = terms.allowed_tokens(city)
    extra = [t for t in _TOKEN.findall(query) if t.casefold() not in allowed]
    if extra:
        raise UnsafeQuery("query contains terms that are not public lookup terms")
