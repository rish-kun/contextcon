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
- Identity binding (design §5.4): evidence carries no basis column, so the basis is
  derived from how the row was attached: a Crustdata reference
  (`crustdata:company:<id>`, `crustdata:person:<id>`, or the bare confirmed company
  id) is `crustdata_id`; `domain:`, `cin:`, `registry:` and `profile:` prefixes map to
  their identifiers; a document uploaded to the case is `case_upload`. Anything else
  has no corroborating identifier and never decides a status or criterion. Claims are
  bound to the confirmed company (and the people linked to their checks by Crustdata
  id) only while identity is confirmed.
- Seller documents: `sources.request["document_type"]` (a `DocumentType` value) says
  what kind of document an upload is; without one it is a generic document.
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
    DocumentType,
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
    FinancialEstimate,
    FinancialInputs,
    ReportedFigure,
    SeriesPoint,
)
from app.domain.types import Evidence as EvidenceIn
from app.domain.types import Source as SourceIn
from app.pipelines.discover.countries import country_name
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

ESTIMATE_PREFIXES = ("headcount.", "hiring.", "revenue.estimated")
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


_REF_BASIS = (
    ("crustdata:", "crustdata_id"),
    ("domain:", "domain"),
    ("cin:", "cin"),
    ("registry:", "registry_id"),
    ("profile:", "profile_url"),
)


def company_entity(case: Case) -> str:
    return str(case.crustdata_company_id or case.id)


def entity_of(e: Evidence, case: Case) -> str | None:
    """The rule-side entity id: the confirmed company's id, or the stored reference."""
    if _company_ref(e.entity_ref, str(case.crustdata_company_id or "")):
        return company_entity(case)
    return e.entity_ref or None


def identity_basis(e: Evidence, src: Source, case: Case) -> list[str]:
    """How the row was tied to its entity; empty means a name match at best."""
    basis: list[str] = []
    if src.document_id is not None or src.provider == "upload":
        basis.append("case_upload")
    ref = e.entity_ref or ""
    for prefix, name in _REF_BASIS:
        if ref.startswith(prefix):
            basis.append(name)
    if case.crustdata_company_id and ref == str(case.crustdata_company_id):
        basis.append("crustdata_id")
    return sorted(set(basis))


def _document_type(src: Source) -> DocumentType | None:
    raw = (src.request or {}).get("document_type") if isinstance(src.request, dict) else None
    try:
        return DocumentType(raw) if raw else None
    except ValueError:
        return None


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
        document_type=_document_type(src),
    )


def _evidence_in(e: Evidence, src: Source, value: Any, case: Case) -> EvidenceIn:
    quote = e.span if e.span and e.span.strip() else None
    field_path = e.field_path or (None if quote else f"evidence.{e.id}")
    return EvidenceIn(
        id=str(e.id),
        source=_source_in(src),
        entity_id=entity_of(e, case),
        quote=quote,
        field_path=field_path,
        field_value=value if field_path else None,
        page=e.page,
        as_of=e.as_of,
        identity_basis=identity_basis(e, src, case),
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


COUNTRY_FIELDS = frozenset({"locations.country", "headcount.largest_headcount_country"})


def _field_value(path: str, value: Any) -> Any:
    """The provider stores ISO codes ("IND") for countries; criteria name the country
    ("India"). An unknown code is unknown (None), never a mismatch."""
    if path in COUNTRY_FIELDS:
        return country_name(value)
    return value


def company_record(case: Case, evidence: list[tuple[Evidence, Source]]) -> CompanyRecord:
    latest: dict[str, tuple[Evidence, Source]] = {}
    for e, s in sorted(evidence, key=lambda p: _when(p[0])):
        latest[e.field_path or ""] = (e, s)
    return CompanyRecord(
        entity_id=company_entity(case),
        name=case.company_name,
        fields={
            path: FieldFact(
                value=_field_value(path, e.value),
                evidence_id=str(e.id),
                as_of=e.as_of,
                is_estimate=_is_estimate(e, s),
                entity_id=entity_of(e, case),
                identity_basis=identity_basis(e, s, case),
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
        out.append(_claim_check(row, latest.get(row.id), linked, case))
    return out


def claim_entities(case: Case, links: list[tuple[str, Evidence, Source]]) -> list[str]:
    """Entities a claim's facts may attach to: the confirmed company, plus people
    linked to its check by Crustdata id. Nothing while identity is not confirmed."""
    if case.identity_status != IdentityStatus.CONFIRMED.value:
        return []
    people = sorted(
        {e.entity_ref for _, e, _ in links if e.entity_ref.startswith("crustdata:person:")}
    )
    return [company_entity(case), *people]


def _claim_check(
    row: ClaimRow,
    check: ClaimCheckRow | None,
    linked: dict[uuid.UUID, list[tuple[str, Evidence, Source]]],
    case: Case,
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
        entity_ids=claim_entities(case, linked.get(check.id, []) if check else []),
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
                evidence=_evidence_in(e, s, value, case),
                component=component,
                value=value,
            )
        )
    return ClaimCheck(
        claim=claim,
        facts=facts,
        sources_read=[read[k] for k in sorted(read)],
    )


# --- Financials ------------------------------------------------------------------

FINANCIAL_PREFIX = "financials."
ESTIMATE_FIELD = "revenue.estimated"


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def financial_inputs(case: Case, evidence: list[tuple[Evidence, Source]]) -> FinancialInputs:
    """What `verify.financials` found and searched, and the provider's revenue estimate.

    Figures are the `financials.<component>` rows (value: `{component, value, period,
    period_end, period_months, amount, currency, unit}`) attached to the confirmed
    company; the rules screen them like any fact. The search record and listing status
    are on the case entity (`identity_identifiers.entity.financials`)."""
    figures: list[ReportedFigure] = []
    estimates: list[FinancialEstimate] = []
    for e, s in sorted(evidence, key=lambda p: str(p[0].id)):
        if e.scrubbed_at is not None:
            continue
        path = e.field_path or ""
        raw = e.value if isinstance(e.value, dict) else {}
        if path.startswith(FINANCIAL_PREFIX) and raw.get("component") in policy.COMPONENT_RULES:
            component = raw["component"]
            figures.append(
                ReportedFigure(
                    fact=ExtractedFact(
                        id=f"{e.id}:{component}",
                        evidence=_evidence_in(e, s, raw.get("value"), case),
                        component=component,
                        value=raw.get("value"),
                    ),
                    period=raw.get("period"),
                    period_end=_date(raw.get("period_end")),
                    period_months=raw.get("period_months"),
                    amount=_number(raw.get("amount")),
                    currency=raw.get("currency"),
                    unit=raw.get("unit"),
                )
            )
        elif path == ESTIMATE_FIELD:
            estimates.append(
                FinancialEstimate(
                    lower_usd=_number(raw.get("lower_bound_usd")),
                    upper_usd=_number(raw.get("upper_bound_usd")),
                    as_of=e.as_of,
                    evidence_id=str(e.id),
                    source_label=s.title or s.publisher or s.provider,
                )
            )
    entity = (case.identity_identifiers or {}).get("entity") or {}
    record = entity.get("financials") if isinstance(entity.get("financials"), dict) else {}
    listing = record.get("listing")
    return FinancialInputs(
        figures=figures,
        estimates=estimates,
        listing=listing if listing in ("listed", "unlisted", "unknown") else "unknown",
        listing_basis=record.get("listing_basis"),
        searched=[str(x) for x in record["searched"]] if "searched" in record else None,
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
        financials=financial_inputs(case, evidence),
    )
