"""CP-22/CP-25 sections of `GET /cases/{id}`, registered on `app.api.cases_sections`.

Registered here: opportunity (fit recomputed with case evidence), assessment, memo,
risks, documents and deletions. The source record and the cost readout extend the
CP-19 builders: sources gain the request hash, an excerpt and its retention state;
cost also counts calls that started and never reported a cost as unknown.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cases_sections import CASE_DETAIL_SECTIONS, CaseContext, register_section
from app.api.cases_sections import build_case_detail as build_sections
from app.api.schemas.assessments import AssessmentVersionOut, FitState
from app.api.schemas.cases import (
    CaseCostOut,
    CaseDetail,
    CaseMemoOut,
    ComparablesOut,
    OpportunityOut,
    RiskItemOut,
)
from app.api.schemas.common import CriterionDimension, SourceRecordOut
from app.api.schemas.documents import DeletionRecordOut, DocumentOut
from app.api.schemas.theses import CriterionOut
from app.db import repo
from app.db.models import AssessmentVersion, Claim, Criterion, Thesis
from app.domain.types import AssessmentVersion as Assessment
from app.pipelines.evaluate.inputs import OPERATORS
from app.pipelines.evaluate.present import Lookups, load_lookups, version_out
from app.pipelines.evaluate.snapshot import Snapshot, load_snapshot
from app.pipelines.memo.cost import cost_line, unrecorded_calls
from app.pipelines.memo.records import (
    Retention,
    deletions_out,
    documents_out,
    load_retention,
    retention_notice,
    source_retention,
)
from app.pipelines.memo.sections import MemoContext, memo_out, risk_items

# The CP-19 builders these sections extend (captured before they are replaced).
_BASE_SOURCES = CASE_DETAIL_SECTIONS["sources"]
_BASE_COST = CASE_DETAIL_SECTIONS["cost"]


@dataclass
class _State:
    """Per-request material shared by the sections below (loaded once)."""

    latest: AssessmentVersion | None = None
    snapshot: Snapshot | None = None
    assessment: Assessment | None = None
    lookups: Lookups = field(default_factory=Lookups)
    version: AssessmentVersionOut | None = None
    retention: Retention = field(default_factory=Retention)
    documents: list[DocumentOut] = field(default_factory=list)
    claim_numbers: dict[str, int] = field(default_factory=dict)
    thesis: Thesis | None = None
    criteria: list[Criterion] = field(default_factory=list)
    memo: CaseMemoOut | None = None
    cost: CaseCostOut | None = None


async def _state(ctx: CaseContext) -> _State:
    cached = ctx.__dict__.get("_cp25")
    if cached is not None:
        return cached
    s = _State()
    case = ctx.case
    s.latest = await ctx.latest_assessment()
    if s.latest is not None:
        s.snapshot = await load_snapshot(ctx.session, s.latest)
        s.assessment = s.snapshot.assessment
        s.lookups = await load_lookups(ctx.session, case.id, [s.snapshot])
        s.version = version_out(s.snapshot, s.lookups)
    s.retention = await load_retention(ctx.session, case)
    s.documents = await documents_out(ctx.session, case)
    claims = (
        await ctx.session.execute(
            select(Claim.id).where(Claim.case_id == case.id).order_by(Claim.created_at, Claim.id)
        )
    ).scalars()
    s.claim_numbers = {str(cid): n for n, cid in enumerate(claims, start=1)}
    if case.thesis_id is not None:
        thesis = await ctx.session.get(Thesis, case.thesis_id)
        if thesis is not None and thesis.workspace_id == ctx.workspace_id:
            s.thesis = thesis
            s.criteria = list(
                (
                    await ctx.session.execute(
                        select(Criterion)
                        .where(Criterion.thesis_id == thesis.id)
                        .order_by(Criterion.position)
                    )
                ).scalars()
            )
    ctx.__dict__["_cp25"] = s
    return s


# --- Opportunity ---------------------------------------------------------------------


def criterion_out(row: Criterion) -> CriterionOut | None:
    op = OPERATORS.get(row.operator)
    if op is None:
        return None
    try:
        dimension = CriterionDimension(row.dimension)
    except ValueError:
        dimension = CriterionDimension.other
    return CriterionOut(
        id=str(row.id),
        position=row.position,
        label=row.label,
        kind=row.kind,
        dimension=dimension,
        operator=op.value,
        value=row.value,
        crustdata_filter=row.crustdata_filter,
        assessed_from_evidence=row.crustdata_filter is None,
        edited=row.edited,
    )


async def opportunity_section(ctx: CaseContext) -> OpportunityOut:
    s = await _state(ctx)
    fit = s.version.judgments.opportunity_fit if s.version else None
    if fit is not None:
        state = fit.state
    elif ctx.case.identity_status != "confirmed":
        state = FitState.identity_unresolved
    elif not s.criteria:
        state = FitState.awaiting_strategy_criteria
    else:
        state = FitState.unavailable
    memo = await memo_section(ctx)
    relevance = next(
        (x.drafted_text for x in (memo.sections if memo else []) if x.key == "opportunity"), None
    )
    return OpportunityOut(
        thesis_id=str(s.thesis.id) if s.thesis else None,
        thesis_text=s.thesis.text if s.thesis else None,
        criteria=[c for c in (criterion_out(r) for r in s.criteria) if c is not None],
        fit_state=state,
        fit=fit.fit if fit else None,
        assessable_pct=fit.assessable_pct if fit else 0,
        criterion_results=fit.criterion_results if fit else [],
        relevance=[relevance] if relevance else [],
    )


# --- Assessment, memo, risks ---------------------------------------------------------


async def assessment_section(ctx: CaseContext) -> AssessmentVersionOut | None:
    return (await _state(ctx)).version


async def _memo_context(ctx: CaseContext, s: _State) -> MemoContext:
    events = await ctx.section_value("events")
    comparables = await ctx.section_value("comparables")
    return MemoContext(
        lookups=s.lookups,
        claim_numbers=s.claim_numbers,
        thesis_text=s.thesis.text if s.thesis else None,
        company_name=ctx.case.company_name,
        events=list(events or []),
        comparables=comparables if isinstance(comparables, ComparablesOut) else None,
        retention=s.retention,
        retention_notice=retention_notice(s.documents),
        cost_line=cost_line(await cost_section(ctx)),
        source_count=len(await ctx.sources()),
    )


async def memo_section(ctx: CaseContext) -> CaseMemoOut | None:
    s = await _state(ctx)
    if s.snapshot is None:
        return None
    if s.memo is None:
        s.memo = await memo_out(ctx.session, s.snapshot, await _memo_context(ctx, s))
    return s.memo


async def risks_section(ctx: CaseContext) -> list[RiskItemOut]:
    s = await _state(ctx)
    if s.assessment is None:
        return []
    return risk_items(s.assessment, MemoContext(lookups=s.lookups, claim_numbers=s.claim_numbers))


# --- Retention, sources, cost --------------------------------------------------------


async def documents_section(ctx: CaseContext) -> list[DocumentOut]:
    return (await _state(ctx)).documents


async def deletions_section(ctx: CaseContext) -> list[DeletionRecordOut]:
    return deletions_out((await _state(ctx)).retention)


async def sources_section(ctx: CaseContext) -> list[SourceRecordOut]:
    """The CP-19 source record plus what reproduces each call and its retention state."""
    base: list[SourceRecordOut] = await _BASE_SOURCES(ctx)
    extra = await source_retention(ctx.session, ctx.case, (await _state(ctx)).retention)
    return [r.model_copy(update=extra.get(r.source_id, {})) for r in base]


async def cost_section(ctx: CaseContext) -> CaseCostOut:
    """The CP-19 readout, with calls that never reported a cost counted as unknown."""
    s = await _state(ctx)
    if s.cost is None:
        base: CaseCostOut = await _BASE_COST(ctx)
        extra = await unrecorded_calls(ctx.session, ctx.case)
        s.cost = base.model_copy(update={"unknown_cost_calls": base.unknown_cost_calls + extra})
    return s.cost


for _key, _builder in (
    ("opportunity", opportunity_section),
    ("assessment", assessment_section),
    ("memo", memo_section),
    ("risks", risks_section),
    ("documents", documents_section),
    ("deletions", deletions_section),
    ("sources", sources_section),
    ("cost", cost_section),
):
    register_section(_key, _builder)


async def build_case_detail(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> CaseDetail:
    """`GET /cases/{id}` for a case id; raises `repo.NotFound` outside the workspace."""
    case = await repo.get_case(session, workspace_id, case_id)
    return await build_sections(session, workspace_id, case)
