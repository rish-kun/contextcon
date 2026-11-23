"""Case-level entry points for evaluation: strategy criteria, re-evaluation, `CaseOut`.

A case opened directly (no thesis) gets no fit score until the user gives strategy
criteria. `set_case_criteria` stores them on a thesis private to the case (a shortlist's
thesis is shared, so it is never edited from a case) and queues an `evaluate` run.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.cases import CaseOut, CaseStatus
from app.api.schemas.common import NamedUserOut
from app.api.schemas.theses import CriterionIn
from app.db import repo
from app.db.enums import RunKind, RunState
from app.db.models import Case, Criterion, Run, Thesis, User
from app.jobs import create_run
from app.jobs.events import load_run_out
from app.pipelines.evaluate.flip_step import decision_flip_step
from app.pipelines.evaluate.service import evaluate_step
from app.settings import get_settings

CASE_THESIS_STATUS = "case_criteria"
CRITERIA_TRIGGER = "strategy criteria updated"


async def _new_case_thesis(session: AsyncSession, case: Case, user_id: uuid.UUID | None) -> Thesis:
    """A fresh thesis per edit: earlier versions keep resolving their criteria labels."""
    thesis = Thesis(
        workspace_id=case.workspace_id,
        created_by=user_id,
        text=f"Strategy criteria for {case.company_name}",
        status=CASE_THESIS_STATUS,
    )
    session.add(thesis)
    await session.flush()
    case.thesis_id = thesis.id
    return thesis


async def set_case_criteria(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    case_id: uuid.UUID,
    criteria: list[CriterionIn],
    *,
    user_id: uuid.UUID | None = None,
) -> Run:
    """Replace the case's strategy criteria and queue a re-evaluation. Flushes only."""
    case = await repo.get_case(session, workspace_id, case_id)
    thesis = await _new_case_thesis(session, case, user_id)
    for i, c in enumerate(criteria):
        session.add(
            Criterion(
                thesis_id=thesis.id,
                position=i,
                label=c.label,
                kind=c.kind.value,
                dimension=c.dimension.value,
                operator=c.operator.value,
                value=c.value,
                crustdata_filter=c.crustdata_filter,
                edited=True,
            )
        )
    await session.flush()
    return await queue_evaluation(session, case, trigger=CRITERIA_TRIGGER, user_id=user_id)


async def queue_evaluation(
    session: AsyncSession, case: Case, *, trigger: str, user_id: uuid.UUID | None = None
) -> Run:
    # Imported here: app.pipelines.act imports app.pipelines.evaluate (circular at load).
    from app.pipelines.act.step import request_list_step

    return await create_run(
        session,
        workspace_id=case.workspace_id,
        kind=RunKind.EVALUATE.value,
        case_id=case.id,
        steps=[evaluate_step(trigger=trigger), decision_flip_step(), request_list_step()],
        created_by=user_id,
    )


ACTIVE_RUN_STATES = (RunState.PENDING, RunState.RUNNING)


async def _latest_run(session: AsyncSession, case: Case) -> Run | None:
    """The case's current run: the newest one still pending or running, else the newest.

    A verify run reopened by a later claim can be older than a finished evaluate run; the
    case page and the status must both follow the one that is working."""
    return (
        await session.execute(
            select(Run)
            .where(Run.case_id == case.id, Run.workspace_id == case.workspace_id)
            .order_by(Run.state.in_(ACTIVE_RUN_STATES).desc(), Run.created_at.desc(), Run.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def current_run(runs: list[Run]) -> Run | None:
    """`_latest_run` over runs already loaded oldest first."""
    active = [r for r in runs if r.state in ACTIVE_RUN_STATES]
    return (active or runs or [None])[-1]


def case_status(case: Case, latest: Run | None, assessed: bool) -> CaseStatus:
    """From the persisted run state only: `verifying` means a run is pending or running,
    so the overview never says "running" while the case page shows a finished run."""
    if latest is not None and latest.state in ACTIVE_RUN_STATES:
        return CaseStatus.verifying
    if case.identity_status != "confirmed" and case.identity_candidates:
        return CaseStatus.awaiting_identity
    if assessed:
        return CaseStatus.assessed
    if latest is None:
        return CaseStatus.verifying  # opened, its first run not yet created
    if case.identity_status != "confirmed":
        return CaseStatus.awaiting_identity
    # The run finished without an assessment: it did not get to the end.
    return CaseStatus.failed


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


async def case_out(
    session: AsyncSession,
    case: Case,
    *,
    runs: list[Run] | None = None,
    assessed: bool | None = None,
) -> CaseOut:
    """`runs` (oldest first) and `assessed` save their queries when the caller already
    has them (the case page loads both for other sections)."""
    latest = current_run(runs) if runs is not None else await _latest_run(session, case)
    if assessed is None:
        assessed = await repo.latest_assessment(session, case.workspace_id, case.id) is not None
    owner = await session.get(User, case.created_by) if case.created_by else None
    budget = case.credit_budget
    if budget is None:
        budget = Decimal(get_settings().case_credit_budget)
    return CaseOut(
        id=str(case.id),
        name=case.company_name,
        website=case.website,
        status=case_status(case, latest, assessed),
        identity_state=case.identity_status,
        crustdata_company_id=_int_or_none(case.crustdata_company_id),
        thesis_id=str(case.thesis_id) if case.thesis_id else None,
        shortlist_item_id=str(case.candidate_id) if case.candidate_id else None,
        credit_budget=float(budget),
        created_at=case.created_at,
        owner=NamedUserOut(
            user_id=str(owner.id) if owner else "",
            display_name=owner.display_name if owner else "Unknown user",
        ),
        run=await load_run_out(session, case.workspace_id, latest.id) if latest else None,
    )
