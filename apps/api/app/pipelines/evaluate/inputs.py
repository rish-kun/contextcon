"""Read a case's records from the database into `AssessmentInputs` for `rules.assess`.

Only records attached to the case are read, and nothing here decides anything: the rules
engine does. The storage conventions this reader relies on (shared with the verify
pipelines that write the rows):

- Thesis criteria: `criteria` rows of the case's thesis. The tested company field is
  `crustdata_filter["field" | "column" | "crustdata_field"]`; without one, the
  criterion's dimension picks the profile field (`DIMENSION_FIELDS`), and dimensions with
  no profile field stay unknown.
- Claims: `claims.components` is `{name: value}` (or `{"components": [{name, value, op}]}`).
  The current check is the newest `claim_checks` row; its linked evidence holds the
  facts. A linked row is a fact for component C when `claim_check_evidence.relation`
  is C, or when `evidence.value` is `{"component": C, "value": ...}`. Any other linked
  row counts as a source that was read and said nothing about the claim.
- Profile signals: case evidence with a `field_path` (Crustdata field paths such as
  `headcount.total`, `basic_info.year_founded`) attached to the confirmed company.
- Events: `events` rows, each with its evidence id.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import Case, ClaimCheckEvidence, Event, Evidence, Source, Thesis
from app.db.models import Claim as ClaimRow
from app.db.models import ClaimCheck as ClaimCheckRow
from app.db.models import Criterion as CriterionRow
from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    CriterionKind,
    CriterionOperator,
    IdentityStatus,
    NotCheckedReason,
    SourceReliability,
)
from app.domain.types import (
    AssessmentInputs,
    BusinessInputs,
    Claim,
    ClaimCheck,
    ClaimComponent,
    CompanyProfile,
    CompanyRecord,
    Criterion,
    DatedEvent,
    ExtractedFact,
    FieldFact,
    SeriesPoint,
)
from app.domain.types import Evidence as EvidenceIn
from app.domain.types import Source as SourceIn
from app.rules import policy

R = SourceReliability

# Contract `SourceClass` values (and the domain's own values) → rule reliability.
SOURCE_RELIABILITY: dict[str, SourceReliability] = {
    "registry_official": R.REGISTRY,
    "funding_database": R.DATA_PROVIDER,
    "professional_profile": R.PROFESSIONAL_PROFILE_SIGNAL,
    "headcount_estimate": R.PROFESSIONAL_PROFILE_SIGNAL,
    "data_provider_profile": R.DATA_PROVIDER,
    "user_typed": R.SELLER_STATEMENT,
    **{r.value: r for r in SourceReliability},
}

# Profile field tested by a criterion that names no Crustdata field.
DIMENSION_FIELDS: dict[str, str] = {
    "geography": "locations.country",
    "ownership": "basic_info.company_type",
    "industry_activity": "basic_info.industries",
    "size": "headcount.total",
    "growth_signal": "headcount.growth_percent.12m",
    "funding_stage": "funding.last_round_type",
    "founded_year": "basic_info.year_founded",
}

# Extraction-style operators → rule operators. Negations have no rule operator, so the
# criterion stays unknown rather than being read the wrong way round.
OPERATORS: dict[str, CriterionOperator] = {
    "equals": CriterionOperator.EQ,
    "contains": CriterionOperator.CONTAINS_ANY,
    "exists": CriterionOperator.IS_TRUE,
    **{o.value: o for o in CriterionOperator},
}
UNASSESSABLE_FIELD = "unassessable"

ESTIMATE_PREFIXES = ("headcount.", "hiring.")
ESTIMATE_CLASSES = frozenset({"headcount_estimate", "professional_profile"})
HEADCOUNT_FIELDS = ("headcount.total", "headcount.timeseries", "headcount.history")

NOT_CHECKED_WORDS: list[tuple[str, NotCheckedReason]] = [
    ("budget", NotCheckedReason.BUDGET_EXHAUSTED),
    ("identity", NotCheckedReason.IDENTITY_UNRESOLVED),
    ("unavailable", NotCheckedReason.SOURCE_UNAVAILABLE),
    ("no source", NotCheckedReason.NO_SOURCE_IN_SCOPE),
    ("error", NotCheckedReason.SOURCE_ERROR),
    ("failed", NotCheckedReason.SOURCE_ERROR),
]


def reliability_of(source_class: str | None) -> SourceReliability:
    """Unknown classes rank lowest, so they can never settle a claim by accident."""
    return SOURCE_RELIABILITY.get(source_class or "", R.SELLER_STATEMENT)


def not_checked_reason(reason: str) -> NotCheckedReason:
    text = reason.casefold()
    for word, value in NOT_CHECKED_WORDS:
        if word in text:
            return value
    return NotCheckedReason.SOURCE_ERROR


def _company_ref(ref: str | None, company_id: str | None) -> bool:
    if not ref or not company_id:
        return False
    return ref == company_id or ref.rsplit(":", 1)[-1] == company_id


def _when(e: Evidence) -> tuple:
    return (e.as_of or dt.date.min, e.created_at, str(e.id))


def _source_in(src: Source) -> SourceIn:
    return SourceIn(
        id=str(src.id),
        provider=src.provider,
        label=src.title or src.publisher or src.provider,
        url=src.endpoint_or_url if src.endpoint_or_url.startswith("http") else None,
        retrieved_at=src.retrieved_at,
        reliability=reliability_of(src.source_class),
        origin_key=(src.request or {}).get("origin_key") if isinstance(src.request, dict) else None,
    )


def _evidence_in(e: Evidence, src: Source, value: Any) -> EvidenceIn:
    quote = e.span if e.span and e.span.strip() else None
    field_path = e.field_path or (None if quote else f"evidence.{e.id}")
    return EvidenceIn(
        id=str(e.id),
        source=_source_in(src),
        entity_id=e.entity_ref or None,
        quote=quote,
        field_path=field_path,
        field_value=value if field_path else None,
        page=e.page,
        as_of=e.as_of,
    )


# --- Criteria --------------------------------------------------------------------


def criterion_field(row: CriterionRow) -> str:
    flt = row.crustdata_filter if isinstance(row.crustdata_filter, dict) else {}
    for key in ("field", "column", "crustdata_field"):
        if isinstance(flt.get(key), str) and flt[key].strip():
            return flt[key].strip()
    return DIMENSION_FIELDS.get(row.dimension, UNASSESSABLE_FIELD)


def criterion_in(row: CriterionRow) -> Criterion:
    op = OPERATORS.get(row.operator)
    return Criterion(
        id=str(row.id),
        label=row.label,
        kind=CriterionKind(row.kind),
        field=criterion_field(row) if op is not None else UNASSESSABLE_FIELD,
        operator=op or CriterionOperator.EQ,
        value=row.value,
        dimension=row.dimension,
    )


async def load_criteria(session: AsyncSession, case: Case) -> list[Criterion]:
    if case.thesis_id is None:
        return []
    rows = (
        await session.execute(
            select(CriterionRow)
            .join(Thesis, Thesis.id == CriterionRow.thesis_id)
            .where(Thesis.id == case.thesis_id, Thesis.workspace_id == case.workspace_id)
            .order_by(CriterionRow.position, CriterionRow.id)
        )
    ).scalars()
    return [criterion_in(r) for r in rows]


# --- Company record and business signals -------------------------------------------


async def _company_evidence(session: AsyncSession, case: Case) -> list[tuple[Evidence, Source]]:
    if case.crustdata_company_id is None:
        return []
    rows = await session.execute(
        select(Evidence, Source)
        .join(Source, Source.id == Evidence.source_id)
        .where(Evidence.case_id == case.id, Evidence.field_path.is_not(None))
    )
    company_id = str(case.crustdata_company_id)
    return [(e, s) for e, s in rows.all() if _company_ref(e.entity_ref, company_id)]


def _is_estimate(e: Evidence, src: Source) -> bool:
    path = e.field_path or ""
    return path.startswith(ESTIMATE_PREFIXES) or src.source_class in ESTIMATE_CLASSES


def company_record(case: Case, evidence: list[tuple[Evidence, Source]]) -> CompanyRecord:
    latest: dict[str, tuple[Evidence, Source]] = {}
    for e, s in sorted(evidence, key=lambda p: _when(p[0])):
        latest[e.field_path or ""] = (e, s)
    return CompanyRecord(
        entity_id=str(case.crustdata_company_id or case.id),
        name=case.company_name,
        fields={
            path: FieldFact(
                value=e.value,
                evidence_id=str(e.id),
                as_of=e.as_of,
                is_estimate=_is_estimate(e, s),
            )
            for path, (e, s) in sorted(latest.items())
            if e.scrubbed_at is None
        },
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def business_inputs(record: CompanyRecord, evidence: list[tuple[Evidence, Source]], events):
    series: dict[tuple[dt.date, str], SeriesPoint] = {}
    for e, _ in evidence:
        if not (e.field_path or "").startswith(HEADCOUNT_FIELDS) or e.as_of is None:
            continue
        n = _number(e.value)
        if n is not None:
            series[(e.as_of, str(e.id))] = SeriesPoint(date=e.as_of, value=n, evidence_id=str(e.id))
    locations = [
        FieldFact(value=str(f.value), evidence_id=f.evidence_id, as_of=f.as_of)
        for path, f in sorted(record.fields.items())
        if path.startswith("locations.") and f.value not in (None, "", [])
    ]
    return BusinessInputs(
        headcount_series=[series[k] for k in sorted(series)],
        open_roles=record.fields.get("hiring.openings_count"),
        locations=locations,
        events=[
            DatedEvent(label=ev.title, date=ev.event_date, evidence_id=str(ev.evidence_id))
            for ev in sorted(events, key=lambda x: (x.event_date, x.title, str(x.id)))
        ],
    )


def company_profile(record: CompanyRecord) -> CompanyProfile:
    def value(*paths: str) -> Any:
        for p in paths:
            f = record.fields.get(p)
            if f is not None and f.value not in (None, ""):
                return f.value
        return None

    year = _number(value("basic_info.year_founded"))
    headcount = value("headcount.total", "basic_info.employee_count_range")
    count = _number(headcount)
    return CompanyProfile(
        founded_year=int(year) if year is not None else None,
        headcount=int(count) if count is not None else headcount,
        funding_stage=value("funding.last_round_type"),
    )


# --- Claims ----------------------------------------------------------------------


def claim_components(raw: Any) -> list[ClaimComponent]:
    if isinstance(raw, dict) and isinstance(raw.get("components"), list):
        out = []
        for c in raw["components"]:
            if isinstance(c, dict) and c.get("name"):
                op = c.get("op") if c.get("op") in ("eq", "gte", "lte") else "eq"
                out.append(ClaimComponent(name=str(c["name"]), value=c.get("value"), op=op))
        return out
    if isinstance(raw, dict):
        return [ClaimComponent(name=str(k), value=v) for k, v in sorted(raw.items())]
    return []


def _fact_component(relation: str | None, value: Any) -> tuple[str | None, Any]:
    if relation and relation in policy.COMPONENT_RULES:
        return relation, value
    if isinstance(value, dict) and value.get("component") in policy.COMPONENT_RULES:
        return value["component"], value.get("value")
    return None, value


async def load_claim_checks(session: AsyncSession, case: Case) -> list[ClaimCheck]:
    claims = await repo.list_claims(session, case.workspace_id, case.id)
    latest = await repo.latest_claim_checks(session, case.workspace_id, case.id)
    check_ids = [c.id for c in latest.values()]
    linked: dict[uuid.UUID, list[tuple[str, Evidence, Source]]] = defaultdict(list)
    if check_ids:
        rows = await session.execute(
            select(ClaimCheckEvidence.claim_check_id, ClaimCheckEvidence.relation, Evidence, Source)
            .join(Evidence, Evidence.id == ClaimCheckEvidence.evidence_id)
            .join(Source, Source.id == Evidence.source_id)
            .where(ClaimCheckEvidence.claim_check_id.in_(check_ids))
        )
        for check_id, relation, e, s in rows.all():
            linked[check_id].append((relation, e, s))

    out: list[ClaimCheck] = []
    for row in sorted(claims, key=lambda c: (c.created_at, str(c.id))):
        out.append(_claim_check(row, latest.get(row.id), linked))
    return out


def _claim_check(
    row: ClaimRow,
    check: ClaimCheckRow | None,
    linked: dict[uuid.UUID, list[tuple[str, Evidence, Source]]],
) -> ClaimCheck:
    try:
        category = ClaimCategory(row.category)
    except ValueError:
        category = ClaimCategory.OTHER
    claim = Claim(
        id=str(row.id),
        text=row.original_text,
        category=category,
        components=claim_components(row.components),
    )
    if check is None:
        return ClaimCheck(
            claim=claim,
            ran=False,
            not_run_reason=NotCheckedReason.NO_SOURCE_IN_SCOPE,
            not_run_detail="no check has run for this claim yet",
        )
    if check.status == ClaimStatus.NOT_CHECKED:
        return ClaimCheck(
            claim=claim,
            ran=False,
            not_run_reason=not_checked_reason(check.reason),
            not_run_detail=check.reason or None,
        )
    facts: list[ExtractedFact] = []
    read: dict[str, SourceIn] = {}
    for relation, e, s in sorted(linked.get(check.id, []), key=lambda t: str(t[1].id)):
        read.setdefault(str(s.id), _source_in(s))
        if e.scrubbed_at is not None:
            continue  # purged under retention: no longer usable as a fact
        component, value = _fact_component(relation, e.value)
        if component is None:
            continue
        facts.append(
            ExtractedFact(
                id=f"{e.id}:{component}",
                evidence=_evidence_in(e, s, value),
                component=component,
                value=value,
            )
        )
    return ClaimCheck(
        claim=claim,
        facts=facts,
        sources_read=[read[k] for k in sorted(read)],
    )


# --- Everything ------------------------------------------------------------------


async def load_inputs(
    session: AsyncSession, case: Case, *, today: dt.date, version: int = 1
) -> AssessmentInputs:
    evidence = await _company_evidence(session, case)
    record = company_record(case, evidence)
    events = list((await session.execute(select(Event).where(Event.case_id == case.id))).scalars())
    return AssessmentInputs(
        case_id=str(case.id),
        version=version,
        today=today,
        identity_status=IdentityStatus(case.identity_status),
        profile=company_profile(record),
        company=record,
        criteria=await load_criteria(session, case),
        claim_checks=await load_claim_checks(session, case),
        business=business_inputs(record, evidence, events),
    )
