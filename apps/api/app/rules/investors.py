"""Investor discovery: group dated funding records by investor and rank them.

- Only records with a date and a named (or identified) investor count.
- Records merge on investor id, or directly on a shared identifier (the same
  website domain), or on the exact normalised name plus a corroborating
  attribute (same domain, or same country and investor type) found on the SAME
  record as that name. A merge is refused when known identifiers conflict at
  the group level (a different domain anywhere in the group). Names that are
  merely similar are flagged as possible duplicates, never merged.
- Funding-kind compatibility reads only the dated rounds inside the disclosed
  scope (on or before the search date). It is "compatible" only when such a
  round of the kind sought exists; otherwise it is "unknown", never a negative
  verdict on incomplete evidence.
- score = Σ 0.5 ** (years since round / half-life) over comparable rounds in the
  lookback window. Ties: comparable count, then latest date, then name.
- The ranking describes past behaviour. It does not predict investment.
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.domain.enums import Compatibility, FundingKind
from app.domain.types import (
    ComparableRound,
    ExcludedRecord,
    FundingRecord,
    InvestorRanking,
    LatestInvestment,
    RankedInvestor,
    SearchScope,
)
from app.rules import policy
from app.rules.compare import normalize_text


def normalize_name(name: str) -> str:
    return normalize_text(name)


def stripped_name(name: str) -> str:
    """Name with common fund suffixes removed; used only to flag duplicates."""
    tokens = normalize_name(name).split()
    while tokens and tokens[-1] in policy.INVESTOR_NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _domain(d: str | None) -> str | None:
    if not d:
        return None
    d = re.sub(r"^https?://", "", d.strip().casefold())
    d = d.split("/")[0]
    return d.removeprefix("www.") or None


def funding_kind(round_type: str | None) -> FundingKind | None:
    if not round_type:
        return None
    rt = re.sub(r"[^a-z0-9]+", "_", round_type.casefold()).strip("_")
    if "grant" in rt:
        return FundingKind.GRANT
    if "debt" in rt or rt in {"loan", "venture_debt", "credit_facility"}:
        return FundingKind.DEBT
    if rt in {"private_equity", "growth", "growth_equity", "pre_ipo", "buyout", "pe"}:
        return FundingKind.GROWTH_EQUITY
    if rt in {"pre_seed", "seed", "angel", "venture"} or rt.startswith("series_"):
        return FundingKind.VENTURE_EQUITY
    return None


def _corroborates(a: FundingRecord, b: FundingRecord) -> bool:
    """A corroborating attribute shared by these two records themselves."""
    da, db = _domain(a.investor_domain), _domain(b.investor_domain)
    if da and db:
        return da == db
    return bool(
        a.investor_country
        and a.investor_type
        and normalize_text(a.investor_country) == normalize_text(b.investor_country or "")
        and normalize_text(a.investor_type) == normalize_text(b.investor_type or "")
    )


def _can_merge(r: FundingRecord, members: list[FundingRecord]) -> bool:
    """May record ``r`` (no investor id) join this group?"""
    domains = {d for d in (_domain(m.investor_domain) for m in members) if d}
    mine = _domain(r.investor_domain)
    if mine and domains:
        # A known identifier decides: the same domain merges directly, a
        # different one is a conflict that no name match can override.
        return mine in domains
    norm = normalize_name(r.investor_name or "")
    if not norm:
        return False
    # The name and the corroborating attribute must be on the same record.
    return any(
        normalize_name(m.investor_name or "") == norm and _corroborates(r, m) for m in members
    )


def _in_scope(r: FundingRecord, scope: SearchScope) -> bool:
    if r.date is None or r.date > scope.as_of:
        return False
    if (scope.as_of - r.date).days > scope.lookback_years * 365.25:
        return False
    if scope.sectors:
        wanted = [normalize_text(s) for s in scope.sectors]
        have = " ".join(normalize_text(s) for s in r.company_sectors)
        if not any(w and f" {w} " in f" {have} " for w in wanted):
            return False
    if scope.geographies and r.company_country:
        geos = {normalize_text(g) for g in scope.geographies}
        if normalize_text(r.company_country) not in geos:
            return False
    return True


def _scope_note(scope: SearchScope, rounds_seen: int) -> str:
    parts = [
        f"among {scope.companies_examined} comparable companies examined"
        if scope.companies_examined
        else "among the companies examined",
        f"sectors: {', '.join(scope.sectors) or 'any'}",
        f"geographies: {', '.join(scope.geographies) or 'any'}",
        f"rounds dated {scope.as_of.year - scope.lookback_years} to {scope.as_of.isoformat()}",
        f"{rounds_seen} dated rounds read",
    ]
    return "Latest comparable investment found " + "; ".join(parts)


def compatibility(
    in_scope: list[FundingRecord], sought: FundingKind | None
) -> tuple[Compatibility, str]:
    """Compatibility with the funding kind sought, from in-scope dated rounds only.

    Compatible only when such a round of the kind sought exists. Anything else
    (kind not stated, round types missing, only other kinds found) is unknown:
    the absence of a matching round in a bounded search is not evidence that
    the investor does not make that kind of investment.
    """
    if sought is None:
        return Compatibility.UNKNOWN, "funding kind sought not stated"
    matching = sorted(
        (m for m in in_scope if m.date is not None and funding_kind(m.round_type) is sought),
        key=lambda m: (m.date, m.id),
    )
    label = sought.value.replace("_", " ")
    if matching:
        n = len(matching)
        return (
            Compatibility.COMPATIBLE,
            f"{n} {label} round{'s' if n != 1 else ''} in the searched scope, "
            f"latest {matching[-1].date.isoformat()}",
        )
    kinds = sorted(
        {k.value.replace("_", " ") for m in in_scope if (k := funding_kind(m.round_type))}
    )
    if kinds:
        return (
            Compatibility.UNKNOWN,
            f"compatibility with {label} unknown: no {label} round found in the searched "
            f"scope (rounds found: {', '.join(kinds)})",
        )
    return (
        Compatibility.UNKNOWN,
        f"compatibility with {label} unknown: round types not recorded in the searched scope",
    )


def group_records(records: list[FundingRecord]) -> tuple[dict[str, list[FundingRecord]], dict]:
    """Return groups keyed by a stable key, plus each group's set of names."""
    ordered = sorted(records, key=lambda r: (r.investor_id is None, r.investor_id or "", r.id))
    groups: dict[str, list[FundingRecord]] = {}
    for r in ordered:
        if r.investor_id:
            groups.setdefault(f"id:{r.investor_id}", []).append(r)
            continue
        candidates = [key for key, members in groups.items() if _can_merge(r, members)]
        if len(candidates) == 1:
            groups[candidates[0]].append(r)
        else:
            groups[f"rec:{r.id}"] = [r]
    return groups, {
        k: sorted({normalize_name(m.investor_name) for m in v if m.investor_name})
        for k, v in groups.items()
    }


def rank_investors(
    records: list[FundingRecord],
    scope: SearchScope,
    sought: FundingKind | None = None,
) -> InvestorRanking:
    excluded: list[ExcludedRecord] = []
    usable: list[FundingRecord] = []
    for r in sorted(records, key=lambda r: r.id):
        if r.date is None:
            excluded.append(ExcludedRecord(record_id=r.id, reason="funding round has no date"))
        elif not r.investor_id and not (r.investor_name and r.investor_name.strip()):
            excluded.append(ExcludedRecord(record_id=r.id, reason="no named investor"))
        else:
            usable.append(r)

    groups, names = group_records(usable)

    # Flag possible duplicates: same exact or suffix-stripped name across groups.
    by_stripped: dict[str, set[str]] = defaultdict(set)
    for key, members in groups.items():
        for m in members:
            if m.investor_name:
                by_stripped[stripped_name(m.investor_name)].add(key)
    dupes: dict[str, set[str]] = defaultdict(set)
    for keys in by_stripped.values():
        if len(keys) > 1:
            for k in keys:
                dupes[k] |= keys - {k}

    ranked: list[RankedInvestor] = []
    for key, members in groups.items():
        comparable = sorted(
            (m for m in members if _in_scope(m, scope)),
            key=lambda m: (m.date, m.id),
        )
        if not comparable:
            continue
        score = sum(
            0.5
            ** (((scope.as_of - m.date).days / 365.25) / policy.INVESTOR_RECENCY_HALF_LIFE_YEARS)
            for m in comparable
        )
        latest = comparable[-1]
        display = next(
            (m.investor_name for m in sorted(members, key=lambda m: m.id) if m.investor_name),
            key,
        )
        investor_id = next((m.investor_id for m in members if m.investor_id), None)

        compat, why_compat = compatibility(comparable, sought)

        unknowns: list[str] = []
        if any(m.amount_usd is None for m in comparable):
            unknowns.append("Cheque size unknown for some rounds")
        if any(m.round_type is None for m in comparable):
            unknowns.append("Round type unknown for some rounds")
        if dupes.get(key):
            unknowns.append("May be the same investor as another entry; not merged")

        sectors = sorted({s for m in comparable for s in m.company_sectors})
        companies = sorted({m.company_name for m in comparable})
        why = (
            f"{len(comparable)} comparable investment{'s' if len(comparable) != 1 else ''} "
            f"({', '.join(companies)}) in {', '.join(sectors) or 'the sector'}; "
            f"latest {latest.date.isoformat()}"
        )
        ranked.append(
            RankedInvestor(
                key=key,
                investor_id=investor_id,
                name=display,
                aliases=[n for n in names[key] if n != normalize_name(display)],
                comparable_rounds=[
                    ComparableRound(
                        record_id=m.id,
                        company_id=m.company_id,
                        company_name=m.company_name,
                        round_type=m.round_type,
                        date=m.date,
                        amount_usd=m.amount_usd,
                        evidence_id=m.evidence_id,
                    )
                    for m in comparable
                ],
                comparable_count=len(comparable),
                score=round(score, 4),
                latest_sector_investment=LatestInvestment(
                    date=latest.date,
                    company_name=latest.company_name,
                    round_type=latest.round_type,
                    evidence_id=latest.evidence_id,
                    scope_note=_scope_note(scope, len(usable)),
                ),
                funding_kind=sought,
                compatibility=compat,
                compatibility_reason=why_compat,
                possible_duplicates=sorted(dupes.get(key, set())),
                why=why,
                unknowns=unknowns,
            )
        )

    ranked.sort(
        key=lambda i: (
            -i.score,
            -i.comparable_count,
            -i.latest_sector_investment.date.toordinal(),
            normalize_name(i.name),
            i.key,
        )
    )
    return InvestorRanking(scope=scope, investors=ranked, excluded_records=excluded)
