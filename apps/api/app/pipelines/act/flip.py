"""The DecisionFlip analysis a request list is ordered by.

`analysis_for_version` prefers the stored analysis (`decision_flip_analyses`, written by
the `evaluate.decision_flip` step that runs between assess and the request list). When
there is none (the step failed, or the version predates it) it computes the analysis
in memory with `rules.analyse`, the same pure code, from the stored version, the claims
and the exact criteria rows the version evaluated. Nothing is written here: the
analysis row belongs to the decision_flip step.

A version the current rules cannot replay (`ReplayMismatch`, or a stored
`not_reproducible` row) gives `None`, and the request list keeps the order
`build_request_list` gave.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Case, Thesis
from app.db.models import Criterion as CriterionRow
from app.db.models import DecisionFlipAnalysis as FlipRow
from app.domain.types import AssessmentVersion, Claim, Criterion, DecisionFlipAnalysis
from app.pipelines.evaluate.inputs import criterion_in
from app.rules import analyse
from app.rules.decision_flip import ReplayMismatch

log = logging.getLogger(__name__)

NOT_REPRODUCIBLE = "not_reproducible"


async def stored_flip(
    session: AsyncSession, workspace_id: uuid.UUID, version_id: uuid.UUID
) -> FlipRow | None:
    """The newest stored analysis of one version."""
    return (
        await session.execute(
            select(FlipRow)
            .where(
                FlipRow.workspace_id == workspace_id,
                FlipRow.assessment_version_id == version_id,
            )
            .order_by(FlipRow.created_at.desc(), FlipRow.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def version_criteria(
    session: AsyncSession, case: Case, assessment: AssessmentVersion
) -> list[Criterion]:
    """The criteria rows the version evaluated, by id, in its evaluation order. A
    criteria edit makes new rows, so an older version keeps its own."""
    order = [e.criterion_id for e in assessment.candidate.fit.evaluations]
    ids = [u for u in (_uuid(i) for i in order) if u is not None]
    if not ids:
        return []
    rows = await session.execute(
        select(CriterionRow)
        .join(Thesis, Thesis.id == CriterionRow.thesis_id)
        .where(CriterionRow.id.in_(ids), Thesis.workspace_id == case.workspace_id)
    )
    by_id = {str(r.id): criterion_in(r) for r in rows.scalars()}
    return [by_id[i] for i in order if i in by_id]


async def analysis_for_version(
    session: AsyncSession,
    case: Case,
    version: VersionRow,
    assessment: AssessmentVersion,
    claims: Mapping[str, Claim],
) -> tuple[DecisionFlipAnalysis | None, str]:
    """`(analysis, source)`; source is `stored`, `computed` or `none`."""
    row = await stored_flip(session, case.workspace_id, version.id)
    if row is not None:
        if row.state == NOT_REPRODUCIBLE:
            return None, "none"
        try:
            return DecisionFlipAnalysis.model_validate(row.payload), "stored"
        except ValidationError:  # an older document shape: recompute below
            log.warning("decision flip row %s does not validate; recomputing", row.id)
    criteria = await version_criteria(session, case, assessment)
    try:
        return analyse(assessment, claims=dict(claims), criteria=criteria), "computed"
    except ReplayMismatch:
        return None, "none"
