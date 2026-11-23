"""`GET /cases/{id}` is assembled from per-section builders, so each checkpoint fills its
own section without touching the others.

    from app.api.cases_sections import CaseContext, register_section

    async def build_claims(ctx: CaseContext) -> list[ClaimOut]:
        ...                                    # ctx.session, ctx.case, ctx.evidence_out(...)

    register_section("claims", build_claims)   # replaces the default for that key

Keys are `CaseDetail` field names. Builders run in registration order and the last
builder registered for a key wins. Defaults here: case, opportunity (placeholder until
CP-22), identity, profile, events, comparables, sources, cost, runs (CP-19). Sections
without a builder take the schema default (claims, assessment, risks, request_list,
message, documents, deletions: empty).

`case_summary` (the `GET /cases` row) works the same way through `register_summary`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.assessments import FitState
from app.api.schemas.cases import (
    CaseCostOut,
    CaseDetail,
    CaseOut,
    CaseStatus,
    CaseSummary,
    ComparableCompanyOut,
    ComparablesOut,
    ComparisonBasisOut,
    CostLineOut,
    EventOut,
    IdentityCandidateOut,
    IdentityKeyOut,
    IdentityOut,
    IdentityPickOut,
    OpportunityOut,
    SharedCostOut,
)
from app.api.schemas.common import (
    CompanyType,
    CostTotalsOut,
    EntityAttachment,
    EstimateKind,
    EvidenceOut,
    FactFloat,
    FactInt,
    FactStr,
    FactStrList,
    IdentityState,
    NamedUserOut,
    RunKind,
    RunState,
    SourceClass,
    SourceRecordOut,
    SourceRef,
)
from app.api.schemas.company import (
    CompanyProfileOut,
    FundingRoundOut,
    HeadcountPointOut,
    HeadcountSeriesOut,
    HiringOut,
    PersonOut,
)
from app.api.schemas.runs import RunSummaryOut
from app.db import ledger
from app.db.enums import IdentityStatus, StepState
from app.db.models import (
    AssessmentVersion,
    Candidate,
    Case,
    Claim,
    Comparable,
    CostEntry,
    DiscoveryRun,
    Event,
    Evidence,
    Run,
    Source,
    Step,
)
from app.jobs.activity import public_step_text
from app.pipelines.evaluate import cases as evaluate_cases
from app.pipelines.verify.common import COMPARABLES, parse_date, parse_ref
from app.settings import get_settings

HEADCOUNT_BASIS = "from professional profiles, not a payroll count"


# --- Context ----------------------------------------------------------------------


@dataclass
class CaseContext:
    """What every builder may read. Sources and evidence load once, on first use."""

    session: AsyncSession
    workspace_id: uuid.UUID
    case: Case
    _sources: dict[uuid.UUID, Source] | None = field(default=None, repr=False)
    _evidence: list[Evidence] | None = field(default=None, repr=False)
    _runs: list[Run] | None = field(default=None, repr=False)
    # Section values already built for this request (`built`).
    _built: dict[str, Any] = field(default_factory=dict, repr=False)
    # Summary values loaded for many cases at once (`build_case_summaries`).
    _batch: dict[str, Any] | None = field(default=None, repr=False)

    async def built(self, key: str) -> Any:
        """The value of detail section `key` for this request, built at most once, so a
        builder that reads another section (the memo reads events and comparables) does
        not query for it again."""
        if key not in self._built:
            self._built[key] = await CASE_DETAIL_SECTIONS[key](self)
        return self._built[key]

    async def sources(self) -> dict[uuid.UUID, Source]:
        if self._sources is None:
            rows = await self.session.execute(
                select(Source)
                .where(Source.case_id == self.case.id, Source.workspace_id == self.workspace_id)
                .order_by(Source.retrieved_at)
            )
            self._sources = {s.id: s for s in rows.scalars()}
        return self._sources

    async def evidence(self) -> list[Evidence]:
        if self._evidence is None:
            rows = await self.session.execute(
                select(Evidence)
                .where(Evidence.case_id == self.case.id)
                .order_by(Evidence.created_at)
            )
            self._evidence = list(rows.scalars())
        return self._evidence

    async def runs(self) -> list[Run]:
        if self._runs is None:
            rows = await self.session.execute(
                select(Run).where(Run.case_id == self.case.id).order_by(Run.created_at)
            )
            self._runs = list(rows.scalars())
        return self._runs

    @property
    def entity_ref(self) -> str | None:
        cid = self.case.crustdata_company_id
        if self.case.identity_status != IdentityStatus.CONFIRMED or cid is None:
            return None
        return f"crustdata:{cid}"

    async def attached_evidence(self) -> list[Evidence]:
        """Evidence attached to the confirmed company. Empty while identity is open."""
        ref = self.entity_ref
        if ref is None:
            return []
        return [e for e in await self.evidence() if parse_ref(e.entity_ref).entity == ref]

    async def source_ref(self, source_id: uuid.UUID, origin: str | None = None) -> SourceRef:
        return source_ref((await self.sources())[source_id], origin)

    async def evidence_out(self, ev: Evidence) -> EvidenceOut:
        return await evidence_out(self, ev)


SectionBuilder = Callable[[CaseContext], Awaitable[Any]]
CASE_DETAIL_SECTIONS: dict[str, SectionBuilder] = {}
CASE_SUMMARY_FIELDS: dict[str, SectionBuilder] = {}


def register_section(key: str, builder: SectionBuilder) -> SectionBuilder:
    if key not in CaseDetail.model_fields:
        raise KeyError(f"CaseDetail has no section {key!r}")
    CASE_DETAIL_SECTIONS.pop(key, None)
    CASE_DETAIL_SECTIONS[key] = builder
    return builder


SummaryBatch = Callable[
    [AsyncSession, uuid.UUID, list[CaseContext]], Awaitable[dict[uuid.UUID, Any]]
]
# Optional loaders that compute one summary field for every listed case at once.
CASE_SUMMARY_BATCHES: dict[str, SummaryBatch] = {}


def register_summary(key: str, builder: SectionBuilder) -> SectionBuilder:
    if key not in CaseSummary.model_fields:
        raise KeyError(f"CaseSummary has no field {key!r}")
    CASE_SUMMARY_FIELDS.pop(key, None)
    CASE_SUMMARY_FIELDS[key] = builder
    # A batch loader belongs to the builder it was written for.
    CASE_SUMMARY_BATCHES.pop(key, None)
    return builder


def register_summary_batch(key: str, load: SummaryBatch) -> SummaryBatch:
    """Compute summary field `key` for all cases of `GET /cases` in a few queries.

    `load(session, workspace_id, ctxs)` returns {case id: value}. A case missing from
    the result falls back to the field's per-case builder. Register it after the
    builder (`register_summary` drops the batch of a replaced builder)."""
    if key not in CASE_SUMMARY_FIELDS:
        raise KeyError(f"no summary builder registered for {key!r}")
    CASE_SUMMARY_BATCHES[key] = load
    return load


def section(key: str) -> Callable[[SectionBuilder], SectionBuilder]:
    def decorate(fn: SectionBuilder) -> SectionBuilder:
        return register_section(key, fn)

    return decorate


def summary_field(key: str) -> Callable[[SectionBuilder], SectionBuilder]:
    def decorate(fn: SectionBuilder) -> SectionBuilder:
        return register_summary(key, fn)

    return decorate


async def build_case_detail(
    session: AsyncSession, workspace_id: uuid.UUID, case: Case
) -> CaseDetail:
    ctx = CaseContext(session, workspace_id, case)
    values = {key: await ctx.built(key) for key in list(CASE_DETAIL_SECTIONS)}
    return CaseDetail(**values)


async def build_case_summary(
    session: AsyncSession, workspace_id: uuid.UUID, case: Case
) -> CaseSummary:
    ctx = CaseContext(session, workspace_id, case)
    values = {key: await builder(ctx) for key, builder in list(CASE_SUMMARY_FIELDS.items())}
    return CaseSummary(**values)


async def build_case_summaries(
    session: AsyncSession, workspace_id: uuid.UUID, cases: list[Case]
) -> list[CaseSummary]:
    """`GET /cases` rows, the same as `build_case_summary` per case, but each field
    with a batch loader is read for every case at once (a handful of queries in all,
    instead of about ten per case)."""
    ctxs = [CaseContext(session, workspace_id, case) for case in cases]
    if ctxs:
        runs: dict[uuid.UUID, list[Run]] = {c.case.id: [] for c in ctxs}
        rows = await session.execute(
            select(Run).where(Run.case_id.in_(list(runs))).order_by(Run.created_at)
        )
        for run in rows.scalars():
            runs[run.case_id].append(run)  # type: ignore[index]
        for ctx in ctxs:
            ctx._runs = runs[ctx.case.id]
    batched: dict[str, dict[uuid.UUID, Any]] = {}
    for key, load in list(CASE_SUMMARY_BATCHES.items()):
        if ctxs and key in CASE_SUMMARY_FIELDS:
            batched[key] = await load(session, workspace_id, ctxs)
    out = []
    for ctx in ctxs:
        values = {}
        for key, builder in list(CASE_SUMMARY_FIELDS.items()):
            found = batched.get(key, {})
            values[key] = found[ctx.case.id] if ctx.case.id in found else await builder(ctx)
        out.append(CaseSummary(**values))
    return out


# --- Provenance mapping -------------------------------------------------------------


def contract_source_class(source: Source) -> SourceClass:
    """`sources.source_class` stores `SourceReliability`, which the contract shares."""
    try:
        return SourceClass(source.source_class)
    except ValueError:
        return SourceClass.data_provider


_PART_LABELS = {
    "profile": "Company record",
    "funding": "Funding record",
    "people": "Company record: people",
    "headcount": "Profile estimate",
    "hiring": "Hiring signal",
    "comparables": "Company search",
}


def source_label(source: Source, cls: SourceClass | None = None) -> str:
    cls = cls or contract_source_class(source)
    part = (source.request or {}).get("part")
    if part in _PART_LABELS:
        return _PART_LABELS[part]
    if cls == SourceClass.news:
        return f"News: {source.publisher}" if source.publisher else "News"
    if cls == SourceClass.company_announcement:
        return f"Announcement: {source.publisher}" if source.publisher else "Announcement"
    if cls == SourceClass.registry:
        return "Registry (MCA)"
    if cls == SourceClass.registry_mirror:
        return f"Registry mirror: {source.publisher}" if source.publisher else "Registry mirror"
    return source.title or cls.value.replace("_", " ").capitalize()


def _provider(source: Source) -> str:
    return {"document": "upload", "upload": "upload", "user": "user"}.get(
        source.provider, source.provider
    )


def source_ref(source: Source, origin: str | None = None) -> SourceRef:
    cls = contract_source_class(source)
    return SourceRef(
        source_id=str(source.id),
        provider=_provider(source),
        label=source_label(source, cls),
        url_or_endpoint=source.endpoint_or_url,
        retrieved_at=source.retrieved_at,
        source_class=cls,
        origin_id=origin if source.provider == "web" else None,
    )


async def evidence_out(ctx: CaseContext, ev: Evidence) -> EvidenceOut:
    ref = parse_ref(ev.entity_ref)
    attached = None
    if ref.attached and ref.entity:
        attached = EntityAttachment(
            entity_name=_entity_name(ctx.case) if ref.entity == ctx.entity_ref else ref.entity,
            matched_on=ref.matched_on,
            identity_confidence=ev.identity_confidence,
        )
    return EvidenceOut(
        evidence_id=str(ev.id),
        source=await ctx.source_ref(ev.source_id, ev.origin_key),
        quote=None if ev.scrubbed_at else ev.span,
        page=ev.page,
        field_path=ev.field_path,
        value=ev.value,
        as_of=ev.as_of,
        attached_to=attached,
        deleted=ev.scrubbed_at is not None,
    )


def _entity_name(case: Case) -> str:
    entity = (case.identity_identifiers or {}).get("entity") or {}
    return str(entity.get("name") or case.company_name)


# --- case ---------------------------------------------------------------------------


async def case_status(ctx: CaseContext) -> CaseStatus:
    runs = await ctx.runs()
    assessed = await ctx.session.execute(
        select(AssessmentVersion.id).where(AssessmentVersion.case_id == ctx.case.id).limit(1)
    )
    return evaluate_cases.case_status(
        ctx.case, evaluate_cases.current_run(runs), assessed.first() is not None
    )


def _credit_budget(case: Case) -> float:
    budget = case.credit_budget
    return float(budget if budget is not None else get_settings().case_credit_budget)


async def build_case_out(ctx: CaseContext) -> CaseOut:
    return await evaluate_cases.case_out(ctx.session, ctx.case)


@section("case")
async def case_section(ctx: CaseContext) -> CaseOut:
    return await build_case_out(ctx)


@section("opportunity")
async def opportunity_section(ctx: CaseContext) -> OpportunityOut:
    """Placeholder until CP-22 registers the real opportunity builder."""
    if ctx.case.identity_status != IdentityStatus.CONFIRMED:
        state = FitState.identity_unresolved
    elif ctx.case.thesis_id is None:
        state = FitState.awaiting_strategy_criteria
    else:
        state = FitState.unavailable
    return OpportunityOut(
        thesis_id=str(ctx.case.thesis_id) if ctx.case.thesis_id else None, fit_state=state
    )


@section("claims")
async def claims_section(ctx: CaseContext) -> list[Any]:
    """CP-20's claim ledger (replace with `register_section("claims", ...)`)."""
    from app.pipelines.verify.claims.ledger import build_claims_section

    return await build_claims_section(ctx.session, ctx.case)


# --- identity -----------------------------------------------------------------------


def _key_out(item: dict[str, Any], evidence: list[EvidenceOut] | None = None) -> IdentityKeyOut:
    return IdentityKeyOut(
        key=item["key"],
        label=item.get("label") or item["key"],
        value=str(item.get("value")),
        evidence=evidence or [],
    )


def _differing_out(item: dict[str, Any]) -> IdentityKeyOut:
    value = str(item.get("value"))
    if item.get("expected") is not None:
        value = f"{value} (case: {item['expected']})"
    return _key_out({**item, "value": value})


@section("identity")
async def identity_section(ctx: CaseContext) -> IdentityOut:
    case = ctx.case
    identifiers = case.identity_identifiers or {}
    by_id = {str(e.id): e for e in await ctx.evidence()}
    keys = []
    for item in identifiers.get("keys", []) if case.identity_status == "confirmed" else []:
        evidence = [
            await ctx.evidence_out(by_id[i]) for i in item.get("evidence_ids", []) if i in by_id
        ]
        keys.append(_key_out(item, evidence))
    pick = identifiers.get("pick")
    show_candidates = case.identity_status != IdentityStatus.CONFIRMED or pick is not None
    candidates = [
        IdentityCandidateOut(
            crustdata_company_id=int(c["crustdata_company_id"]),
            name=c.get("name") or str(c["crustdata_company_id"]),
            confidence_score=c.get("confidence_score"),
            matching=[_key_out(k) for k in c.get("matching", [])],
            differing=[_differing_out(k) for k in c.get("differing", [])],
        )
        for c in (case.identity_candidates or [] if show_candidates else [])
    ]
    pick_out = None
    if pick:
        pick_out = IdentityPickOut(
            crustdata_company_id=int(pick["crustdata_company_id"]),
            picked_by=NamedUserOut(user_id=pick["user_id"], display_name=pick["display_name"]),
            picked_at=datetime.fromisoformat(pick["picked_at"]),
            matched_keys=list(pick.get("matched_keys", [])),
        )
    confirmed = case.identity_status == IdentityStatus.CONFIRMED
    return IdentityOut(
        state=IdentityState(case.identity_status),
        entity_name=_entity_name(case) if confirmed else None,
        crustdata_company_id=int(case.crustdata_company_id) if confirmed else None,
        keys=keys,
        candidates=candidates,
        pick=pick_out,
        note=identifiers.get("note"),
    )


# --- profile ------------------------------------------------------------------------


@section("profile")
async def profile_section(ctx: CaseContext) -> CompanyProfileOut | None:
    rows = await ctx.attached_evidence()
    if not rows:
        return None
    latest: dict[str, Evidence] = {}
    multi: dict[str, list[Evidence]] = {}
    for ev in rows:
        if not ev.field_path:
            continue
        latest[ev.field_path] = ev
        multi.setdefault(ev.field_path.split("[")[0], []).append(ev)

    async def fact(path: str, cls: type, cast: Callable[[Any], Any] = str, **kw: Any) -> Any:
        ev = latest.get(path)
        if ev is None or ev.value in (None, "", []):
            return None
        try:
            value = cast(ev.value)
        except (TypeError, ValueError):
            return None
        return cls(
            value=value,
            source=await ctx.source_ref(ev.source_id),
            evidence_id=str(ev.id),
            as_of=ev.as_of,
            **kw,
        )

    signal = {
        "is_estimate": True,
        "estimate_kind": EstimateKind.signal,
        "estimate_basis": HEADCOUNT_BASIS,
    }
    name = await fact("basic_info.name", FactStr)
    if name is None:
        return None

    series = None
    if (ev := latest.get("headcount.timeseries")) and isinstance(ev.value, list):
        points = [
            HeadcountPointOut(date=d, employee_count=int(p["employee_count"]))
            for p in ev.value
            if (d := parse_date(p.get("date"))) and p.get("employee_count") is not None
        ]
        if points:
            series = HeadcountSeriesOut(
                points=points,
                source=await ctx.source_ref(ev.source_id),
                estimate_basis=HEADCOUNT_BASIS,
            )

    rounds = []
    for ev in multi.get("funding.milestones", []):
        value = ev.value or {}
        rounds.append(
            FundingRoundOut(
                round_type=value.get("round_type"),
                date=parse_date(value.get("date")),
                amount_usd=value.get("amount_usd"),
                investors=list(value.get("investors") or []),
                source=await ctx.source_ref(ev.source_id),
                evidence_id=str(ev.id),
            )
        )
    rounds.sort(key=lambda r: r.date or date.min, reverse=True)

    people = []
    for path in ("people.founders", "people.cxos"):
        for ev in multi.get(path, []):
            value = ev.value or {}
            if any(p.name == value.get("name") for p in people):
                continue
            title = None
            if value.get("title"):
                title = FactStr(
                    value=value["title"],
                    source=await ctx.source_ref(ev.source_id),
                    evidence_id=str(ev.id),
                    as_of=ev.as_of,
                )
            people.append(
                PersonOut(name=value["name"], title=title, profile_url=value.get("profile_url"))
            )

    hiring = None
    openings = await fact("hiring.openings_count", FactInt, int, **signal)
    titles = await fact(
        "hiring.recent_titles_csv",
        FactStrList,
        lambda v: [t.strip() for t in str(v).split(",") if t.strip()][:10],
        is_estimate=True,
        estimate_kind=EstimateKind.signal,
    )
    if openings or titles:
        hiring = HiringOut(openings=openings, recent_titles=titles)

    entity = (ctx.case.identity_identifiers or {}).get("entity") or {}
    company_type = CompanyType(ctx.case.company_type) if ctx.case.company_type else None
    return CompanyProfileOut(
        crustdata_company_id=int(ctx.case.crustdata_company_id),
        name=name,
        legal_name=await fact("registry.legal_name", FactStr),
        domain=await fact("basic_info.primary_domain", FactStr),
        description=await fact("basic_info.description", FactStr),
        industries=await fact("basic_info.industries", FactStrList, list),
        headquarters=await fact("locations.headquarters", FactStr),
        country=await fact("locations.country", FactStr),
        year_founded=await fact("basic_info.year_founded", FactInt, int),
        incorporation_date=await fact("registry.incorporation_date", FactStr),
        registry_id=await fact("registry.cin", FactStr),
        company_type=company_type,
        company_type_reason=entity.get("company_type_reason"),
        headcount=await fact("headcount.total", FactInt, int, **signal),
        headcount_growth_yoy_pct=await fact(
            "headcount.growth_percent.yoy", FactFloat, float, **signal
        ),
        headcount_series=series,
        total_funding_usd=await fact("funding.total_investment_usd", FactFloat, float),
        funding_rounds=rounds,
        people=people,
        hiring=hiring,
    )


# --- events -------------------------------------------------------------------------


@section("events")
async def events_section(ctx: CaseContext) -> list[EventOut]:
    rows = await ctx.session.execute(
        select(Event, Evidence)
        .join(Evidence, Evidence.id == Event.evidence_id)
        .where(Event.case_id == ctx.case.id)
        .order_by(Event.event_date.desc())
    )
    return [await event_out(ctx, event, ev) for event, ev in rows.all()]


async def event_out(ctx: CaseContext, event: Event, ev: Evidence) -> EventOut:
    return EventOut(
        id=str(event.id),
        event_date=event.event_date,
        title=event.title,
        kind=event.kind if not event.stage else f"{event.kind} ({event.stage})",
        evidence=await ctx.evidence_out(ev),
    )


# --- comparables --------------------------------------------------------------------


async def _latest_step_output(ctx: CaseContext, key: str) -> dict[str, Any] | None:
    row = await ctx.session.execute(
        select(Step.output)
        .join(Run, Run.id == Step.run_id)
        .where(Run.case_id == ctx.case.id, Step.key == key, Step.state == StepState.DONE)
        .order_by(Step.finished_at.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


def _basis_out(basis: dict[str, Any] | None) -> ComparisonBasisOut:
    basis = basis or {}
    return ComparisonBasisOut(
        industry=basis.get("industry"),
        country=basis.get("country"),
        headcount_band=basis.get("headcount_band"),
    )


@section("comparables")
async def comparables_section(ctx: CaseContext) -> ComparablesOut:
    rows = (
        await ctx.session.execute(
            select(Comparable, Evidence)
            .join(Evidence, Evidence.id == Comparable.evidence_id)
            .where(Comparable.case_id == ctx.case.id)
            .order_by(Comparable.created_at)
        )
    ).all()
    if rows:
        companies = []
        for comp, ev in rows:
            value = ev.value or {}
            companies.append(
                ComparableCompanyOut(
                    crustdata_company_id=int(comp.crustdata_company_id),
                    name=comp.name,
                    observation=FactStr(
                        value=value.get("observation") or str(value.get("headcount")),
                        source=await ctx.source_ref(ev.source_id),
                        evidence_id=str(ev.id),
                        as_of=ev.as_of,
                        is_estimate=True,
                        estimate_kind=EstimateKind.signal,
                        estimate_basis=HEADCOUNT_BASIS,
                    ),
                )
            )
        return ComparablesOut(basis=_basis_out(rows[0][0].basis), companies=companies)
    output = await _latest_step_output(ctx, COMPARABLES)
    if output is None:
        reason = (
            "Not checked: identity unresolved"
            if ctx.case.identity_status != IdentityStatus.CONFIRMED
            else "Not checked yet"
        )
        return ComparablesOut(basis=ComparisonBasisOut(), no_fair_comparison_reason=reason)
    return ComparablesOut(
        basis=_basis_out(output.get("basis")),
        no_fair_comparison_reason=output.get("no_fair_comparison")
        or output.get("blocked")
        or "No fair comparison found",
    )


# --- sources ------------------------------------------------------------------------


@section("sources")
async def sources_section(ctx: CaseContext) -> list[SourceRecordOut]:
    by_source: dict[uuid.UUID, list[Evidence]] = {}
    for ev in await ctx.evidence():
        by_source.setdefault(ev.source_id, []).append(ev)
    out = []
    for source in (await ctx.sources()).values():
        evidence = by_source.get(source.id, [])
        refs = [parse_ref(e.entity_ref) for e in evidence]
        attached = not refs or any(r.attached for r in refs)
        origins = {e.origin_key for e in evidence}
        out.append(
            SourceRecordOut(
                source_id=str(source.id),
                provider=_provider(source),
                label=source_label(source),
                url_or_endpoint=source.endpoint_or_url,
                request=source.request or None,
                retrieved_at=source.retrieved_at,
                source_class=contract_source_class(source),
                origin_id=_single_origin(source, origins),
                title=source.title,
                publisher=source.publisher,
                run_id=str(source.run_id) if source.run_id else None,
                attached=attached,
                unattached_reason=None if attached else refs[0].reason,
            )
        )
    return out


def _single_origin(source: Source, origins: set[str]) -> str | None:
    return next(iter(origins)) if source.provider == "web" and len(origins) == 1 else None


# --- cost and runs --------------------------------------------------------------------


def _totals_out(totals: ledger.CostTotals) -> CostTotalsOut:
    return CostTotalsOut(
        crustdata_credits=float(totals.credits),
        llm_usd=float(totals.usd),
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        unknown_cost_calls=totals.unknown_calls,
    )


def _row_totals(row: Any) -> CostTotalsOut:
    return CostTotalsOut(
        crustdata_credits=float(row.credits or 0),
        llm_usd=float(row.usd or 0),
        input_tokens=int(row.input_tokens or 0),
        output_tokens=int(row.output_tokens or 0),
        unknown_cost_calls=int(row.unknown or 0),
    )


_COST_COLUMNS = (
    func.sum(CostEntry.credits).label("credits"),
    func.sum(CostEntry.usd).label("usd"),
    func.sum(CostEntry.input_tokens).label("input_tokens"),
    func.sum(CostEntry.output_tokens).label("output_tokens"),
    func.count().filter(CostEntry.unknown).label("unknown"),
    func.bool_and(CostEntry.cached).label("cached"),
    func.max(CostEntry.created_at).label("at"),
)


async def shared_discovery_cost(ctx: CaseContext) -> SharedCostOut | None:
    if ctx.case.candidate_id is None:
        return None
    discovery = (
        await ctx.session.execute(
            select(DiscoveryRun)
            .join(Candidate, Candidate.discovery_run_id == DiscoveryRun.id)
            .where(
                Candidate.id == ctx.case.candidate_id,
                DiscoveryRun.workspace_id == ctx.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if discovery is None:
        return None
    run_id = (
        await ctx.session.execute(
            select(Run.id)
            .where(Run.discovery_run_id == discovery.id)
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    totals = await ledger.discovery_run_totals(ctx.session, ctx.workspace_id, discovery.id)
    return SharedCostOut(
        run_id=str(run_id or discovery.id),
        thesis_id=str(discovery.thesis_id),
        cost=_totals_out(totals),
    )


@section("cost")
async def cost_section(ctx: CaseContext) -> CaseCostOut:
    """This case's own spend. Discovery spend is listed as shared, never added."""
    totals = await ledger.case_totals(ctx.session, ctx.workspace_id, ctx.case.id)
    rows = (
        await ctx.session.execute(
            select(Run.id, Run.kind, Run.created_at, Step.key, Step.label, *_COST_COLUMNS)
            .select_from(CostEntry)
            .join(Run, Run.id == CostEntry.run_id)
            .outerjoin(Step, Step.id == CostEntry.step_id)
            .where(CostEntry.case_id == ctx.case.id)
            .group_by(Run.id, Run.kind, Run.created_at, Step.key, Step.label)
            .order_by(func.max(CostEntry.created_at))
        )
    ).all()
    by_step = [
        CostLineOut(
            run_id=str(r.id),
            run_kind=RunKind(r.kind),
            step_key=r.key or "",
            step_label=public_step_text(r.key or "", r.label or r.key or "", None, None)[0],
            cost=_row_totals(r),
            cached=bool(r.cached),
            at=r.at or r.created_at,
        )
        for r in rows
    ]
    run_ids = [r.id for r in await ctx.runs()]
    not_run = 0
    if run_ids:
        not_run = (
            await ctx.session.execute(
                select(func.count(Step.id)).where(
                    Step.run_id.in_(run_ids),
                    Step.state.in_([StepState.SKIPPED_BUDGET, StepState.FAILED]),
                )
            )
        ).scalar_one()
    return CaseCostOut(
        crustdata_credits=float(totals.credits),
        llm_usd=float(totals.usd),
        unknown_cost_calls=totals.unknown_calls,
        credit_budget=_credit_budget(ctx.case),
        checks_not_run=int(not_run),
        by_step=by_step,
        shared_discovery=await shared_discovery_cost(ctx),
    )


@section("runs")
async def runs_section(ctx: CaseContext) -> list[RunSummaryOut]:
    runs = await ctx.runs()
    if not runs:
        return []
    costs = {
        r.run_id: r
        for r in (
            await ctx.session.execute(
                select(CostEntry.run_id, *_COST_COLUMNS[:5])
                .where(CostEntry.case_id == ctx.case.id, CostEntry.run_id.is_not(None))
                .group_by(CostEntry.run_id)
            )
        ).all()
    }
    return [
        RunSummaryOut(
            id=str(run.id),
            kind=RunKind(run.kind),
            state=RunState(run.state),
            created_at=run.created_at,
            finished_at=run.finished_at,
            cost=_row_totals(costs[run.id]) if run.id in costs else CostTotalsOut(),
        )
        for run in reversed(runs)
    ]


# --- GET /cases rows ------------------------------------------------------------------


@summary_field("id")
async def _summary_id(ctx: CaseContext) -> str:
    return str(ctx.case.id)


@summary_field("name")
async def _summary_name(ctx: CaseContext) -> str:
    return ctx.case.company_name


@summary_field("website")
async def _summary_website(ctx: CaseContext) -> str | None:
    return ctx.case.website


@summary_field("status")
async def _summary_status(ctx: CaseContext) -> CaseStatus:
    return await case_status(ctx)


@summary_field("identity_state")
async def _summary_identity(ctx: CaseContext) -> IdentityState:
    return IdentityState(ctx.case.identity_status)


@summary_field("claim_count")
async def _summary_claims(ctx: CaseContext) -> int:
    found = await ctx.session.execute(
        select(func.count(Claim.id)).where(Claim.case_id == ctx.case.id)
    )
    return int(found.scalar_one())


@summary_field("cost")
async def _summary_cost(ctx: CaseContext) -> CostTotalsOut:
    return _totals_out(await ledger.case_totals(ctx.session, ctx.workspace_id, ctx.case.id))


@summary_field("latest_run_state")
async def _summary_run_state(ctx: CaseContext) -> str | None:
    runs = await ctx.runs()
    return runs[-1].state if runs else None


def _case_ids(ctxs: list[CaseContext]) -> list[uuid.UUID]:
    return [c.case.id for c in ctxs]


async def _batch_status(
    session: AsyncSession, workspace_id: uuid.UUID, ctxs: list[CaseContext]
) -> dict[uuid.UUID, CaseStatus]:
    """`_summary_status` for every case: runs are preloaded, assessed is one query."""
    assessed = set(
        (
            await session.execute(
                select(AssessmentVersion.case_id)
                .where(AssessmentVersion.case_id.in_(_case_ids(ctxs)))
                .distinct()
            )
        ).scalars()
    )
    return {
        c.case.id: evaluate_cases.case_status(
            c.case, evaluate_cases.current_run(await c.runs()), c.case.id in assessed
        )
        for c in ctxs
    }


async def _batch_claims(
    session: AsyncSession, workspace_id: uuid.UUID, ctxs: list[CaseContext]
) -> dict[uuid.UUID, int]:
    ids = _case_ids(ctxs)
    counts = dict(
        (
            await session.execute(
                select(Claim.case_id, func.count(Claim.id))
                .where(Claim.case_id.in_(ids))
                .group_by(Claim.case_id)
            )
        ).all()
    )
    return {cid: int(counts.get(cid, 0)) for cid in ids}


async def _batch_cost(
    session: AsyncSession, workspace_id: uuid.UUID, ctxs: list[CaseContext]
) -> dict[uuid.UUID, CostTotalsOut]:
    totals = await ledger.case_totals_many(session, workspace_id, _case_ids(ctxs))
    return {cid: _totals_out(t) for cid, t in totals.items()}


register_summary_batch("status", _batch_status)
register_summary_batch("claim_count", _batch_claims)
register_summary_batch("cost", _batch_cost)


@summary_field("created_at")
async def _summary_created(ctx: CaseContext) -> datetime:
    return ctx.case.created_at


@summary_field("updated_at")
async def _summary_updated(ctx: CaseContext) -> datetime:
    runs = await ctx.runs()
    stamps = [ctx.case.created_at, *(r.updated_at for r in runs if r.updated_at)]
    return max(stamps) if stamps else datetime.now(UTC)


__all__ = [
    "CASE_DETAIL_SECTIONS",
    "CASE_SUMMARY_BATCHES",
    "CASE_SUMMARY_FIELDS",
    "CaseContext",
    "build_case_detail",
    "build_case_out",
    "build_case_summaries",
    "build_case_summary",
    "contract_source_class",
    "event_out",
    "register_section",
    "register_summary",
    "register_summary_batch",
    "section",
    "source_ref",
    "summary_field",
]
