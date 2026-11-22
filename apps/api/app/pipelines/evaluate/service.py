"""Evaluate a case and keep every assessment as an immutable, numbered version.

`evaluate_case` reads the case's records, calls `rules.assess`, and inserts a new
`assessment_versions` row only when the inputs changed (same records under the same
policy give the same assessment, so an unchanged inputs hash writes nothing). Each new
version stores the full rules output and its diff from the previous version, so a
change of view is shown with its reason (PRD principle 9).

The stored `judgments` document is `{"assessment": <public skeleton>, "today": <date>,
"confidential": {"kind", "removed_on"}, "memo": <memo sections>}`. Seller-derived text
lives in an expiring confidential payload instead (`app.pipelines.evaluate.snapshot`);
read versions through `load_snapshot`. Each version also records the documents that
triggered it and every document and evidence row it rests on.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Case, Evidence, Source
from app.domain.types import AssessmentDiff, AssessmentInputs, AssessmentVersion
from app.jobs import StepSpec
from app.pipelines.evaluate.inputs import load_inputs
from app.pipelines.evaluate.snapshot import (
    SNAPSHOT_KIND,
    load_snapshot,
    redact_assessment,
    redact_diff,
    removed_text,
    snapshot_deadline,
    store_snapshot,
)
from app.rules import assess, diff, inputs_hash

HANDLER = "evaluate.assess"
STEP_KEY = "evaluate"

# Called with the new assessment before it is stored; returns extra sections to keep in
# the version (the memo). Set by the memo pipeline; None keeps CP-22 standalone.
Enricher = Callable[[AsyncSession, Case, AssessmentInputs, AssessmentVersion, Any], Awaitable[dict]]


@dataclass
class EvaluationOutcome:
    created: bool
    version: VersionRow
    assessment: AssessmentVersion
    diff: AssessmentDiff | None


def stored_assessment(row: VersionRow) -> AssessmentVersion:
    """The public skeleton stored in the row (statuses, ids, scores). For the full
    snapshot while retention allows, use `snapshot.load_snapshot`."""
    return AssessmentVersion.model_validate(row.judgments["assessment"])


SELLER_DOCUMENTS_TRIGGER = "seller documents"


def public_trigger(trigger: str) -> str:
    """The trigger as stored on the immutable version. Uploaded file names are
    confidential and the documents are recorded by id (`trigger_document_ids`), so a
    "seller documents <names>" trigger keeps only its kind."""
    if trigger.casefold().startswith(SELLER_DOCUMENTS_TRIGGER):
        return SELLER_DOCUMENTS_TRIGGER
    return trigger[:64]


def consumed_evidence_ids(a: AssessmentVersion) -> list[str]:
    j = a.judgments
    ids = {r.evidence_id for o in a.outcomes for r in o.evidence}
    ids |= {i for e in j.opportunity_fit.evaluations for i in e.evidence_ids}
    ids |= {i for sig in j.business.signals for i in sig.evidence_ids}
    ids |= {f.evidence_id for f in j.financial.figures}
    return sorted(ids)


async def _documents_of(
    session: AsyncSession, case_id: uuid.UUID, evidence_ids: list[str]
) -> list[str]:
    wanted = []
    for i in evidence_ids:
        try:
            wanted.append(uuid.UUID(i))
        except ValueError:
            continue
    if not wanted:
        return []
    rows = await session.execute(
        select(Source.document_id)
        .join(Evidence, Evidence.source_id == Source.id)
        .where(
            Evidence.id.in_(wanted),
            Evidence.case_id == case_id,
            Source.document_id.is_not(None),
        )
        .distinct()
    )
    return sorted(str(d) for d in rows.scalars())


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
    trigger_document_ids: list[str] | None = None,
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
        previous = (await load_snapshot(session, prev)).assessment
        if prev.inputs_hash == result.inputs_hash:
            return EvaluationOutcome(False, prev, previous, None)
        change = diff(previous, result)
        if prev.policy_version == result.policy_version and _only_the_date_moved(
            inputs, prev, change
        ):
            return EvaluationOutcome(False, prev, previous, None)

    deadline = await snapshot_deadline(session, case.id)
    placeholder = removed_text(deadline.date())
    document: dict[str, Any] = {
        "assessment": redact_assessment(result.model_dump(mode="json"), placeholder),
        "today": today.isoformat(),
        "confidential": {"kind": SNAPSHOT_KIND, "removed_on": deadline.date().isoformat()},
    }
    evidence_ids = consumed_evidence_ids(result)
    new_evidence = sorted(
        {i for c in (change.claim_changes if change else []) for i in c.evidence_added}
    )
    triggers = sorted(
        set(trigger_document_ids or []) | set(await _documents_of(session, case.id, new_evidence))
    )
    if enrich is not None:
        document.update(await enrich(session, case, inputs, result, enrich_arg))
    row = await repo.add_assessment_version(
        session,
        workspace_id,
        case.id,
        policy_version=result.policy_version,
        inputs_hash=result.inputs_hash,
        judgments=document,
        disposition=result.disposition.value,
        reasons=list(result.judgments.disposition.reasons),
        diff_from_previous=redact_diff(
            change.model_dump(mode="json") if change else None, placeholder
        ),
        trigger=public_trigger(trigger),
        trigger_document_ids=triggers,
        document_ids=await _documents_of(session, case.id, evidence_ids),
        evidence_ids=evidence_ids,
        run_id=run_id,
        created_by=created_by,
    )
    await store_snapshot(
        session,
        row,
        workspace_id=workspace_id,
        assessment=result,
        diff=change,
        delete_after=deadline,
        run_id=run_id,
    )
    return EvaluationOutcome(True, row, result, change)


def evaluate_step(
    *,
    depends_on: list[str] | tuple[str, ...] = (),
    trigger: str | None = None,
    document_ids: list[str] | tuple[str, ...] = (),
):
    """The step every verify, recheck and evaluate run ends with. It costs no credits and
    runs even when an earlier step failed or ran out of budget, so the case can still say
    which checks did not run. A recheck passes the uploaded `document_ids` that caused
    it; they are recorded on the new version."""
    step_input: dict[str, Any] = {}
    if trigger:
        step_input["trigger"] = trigger
    if document_ids:
        step_input["document_ids"] = [str(d) for d in document_ids]
    return StepSpec(
        key=STEP_KEY,
        handler=HANDLER,
        label="Update the assessment",
        input=step_input,
        depends_on=tuple(depends_on),
        uses_budget=False,
        tolerate_failed_deps=True,
    )
