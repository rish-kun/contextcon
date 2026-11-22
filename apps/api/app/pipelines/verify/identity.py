"""`verify.identity`: which company is this? (PRD principle 4, design §5.4, §6.3 step 1)

`company_identify` (0.2 credits per matched identifier) runs by domain first, then by
name. A candidate is **confirmed** only when a corroborating identifier matches what
the case was opened with: domain, Crustdata id, profile URL, HQ city, founded year or
registry id. A name match alone never confirms.

- one corroborated candidate (and the name lookup does not point elsewhere) → `confirmed`
- two or more corroborated candidates (e.g. a group domain), or several plausible
  name-only candidates → `ambiguous`
- no candidate, a single name-only candidate, or domain and name pointing at different
  companies → `unresolved`

Candidates are stored with the identifiers that matched and differed, so the UI can
show the evidence behind a manual pick (`POST /cases/{id}/identity`). Identity-dependent
steps (profile, registry, events, comparables) are appended only once identity is
confirmed; until then they do not exist and dependent checks read as not checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.crustdata_models import IdentifyResult
from app.db.enums import IdentityStatus
from app.db.models import Case
from app.domain.enums import SourceReliability
from app.jobs import StepContext, StepSpec, step_handler
from app.pipelines.verify import common
from app.pipelines.verify.common import (
    COMPARABLES,
    EVENTS,
    IDENTITY,
    PROFILE,
    REGISTRY,
    normalize_domain,
    normalize_name,
    normalize_url,
)
from app.pipelines.verify.tail import ensure_assessment_tail

# A candidate's primary domain is compared exactly; its secondary domains (all_domains)
# also corroborate, but a group domain shared as primary by several records is ambiguous.
# Name-only matches below this confidence are not plausible candidates.
PLAUSIBLE_NAME_CONFIDENCE = 0.5
MAX_CANDIDATES = 6

KEY_LABELS = {
    "crustdata_company_id": "Crustdata id",
    "domain": "Domain",
    "profile_url": "Profile URL",
    "hq_city": "HQ city",
    "founded_year": "Founded year",
    "cin": "Registry id (CIN)",
    "name": "Name",
    "domain_claimed": "Domain (claimed on the record; the domain lookup did not return it)",
}
CORROBORATING_KEYS = ("crustdata_company_id", "domain", "profile_url", "hq_city", "founded_year")


@dataclass
class Expected:
    """What the case was opened with. `name` is shown but never corroborates."""

    name: str | None = None
    domain: str | None = None
    crustdata_company_id: int | None = None
    profile_url: str | None = None
    hq_city: str | None = None
    founded_year: int | None = None

    @classmethod
    def of(cls, case: Case) -> Expected:
        data = dict((case.identity_identifiers or {}).get("expected") or {})
        return cls(
            name=data.get("name") or case.company_name,
            domain=normalize_domain(data.get("domain") or case.website),
            crustdata_company_id=data.get("crustdata_company_id"),
            profile_url=data.get("profile_url"),
            hq_city=data.get("hq_city"),
            founded_year=data.get("founded_year"),
        )


@dataclass
class Candidate:
    crustdata_company_id: int
    name: str
    primary_domain: str | None = None
    domains: list[str] = field(default_factory=list)
    profile_url: str | None = None
    founded_year: int | None = None
    description: str | None = None
    industries: list[str] = field(default_factory=list)
    confidence_score: float | None = None
    found_by: list[str] = field(default_factory=list)
    matching: list[dict[str, Any]] = field(default_factory=list)
    differing: list[dict[str, Any]] = field(default_factory=list)

    @property
    def matched_keys(self) -> list[str]:
        return [k["key"] for k in self.matching if k["key"] in CORROBORATING_KEYS]

    def as_json(self) -> dict[str, Any]:
        return {
            "crustdata_company_id": self.crustdata_company_id,
            "name": self.name,
            "primary_domain": self.primary_domain,
            "domains": self.domains,
            "profile_url": self.profile_url,
            "founded_year": self.founded_year,
            "description": self.description,
            "industries": self.industries,
            "confidence_score": self.confidence_score,
            "found_by": self.found_by,
            "matching": self.matching,
            "differing": self.differing,
        }


@dataclass
class IdentityDecision:
    state: IdentityStatus
    chosen: Candidate | None
    candidates: list[Candidate]
    note: str


def _candidates(results: list[IdentifyResult], found_by: str) -> list[Candidate]:
    out: list[Candidate] = []
    for result in results:
        for match in result.matches:
            data = match.company_data
            info = data.basic_info
            cid = data.crustdata_company_id or (info.crustdata_company_id if info else None)
            if cid is None or info is None:
                continue
            raw_domains = [info.primary_domain, *(info.all_domains or [])]
            domains = [normalize_domain(d) for d in raw_domains]
            website = normalize_domain(info.website)
            if website:
                domains.append(website)
            out.append(
                Candidate(
                    crustdata_company_id=int(cid),
                    name=info.name or "",
                    primary_domain=normalize_domain(info.primary_domain) or website,
                    domains=[d for d in dict.fromkeys(domains) if d],
                    profile_url=info.professional_network_url,
                    founded_year=info.year_founded,
                    description=info.description,
                    industries=list(info.industries or []),
                    confidence_score=match.confidence_score,
                    found_by=[found_by],
                )
            )
    return out


def _key(key: str, value: Any, expected: Any = None) -> dict[str, Any]:
    item = {"key": key, "label": KEY_LABELS[key], "value": str(value)}
    if expected is not None:
        item["expected"] = str(expected)
    return item


def _compare(candidate: Candidate, expected: Expected) -> None:
    matching: list[dict[str, Any]] = []
    differing: list[dict[str, Any]] = []

    def check(key: str, given: Any, have: Any, same: bool) -> None:
        if given is None or given == "":
            return
        if same:
            matching.append(_key(key, have))
        elif have not in (None, "", []):
            differing.append(_key(key, have, given))

    check(
        "crustdata_company_id",
        expected.crustdata_company_id,
        candidate.crustdata_company_id,
        expected.crustdata_company_id == candidate.crustdata_company_id,
    )
    check(
        "domain",
        expected.domain,
        candidate.primary_domain or (candidate.domains[0] if candidate.domains else None),
        expected.domain in candidate.domains,
    )
    if expected.domain in candidate.domains and candidate.primary_domain != expected.domain:
        matching[-1]["value"] = expected.domain
    check(
        "profile_url",
        expected.profile_url,
        candidate.profile_url,
        bool(candidate.profile_url)
        and normalize_url(expected.profile_url) == normalize_url(candidate.profile_url),
    )
    check(
        "founded_year",
        expected.founded_year,
        candidate.founded_year,
        expected.founded_year is not None and expected.founded_year == candidate.founded_year,
    )
    # The name is shown next to the identifiers but is never corroboration on its own.
    if expected.name and candidate.name:
        if normalize_name(expected.name) == normalize_name(candidate.name):
            matching.append(_key("name", candidate.name))
        else:
            differing.append(_key("name", candidate.name, expected.name))
    candidate.matching, candidate.differing = matching, differing


def _merge(groups: list[list[Candidate]]) -> list[Candidate]:
    merged: dict[int, Candidate] = {}
    for group in groups:
        for c in group:
            seen = merged.get(c.crustdata_company_id)
            if seen is None:
                merged[c.crustdata_company_id] = c
                continue
            seen.found_by = list(dict.fromkeys(seen.found_by + c.found_by))
            if (c.confidence_score or 0) > (seen.confidence_score or 0):
                seen.confidence_score = c.confidence_score
    return list(merged.values())


def _demote_domain_claimers(candidates: list[Candidate]) -> None:
    """The domain lookup is the authority on which record owns a domain. When it
    returned a matching record, a record found only by name that also claims the
    domain is a possible duplicate, not a second corroborated candidate."""
    owners = [c for c in candidates if "domain" in c.found_by and "domain" in c.matched_keys]
    if not owners:
        return
    for c in candidates:
        if "domain" in c.found_by:
            continue
        for item in c.matching:
            if item["key"] == "domain":
                item["key"], item["label"] = "domain_claimed", KEY_LABELS["domain_claimed"]


def _plausible(c: Candidate) -> bool:
    if c.matched_keys or "domain" in c.found_by:
        return True
    return c.confidence_score is None or c.confidence_score >= PLAUSIBLE_NAME_CONFIDENCE


def decide_identity(
    expected: Expected,
    by_domain: list[IdentifyResult],
    by_name: list[IdentifyResult],
) -> IdentityDecision:
    """Pure decision over identify results. No I/O; unit-tested directly."""
    domain_cands = _candidates(by_domain, "domain")
    name_cands = _candidates(by_name, "name")
    candidates = _merge([domain_cands, name_cands])
    for c in candidates:
        _compare(c, expected)
    _demote_domain_claimers(candidates)
    candidates = [c for c in candidates if _plausible(c)]
    candidates.sort(key=lambda c: (-len(c.matched_keys), -(c.confidence_score or 0)))
    candidates = candidates[:MAX_CANDIDATES]
    corroborated = [c for c in candidates if c.matched_keys]
    claimers = [c for c in candidates if any(k["key"] == "domain_claimed" for k in c.matching)]
    name_ids = {c.crustdata_company_id for c in name_cands}

    pinned = [c for c in corroborated if "crustdata_company_id" in c.matched_keys]
    if len(pinned) == 1:
        chosen = pinned[0]
        if any(k["key"] == "domain" for k in chosen.differing):
            return IdentityDecision(
                IdentityStatus.UNRESOLVED,
                None,
                candidates,
                "The Crustdata id and the website point at different companies.",
            )
        return IdentityDecision(
            IdentityStatus.CONFIRMED, chosen, candidates, _confirmed_note(chosen)
        )
    primary_note = ""
    if len(corroborated) >= 2 and expected.domain:
        # Several records list the domain, but only one has it as its primary domain
        # (the others list it as a secondary domain): the primary domain distinguishes.
        primary = [c for c in corroborated if c.primary_domain == expected.domain]
        if len(primary) == 1 and set(primary[0].matched_keys) >= {
            k for c in corroborated for k in c.matched_keys
        }:
            primary_note = (
                f" {len(corroborated) - 1} other record(s) list {expected.domain} only as a "
                "secondary domain."
            )
            corroborated = primary
    if len(corroborated) == 1:
        chosen = corroborated[0]
        if name_ids and chosen.crustdata_company_id not in name_ids:
            return IdentityDecision(
                IdentityStatus.UNRESOLVED,
                None,
                candidates,
                "The domain and the name point at different companies; pick one.",
            )
        return IdentityDecision(
            IdentityStatus.CONFIRMED,
            chosen,
            candidates,
            _confirmed_note(chosen) + primary_note + _claimers_note(claimers, expected),
        )
    if len(corroborated) >= 2:
        return IdentityDecision(
            IdentityStatus.AMBIGUOUS,
            None,
            candidates,
            f"{len(corroborated)} companies share the identifiers given "
            f"({', '.join(sorted({k for c in corroborated for k in c.matched_keys}))}); pick one.",
        )
    if len(candidates) >= 2:
        return IdentityDecision(
            IdentityStatus.AMBIGUOUS,
            None,
            candidates,
            f"{len(candidates)} companies match the name, none on a corroborating identifier.",
        )
    if candidates:
        return IdentityDecision(
            IdentityStatus.UNRESOLVED,
            None,
            candidates,
            "Only the name matches; a name alone does not confirm identity.",
        )
    return IdentityDecision(IdentityStatus.UNRESOLVED, None, [], "No matching company found.")


def _claimers_note(claimers: list[Candidate], expected: Expected) -> str:
    if not claimers:
        return ""
    names = ", ".join(f"{c.name} ({c.crustdata_company_id})" for c in claimers)
    return (
        f" Possible duplicate kept separate: {names} lists {expected.domain} on its record, "
        "but the domain lookup did not return it."
    )


def _confirmed_note(c: Candidate) -> str:
    labels = ", ".join(KEY_LABELS[k].lower() for k in c.matched_keys)
    return f"Confirmed on {labels}."


def dependent_steps() -> list[StepSpec]:
    """Steps that need a confirmed identity. Appended by the identity step when it
    confirms, or by a manual pick."""
    return [
        StepSpec(PROFILE, PROFILE, label="Build the company profile", depends_on=[IDENTITY]),
        StepSpec(REGISTRY, REGISTRY, label="Look for registry records", depends_on=[PROFILE]),
        StepSpec(EVENTS, EVENTS, label="Gather dated events", depends_on=[PROFILE]),
        StepSpec(COMPARABLES, COMPARABLES, label="Find comparable companies", depends_on=[PROFILE]),
    ]


def apply_confirmation(
    case: Case,
    chosen: dict[str, Any],
    *,
    keys: list[dict[str, Any]],
    basis: str,
    note: str,
    pick: dict[str, Any] | None = None,
) -> None:
    """Mark the case confirmed on `chosen` (a stored candidate dict)."""
    identifiers = dict(case.identity_identifiers or {})
    identifiers.update(
        {
            "basis": basis,
            "keys": keys,
            "note": note,
            "confirmed_at": datetime.now(UTC).isoformat(),
            "entity": {
                **dict(identifiers.get("entity") or {}),
                "name": chosen.get("name"),
                "domains": chosen.get("domains") or [],
                "profile_url": chosen.get("profile_url"),
                "founded_year": chosen.get("founded_year"),
            },
        }
    )
    if pick is not None:
        identifiers["pick"] = pick
    case.identity_identifiers = identifiers
    case.identity_status = IdentityStatus.CONFIRMED
    case.crustdata_company_id = str(chosen["crustdata_company_id"])


IDENTIFY_ENDPOINT = "/company/identify"


def identify_request(kind: str, value: str) -> dict[str, Any]:
    return {kind: [value]}


async def _identify(
    ctx: StepContext, client: Any, case: Case, kind: str, value: str
) -> list[IdentifyResult]:
    await ctx.require_budget(0.2)
    results, _ = await client.identify_company(**{kind: [value]})
    await common.get_or_create_source(
        ctx,
        case,
        provider="crustdata",
        endpoint_or_url=IDENTIFY_ENDPOINT,
        source_class=SourceReliability.DATA_PROVIDER,
        request=identify_request(kind, value),
        title=f"Company identify by {kind[:-1]}",
    )
    return results


async def record_key_evidence(
    session: AsyncSession, case: Case, candidate: dict[str, Any], *, basis: str
) -> list[dict[str, Any]]:
    """Evidence rows for the identifiers that matched `candidate` (a stored candidate
    dict), on the identify call that found it. Returns the keys with evidence ids."""
    expected = Expected.of(case)
    lookups = []
    if "domain" in candidate.get("found_by", []) and expected.domain:
        lookups.append(identify_request("domains", expected.domain))
    if "name" in candidate.get("found_by", []) and expected.name:
        lookups.append(identify_request("names", expected.name))
    source = None
    for request in lookups:
        source = await common.find_source(
            session,
            case,
            provider="crustdata",
            endpoint_or_url=IDENTIFY_ENDPOINT,
            source_class=SourceReliability.DATA_PROVIDER,
            request=request,
        )
        if source is not None:
            break
    cid = candidate["crustdata_company_id"]
    matched = [k["key"] for k in candidate.get("matching", []) if k["key"] in CORROBORATING_KEYS]
    ref_keys = matched if basis == "auto" else ["manual_pick", *matched]
    keys: list[dict[str, Any]] = []
    for item in candidate.get("matching", []):
        if item["key"] not in CORROBORATING_KEYS:
            continue
        evidence_ids: list[str] = []
        if source is not None:
            evidence_id = await common.upsert_evidence(
                session,
                source,
                case_id=case.id,
                origin_key=f"crustdata:identify:{cid}:{item['key']}",
                entity_ref=common.attached_ref(f"crustdata:{cid}", ref_keys),
                field_path=_FIELD_PATHS[item["key"]],
                value=item["value"],
                as_of=datetime.now(UTC).date(),
                identity_confidence=candidate.get("confidence_score"),
            )
            evidence_ids.append(str(evidence_id))
        keys.append({**item, "evidence_ids": evidence_ids})
    return keys


@step_handler(IDENTITY)
async def identify(ctx: StepContext) -> dict[str, Any]:
    case = await common.load_case(ctx)
    identifiers = dict(case.identity_identifiers or {})
    if case.identity_status == IdentityStatus.CONFIRMED and identifiers.get("basis") == "manual":
        # A re-run never overrides a person's pick.
        await ctx.append_steps(dependent_steps())
        await ensure_assessment_tail(ctx.session, run_id=ctx.run.id)
        ctx.result = "Identity confirmed earlier by a manual pick"
        return {"state": "confirmed", "basis": "manual"}

    expected = Expected.of(case)
    client = common.clients.crustdata(ctx)
    try:
        by_domain: list[IdentifyResult] = []
        by_name: list[IdentifyResult] = []
        if expected.domain:
            await ctx.set_detail(f"Matching the domain {expected.domain}")
            by_domain = await _identify(ctx, client, case, "domains", expected.domain)
        if expected.name:
            await ctx.set_detail("Matching the name")
            by_name = await _identify(ctx, client, case, "names", expected.name)
    finally:
        await common.close_quietly(client)

    decision = decide_identity(expected, by_domain, by_name)
    case.identity_candidates = [c.as_json() for c in decision.candidates]
    identifiers["note"] = decision.note
    identifiers["decided_at"] = datetime.now(UTC).isoformat()
    case.identity_identifiers = identifiers

    if decision.state != IdentityStatus.CONFIRMED or decision.chosen is None:
        case.identity_status = decision.state
        case.crustdata_company_id = None
        await ctx.session.flush()
        ctx.result = f"Identity {decision.state.value}: {len(decision.candidates)} candidates"
        return {
            "state": decision.state.value,
            "candidates": len(decision.candidates),
            "note": decision.note,
        }

    chosen = decision.chosen.as_json()
    keys = await record_key_evidence(ctx.session, case, chosen, basis="auto")
    apply_confirmation(case, chosen, keys=keys, basis="auto", note=decision.note)
    await ctx.session.flush()
    await ctx.append_steps(dependent_steps())
    await ensure_assessment_tail(ctx.session, run_id=ctx.run.id)
    matched = decision.chosen.matched_keys
    ctx.result = f"Identity confirmed: {decision.chosen.name} ({', '.join(matched)})"
    return {
        "state": "confirmed",
        "crustdata_company_id": decision.chosen.crustdata_company_id,
        "matched_on": matched,
    }


_FIELD_PATHS = {
    "crustdata_company_id": "crustdata_company_id",
    "domain": "basic_info.primary_domain",
    "profile_url": "basic_info.professional_network_url",
    "founded_year": "basic_info.year_founded",
    "hq_city": "locations.headquarters",
}
