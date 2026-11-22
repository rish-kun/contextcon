"""DecisionFlip routes and case sections (F-decisionflip.md §7.3).

* `GET /cases/{id}` gains a `decision_flip` section: the analysis of the latest
  assessment version, or null (no assessment, or not computed). Reading never computes.
* `GET /cases` gains a `decision_flip` summary for the Pipeline board, read from columns.
* `GET /cases/{id}/decision-flip?version=N`: one version's analysis (default latest),
  with labels, claim text and the resolution against the previous version. 404 when
  the case or version does not exist; null when the version has no analysis yet.
* `POST /cases/{id}/decision-flip`: recompute for a version (default latest). Pure and
  millisecond-scale, so it runs in the request: no run, no credits, no model.
  Idempotent: 200 with the existing row when its `analysis_key` matches, else 201.

Every query is scoped to the signed-in user's workspace (`app.auth.deps` through
`cases_deps`). Fixture mode serves analyses computed by the real rules.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import fixture_decision_flip, fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.cases_deps import Actor, CaseSession
from app.api.cases_sections import CaseContext, register_section, register_summary
from app.api.schemas.common import ErrorOut
from app.api.schemas.decision_flip import (
    DecisionFlipOut,
    DecisionFlipRecomputeIn,
    DecisionFlipSummaryOut,
    FlipResolutionItemOut,
    FlipResolutionOut,
)
from app.db import repo
from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Case, Thesis
from app.db.models import Claim as ClaimRow
from app.db.models import Criterion as CriterionRow
from app.db.models import DecisionFlipAnalysis as FlipRow
from app.db.repo import NotFound
from app.domain.types import AssessmentDiff, AssessmentVersion, DecisionFlipAnalysis
from app.pipelines.evaluate.flip import (
    flip_for_version,
    flip_of_version,
    latest_flip,
    stored_analysis,
)
from app.pipelines.evaluate.service import stored_assessment

router = make_router(prefix="/cases", tags=["cases"])
log = logging.getLogger(__name__)

CONFLICT = {409: {"model": ErrorOut, "description": "No assessment to analyse."}}


# --- Presenting a stored analysis ----------------------------------------------------


def _uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


def _humanise(value: str) -> str:
    return value.replace("_", " ").capitalize()


async def _labels(
    session: AsyncSession, case: Case, analysis: DecisionFlipAnalysis
) -> dict[str, dict[str, str | None]]:
    """`label` and `claim_text` per item, from the rows as they are now (scrubbed text
    shows through, as in the request list)."""
    claim_ids = [u for u in (_uuid(i.claim_id) for i in analysis.items) if u]
    criterion_ids = [u for u in (_uuid(i.criterion_id) for i in analysis.items) if u]
    claims: dict[str, ClaimRow] = {}
    if claim_ids:
        rows = await session.execute(
            select(ClaimRow).where(ClaimRow.case_id == case.id, ClaimRow.id.in_(claim_ids))
        )
        claims = {str(r.id): r for r in rows.scalars()}
    criteria: dict[str, str] = {}
    if criterion_ids:
        rows = await session.execute(
            select(CriterionRow.id, CriterionRow.label)
            .join(Thesis, Thesis.id == CriterionRow.thesis_id)
            .where(CriterionRow.id.in_(criterion_ids), Thesis.workspace_id == case.workspace_id)
        )
        criteria = {str(i): label for i, label in rows.all()}
    out: dict[str, dict[str, str | None]] = {}
    for item in analysis.items:
        text: str | None = None
        if item.claim_id is not None:
            row = claims.get(item.claim_id)
            label = _humanise(row.category if row else (item.check or "claim"))
            text = row.original_text if row else None
        elif item.criterion_id is not None:
            label = criteria.get(item.criterion_id, item.criterion_id)
        elif item.check is not None:
            label = f"{_humanise(item.check)} (not claimed yet)"
        elif item.id == "identity":
            label = "Legal entity"
        else:
            label = "Financial inputs"
        out[item.id] = {"label": label, "claim_text": text}
    return out


def _state_now(item_id: str, a: AssessmentVersion) -> str | None:
    kind, _, ref = item_id.partition(":")
    if kind == "claim":
        return next((o.status.value for o in a.outcomes if o.claim_id == ref), None)
    if kind == "criterion":
        evals = a.candidate.fit.evaluations
        return next((e.result.value for e in evals if e.criterion_id == ref), None)
    return None


async def _resolution(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    case: Case,
    version: VersionRow,
    a: DecisionFlipAnalysis,
    labels: dict[str, dict[str, str | None]],
) -> FlipResolutionOut | None:
    """This version's items against the previous version's analysis, by item id (§4)."""
    if version.previous_version_id is None:
        return None
    previous_row = await flip_of_version(session, workspace_id, version.previous_version_id)
    if previous_row is None:
        return None
    previous = stored_analysis(previous_row)
    if previous is None:  # not reproducible: nothing to compare against
        return None
    labels = {**await _labels(session, case, previous), **labels}
    now = {i.id: i for i in a.items}
    assessment = stored_assessment(version)
    diff = (
        AssessmentDiff.model_validate(version.diff_from_previous)
        if version.diff_from_previous
        else None
    )
    added = {c.claim_id: c.evidence_added for c in (diff.claim_changes if diff else [])}
    items: list[FlipResolutionItemOut] = []
    for before in previous.items:
        current = now.get(before.id)
        if current is not None:
            settled = current.current_state in ("contradicted", "fail")
            outcome = (
                "settled_against"
                if settled and current.current_state != before.current_state
                else "still_open"
            )
            state = current.current_state
        else:
            state = _state_now(before.id, assessment)
            outcome = "settled_against" if state in ("contradicted", "fail") else "resolved"
        items.append(
            FlipResolutionItemOut(
                item_id=before.id,
                label=labels.get(before.id, {}).get("label") or "",
                outcome=outcome,
                was_blocker=before.decision_blocker,
                current_state=state,
                evidence_ids=list(added.get(before.claim_id or "", [])),
            )
        )
    seen = {i.id for i in previous.items}
    items += [
        FlipResolutionItemOut(
            item_id=i.id,
            label=labels.get(i.id, {}).get("label") or "",
            outcome="new",
            was_blocker=False,
            current_state=i.current_state,
        )
        for i in a.items
        if i.id not in seen
    ]
    return FlipResolutionOut(
        previous_version=previous.assessment_version,
        previous_blockers=sum(1 for i in previous.items if i.decision_blocker),
        resolved_blockers=sum(1 for i in items if i.was_blocker and i.outcome == "resolved"),
        items=items,
    )


async def present(
    session: AsyncSession, workspace_id: uuid.UUID, case: Case, version: VersionRow, row: FlipRow
) -> DecisionFlipOut:
    analysis = stored_analysis(row)  # None for a not_reproducible row
    labels = await _labels(session, case, analysis) if analysis else {}
    resolution = (
        await _resolution(session, workspace_id, case, version, analysis, labels)
        if analysis
        else None
    )
    out = DecisionFlipOut.model_validate(
        {
            **row.payload,
            "analysis_id": str(row.id),
            "blocker_count": row.blocker_count,
            "created_at": row.created_at,
            "resolution": resolution,
        }
    )
    return out.model_copy(
        update={"items": [i.model_copy(update=labels.get(i.id, {})) for i in out.items]}
    )


# --- Case sections ------------------------------------------------------------------


async def decision_flip_section(ctx: CaseContext) -> DecisionFlipOut | None:
    found = await latest_flip(ctx.session, ctx.workspace_id, ctx.case.id)
    if found is None or found[1] is None:
        return None
    version, row = found
    return await present(ctx.session, ctx.workspace_id, ctx.case, version, row)


async def decision_flip_summary(ctx: CaseContext) -> DecisionFlipSummaryOut | None:
    version = await repo.latest_assessment(ctx.session, ctx.workspace_id, ctx.case.id)
    if version is None:
        return None
    found = (
        await ctx.session.execute(
            select(FlipRow.state, FlipRow.target, FlipRow.blocker_count)
            .where(
                FlipRow.workspace_id == ctx.workspace_id,
                FlipRow.assessment_version_id == version.id,
            )
            .order_by(FlipRow.created_at.desc(), FlipRow.id.desc())
            .limit(1)
        )
    ).first()
    if found is None:
        return None
    return DecisionFlipSummaryOut(
        state=found.state,
        next_disposition=found.target,
        blockers_to_next=found.blocker_count,
        assessment_version=version.version,
    )


def _never_fails(builder):
    """A DecisionFlip problem never breaks the case page or the board: log, show null."""

    async def safe(ctx: CaseContext):
        try:
            async with ctx.session.begin_nested():
                return await builder(ctx)
        except Exception:
            log.exception("decision_flip section failed for case %s", ctx.case.id)
            return None

    return safe


register_section("decision_flip", _never_fails(decision_flip_section))
register_summary("decision_flip", _never_fails(decision_flip_summary))


# --- Routes ---------------------------------------------------------------------------


def _fixture(case_id: str) -> DecisionFlipOut:
    if fixtures.case_out(case_id) is None:
        not_found("Case")
    if case_id != fixtures.CASE_ID:
        not_found("Assessment")  # the ambiguous case has no assessment yet
    return fixture_decision_flip.SCENARIOS["two_blockers"](case_id)


async def _case_and_version(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: str, version: int | None
) -> tuple[Case, VersionRow | None]:
    case_uuid = _uuid(case_id)
    if case_uuid is None:
        not_found("Case")
    try:
        case = await repo.get_case(session, workspace_id, case_uuid)
    except NotFound:
        not_found("Case")
    if version is None:
        return case, await repo.latest_assessment(session, workspace_id, case.id)
    row = (
        await session.execute(
            select(VersionRow).where(VersionRow.case_id == case.id, VersionRow.version == version)
        )
    ).scalar_one_or_none()
    if row is None:
        not_found("Assessment version")
    return case, row


@router.get("/{case_id}/decision-flip", response_model=DecisionFlipOut | None)
async def get_decision_flip(
    case_id: str,
    actor: Actor,
    session: CaseSession,
    version: int | None = Query(default=None, ge=1, description="Default: the latest version."),
) -> DecisionFlipOut | None:
    """What would change the decision for one assessment version. Hypothetical: every
    simulated outcome is marked so. Null when the version has not been analysed yet."""
    if actor is None or session is None:
        return fixture_or_501("DecisionFlip", lambda: _fixture(case_id))
    case, row = await _case_and_version(session, actor.workspace_id, case_id, version)
    if row is None:
        not_found("Assessment")
    flip = await flip_of_version(session, actor.workspace_id, row.id)
    if flip is None:
        return None
    return await present(session, actor.workspace_id, case, row, flip)


@router.post(
    "/{case_id}/decision-flip",
    response_model=DecisionFlipOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": DecisionFlipOut, "description": "Already computed."}, **CONFLICT},
)
async def recompute_decision_flip(
    case_id: str,
    actor: Actor,
    session: CaseSession,
    response: Response,
    body: DecisionFlipRecomputeIn | None = None,
) -> DecisionFlipOut:
    """Compute the analysis for a version (default latest). Costs nothing: no run, no
    credits, no model. 200 with the existing analysis when nothing changed."""
    if actor is None or session is None:
        response.status_code = status.HTTP_200_OK
        return fixture_or_501("DecisionFlip", lambda: _fixture(case_id))
    case, row = await _case_and_version(
        session, actor.workspace_id, case_id, body.version if body else None
    )
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The case has no assessment to analyse yet.")
    result = await flip_for_version(session, actor.workspace_id, row)
    await session.commit()
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return await present(session, actor.workspace_id, case, row, result.row)
