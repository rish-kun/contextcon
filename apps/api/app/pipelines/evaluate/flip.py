"""DecisionFlip persistence: one immutable analysis row per (assessment version, key).

`flip_for_version` reads the *stored* assessment version (its public skeleton, so the
result is the same before and after retention scrubs the confidential snapshot), runs
`rules.decision_flip.analyse` on it and inserts a `decision_flip_analyses` row unless
one with the same `analysis_key` exists. It is pure apart from that insert: no run, no
credits, no model. A new `flip_version` or materiality gives a new key and a new row;
readers take the newest row of a version.

The stored version lacks what the rules need beside it, so it is passed in as the
version was assessed: the claims (wording picks an event's settling document;
materiality mirrors `load_inputs`, which does not read `claims.material`) and the
exact criteria rows it evaluated, by id (weights and the dimension behind the
must-have mapping; a criteria edit makes new rows, so old versions keep theirs).

When the current rules do not reproduce a version (one assessed under an older
policy), a row with state `not_reproducible` is stored instead, so the run carries on,
the UI can say why, and a retry finds that row rather than failing again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Case, Thesis
from app.db.models import Claim as ClaimRow
from app.db.models import Criterion as CriterionRow
from app.db.models import DecisionFlipAnalysis as FlipRow
from app.domain.enums import ClaimCategory
from app.domain.types import (
    MINIMUM_SET_LABEL,
    AssessmentVersion,
    Claim,
    Criterion,
    DecisionFlipAnalysis,
)
from app.pipelines.evaluate.inputs import claim_components, criterion_in
from app.pipelines.evaluate.service import stored_assessment
from app.rules import decision_flip
from app.rules.decision_flip import FLIP_VERSION, ReplayMismatch

# Stored instead of an analysis when the current rules do not reproduce the version.
NOT_REPRODUCIBLE = "not_reproducible"
NOT_REPRODUCIBLE_TEXT = (
    "This version was assessed under rules that no longer reproduce it, so what would "
    "change it cannot be worked out. Re-run the assessment to analyse it."
)

__all__ = [
    "NOT_REPRODUCIBLE",
    "FlipResult",
    "ReplayMismatch",
    "analyse_version",
    "blocker_count",
    "flip_for_version",
    "latest_flip",
    "flip_of_version",
    "stored_analysis",
]


@dataclass
class FlipResult:
    created: bool
    row: FlipRow

    @property
    def analysis(self) -> DecisionFlipAnalysis | None:
        return stored_analysis(self.row)


def blocker_count(analysis: DecisionFlipAnalysis) -> int:
    return sum(1 for i in analysis.items if i.decision_blocker)


def stored_analysis(row: FlipRow) -> DecisionFlipAnalysis | None:
    """The stored analysis; None for a `not_reproducible` row."""
    if row.state == NOT_REPRODUCIBLE:
        return None
    return DecisionFlipAnalysis.model_validate(row.payload)


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def version_claims(
    session: AsyncSession, case_id: uuid.UUID, assessment: AssessmentVersion
) -> dict[str, Claim]:
    """The version's claims as the rules see them (category, components, wording)."""
    ids = [u for u in (_uuid(o.claim_id) for o in assessment.outcomes) if u is not None]
    if not ids:
        return {}
    rows = await session.execute(
        select(ClaimRow).where(ClaimRow.case_id == case_id, ClaimRow.id.in_(ids))
    )
    out: dict[str, Claim] = {}
    for row in rows.scalars():
        try:
            category = ClaimCategory(row.category)
        except ValueError:
            category = ClaimCategory.OTHER
        out[str(row.id)] = Claim(
            id=str(row.id),
            text=row.original_text or "",
            category=category,
            components=claim_components(row.components),
        )
    return out


async def version_criteria(
    session: AsyncSession, case: Case, assessment: AssessmentVersion
) -> list[Criterion]:
    """The criteria rows the version evaluated, by id, in its evaluation order."""
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


async def analyse_version(
    session: AsyncSession, case: Case, version: VersionRow
) -> tuple[DecisionFlipAnalysis | None, dict]:
    """Analyse a stored version: `(analysis, payload)`, or `(None, payload)` with a
    `not_reproducible` payload when the current rules do not reproduce it."""
    assessment = stored_assessment(version)
    claims = await version_claims(session, version.case_id, assessment)
    criteria = await version_criteria(session, case, assessment)
    try:
        analysis = decision_flip.analyse(assessment, claims=claims, criteria=criteria)
    except ReplayMismatch as exc:
        return None, _not_reproducible(assessment, claims, str(exc))
    return analysis, analysis.model_dump(mode="json")


def _not_reproducible(a: AssessmentVersion, claims: dict[str, Claim], reason: str) -> dict:
    materiality = {
        o.claim_id: (claims[o.claim_id].material if o.claim_id in claims else True)
        for o in a.outcomes
    }
    decision = a.judgments.disposition
    return {
        "hypothetical": True,
        "case_id": a.case_id,
        "assessment_version": a.version,
        "policy_version": a.policy_version,
        "inputs_hash": a.inputs_hash,
        "flip_version": FLIP_VERSION,
        "analysis_key": decision_flip.analysis_key(a.inputs_hash, a.policy_version, materiality),
        "selection_basis": "fewest_checks",
        "selection_label": MINIMUM_SET_LABEL,
        "state": NOT_REPRODUCIBLE,
        "not_reproducible_reason": reason,
        "current": decision.disposition.value,
        "current_rule": decision.rule,
        "current_reasons": list(decision.reasons),
        "target": None,
        "ceiling": None,
        "items": [],
        "minimal_sets": [],
        "minimum_evidence": None,
        "worst_if_contradicted": None,
        "next_best_action": {
            "action": "none",
            "text": NOT_REPRODUCIBLE_TEXT,
            "item_ids": [],
            "documents": [],
            "conditions": [],
        },
        "search": "exhaustive",
        "greedy": False,
        "evaluations": 0,
    }


async def _row(session: AsyncSession, version_id: uuid.UUID, key: str) -> FlipRow | None:
    return (
        await session.execute(
            select(FlipRow).where(
                FlipRow.assessment_version_id == version_id, FlipRow.analysis_key == key
            )
        )
    ).scalar_one_or_none()


async def flip_for_version(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    version: VersionRow,
    *,
    run_id: uuid.UUID | None = None,
) -> FlipResult:
    """The analysis of `version`, inserted once. Idempotent by `analysis_key`: a second
    call (a retried step, a repeated POST, a concurrent writer) returns the existing row
    with `created=False`. Never raises for a version the rules cannot replay: it stores
    a `not_reproducible` row. Flushes, no commit."""
    case = await repo.get_case(session, workspace_id, version.case_id)  # workspace guard
    analysis, payload = await analyse_version(session, case, version)
    key = payload["analysis_key"]
    existing = await _row(session, version.id, key)
    if existing is not None:
        return FlipResult(False, existing)
    inserted = (
        await session.execute(
            insert(FlipRow)
            .values(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                case_id=case.id,
                assessment_version_id=version.id,
                analysis_key=key,
                policy_version=payload["policy_version"],
                inputs_hash=payload["inputs_hash"],
                flip_version=payload["flip_version"],
                state=payload["state"],
                target=payload["target"],
                blocker_count=blocker_count(analysis) if analysis else 0,
                payload=payload,
                run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=["assessment_version_id", "analysis_key"])
            .returning(FlipRow.id)
        )
    ).scalar_one_or_none()
    row = await _row(session, version.id, key)
    assert row is not None
    return FlipResult(inserted is not None, row)


async def flip_of_version(
    session: AsyncSession, workspace_id: uuid.UUID, version_id: uuid.UUID
) -> FlipRow | None:
    """The newest analysis of one version, or None when it has not been computed."""
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


async def latest_flip(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> tuple[VersionRow, FlipRow | None] | None:
    """The latest assessment version of the case and its analysis (None if not
    computed); None when the case has no assessment."""
    version = await repo.latest_assessment(session, workspace_id, case_id)
    if version is None:
        return None
    return version, await flip_of_version(session, workspace_id, version.id)
