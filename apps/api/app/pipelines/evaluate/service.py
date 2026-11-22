"""Evaluate a case and keep every assessment as an immutable, numbered version.

`evaluate_case` reads the case's records, calls `rules.assess`, and inserts a new
`assessment_versions` row only when the inputs changed (same records under the same
policy give the same assessment, so an unchanged inputs hash writes nothing). Each new
version stores the full rules output and its diff from the previous version, so a
change of view is shown with its reason (PRD principle 9).

The stored `judgments` document is `{"assessment": <AssessmentVersion>, "today": <date>,
"memo": <memo sections or absent>}`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import AssessmentVersion as VersionRow
from app.domain.types import AssessmentDiff, AssessmentInputs, AssessmentVersion
from app.jobs import StepSpec
from app.pipelines.evaluate.inputs import load_inputs
from app.rules import assess, diff, inputs_hash

HANDLER = "evaluate.assess"
STEP_KEY = "evaluate"

# Called with the new assessment before it is stored; returns extra sections to keep in
# the version (the memo). Set by the memo pipeline; None keeps CP-22 standalone.
Enricher = Callable[[AsyncSession, uuid.UUID, AssessmentVersion, Any], Awaitable[dict]]


@dataclass
class EvaluationOutcome:
    created: bool
    version: VersionRow
    assessment: AssessmentVersion
    diff: AssessmentDiff | None


def stored_assessment(row: VersionRow) -> AssessmentVersion:
    return AssessmentVersion.model_validate(row.judgments["assessment"])


def stored_today(row: VersionRow) -> dt.date | None:
    raw = (row.judgments or {}).get("today")
    return dt.date.fromisoformat(raw) if raw else None


def _empty(d: AssessmentDiff) -> bool:
    return not (d.claim_changes or d.judgment_changes or d.disposition_change)


def _only_the_date_moved(inputs: AssessmentInputs, prev: VersionRow, d: AssessmentDiff) -> bool:
    """`today` is hashed (company age depends on it), so a re-run on a later day has a new
    hash. When nothing else moved and the result is identical, it is not a new view."""
    prev_today = stored_today(prev)
    if prev_today is None or not _empty(d):
        return False
    return inputs_hash(inputs.model_copy(update={"today": prev_today})) == prev.inputs_hash


async def evaluate_case(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    case_id: uuid.UUID,
    *,
    today: dt.date,
    trigger: str = "evaluate",
    run_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    enrich: Enricher | None = None,
    enrich_arg: Any = None,
) -> EvaluationOutcome:
    """Assess the case; insert a version only if the inputs changed. Flushes, no commit."""
    case = await repo.get_case(session, workspace_id, case_id)
    prev = await repo.latest_assessment(session, workspace_id, case.id)
    inputs = await load_inputs(
        session, case, today=today, version=(prev.version + 1) if prev else 1
    )
    result = assess(inputs)

    change: AssessmentDiff | None = None
    if prev is not None:
        if prev.inputs_hash == result.inputs_hash:
            return EvaluationOutcome(False, prev, stored_assessment(prev), None)
        change = diff(stored_assessment(prev), result)
        if prev.policy_version == result.policy_version and _only_the_date_moved(
            inputs, prev, change
        ):
            return EvaluationOutcome(False, prev, stored_assessment(prev), None)

    document: dict[str, Any] = {
        "assessment": result.model_dump(mode="json"),
        "today": today.isoformat(),
    }
    if enrich is not None:
        document.update(await enrich(session, case.id, result, enrich_arg))
    row = await repo.add_assessment_version(
        session,
        workspace_id,
        case.id,
        policy_version=result.policy_version,
        inputs_hash=result.inputs_hash,
        judgments=document,
        disposition=result.disposition.value,
        reasons=list(result.judgments.disposition.reasons),
        diff_from_previous=change.model_dump(mode="json") if change else None,
        trigger=trigger[:64],
        run_id=run_id,
        created_by=created_by,
    )
    return EvaluationOutcome(True, row, result, change)


def evaluate_step(*, depends_on: list[str] | tuple[str, ...] = (), trigger: str | None = None):
    """The step every verify, recheck and evaluate run ends with. It costs no credits and
    runs even when an earlier step failed or ran out of budget, so the case can still say
    which checks did not run."""
    return StepSpec(
        key=STEP_KEY,
        handler=HANDLER,
        label="Update the assessment",
        input={"trigger": trigger} if trigger else {},
        depends_on=tuple(depends_on),
        uses_budget=False,
        tolerate_failed_deps=True,
    )
