"""Case routes. Create/identity/verify/list/detail: CP-19 (detail sections are extended
through `app.api.cases_sections`). Criteria and assessments: CP-22."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import cases_service, fixtures
from app.api._base import fixture_or_501, fixtures_enabled, make_router, not_found
from app.api.cases_deps import Actor, CaseSession
from app.api.cases_sections import build_case_detail, build_case_summary
from app.api.schemas.assessments import AssessmentVersionOut
from app.api.schemas.cases import (
    CaseCreate,
    CaseCriteriaIn,
    CaseDetail,
    CaseOut,
    CaseSummary,
    IdentityPickIn,
)
from app.api.schemas.runs import RunOut
from app.auth.deps import CurrentUser, WorkspaceId
from app.db.models import AssessmentVersion, Case
from app.db.repo import NotFound, list_case_children
from app.db.repo import get_case as repo_get_case
from app.db.repo import list_cases as repo_list_cases
from app.db.session import get_session
from app.jobs import events as run_events
from app.pipelines import evaluate

router = make_router(prefix="/cases", tags=["cases"])


# --- Case access -------------------------------------------------------------------
# The workspace comes from the signed-in user (`app.auth.deps`, 401 without a session).
# Fixture mode needs neither a workspace nor a database, so both resolve to None there.


async def case_workspace(workspace_id: WorkspaceId) -> uuid.UUID | None:
    return None if fixtures_enabled() else workspace_id


async def case_session() -> AsyncIterator[AsyncSession | None]:
    if fixtures_enabled():
        yield None
        return
    async for session in get_session():
        yield session


Workspace = Annotated[uuid.UUID | None, Depends(case_workspace)]
Session = Annotated[AsyncSession | None, Depends(case_session)]


def _case_uuid(case_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(case_id)
    except ValueError:
        not_found("Case")


def _fixture_case(case_id: str) -> CaseOut:
    case = fixtures.case_out(case_id)
    if case is None:
        not_found("Case")
    return case


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(body: CaseCreate, actor: Actor, session: CaseSession) -> CaseOut:
    """Open a case from a shortlist item, or from a name and website. Starts a verify run."""
    if actor is None or session is None:
        return fixture_or_501("CP-19", lambda: _fixture_case(fixtures.CASE_ID))
    case = await cases_service.create_case(session, actor, body)
    return await evaluate.case_out(session, case)


@router.get("", response_model=list[CaseSummary])
async def list_cases(actor: Actor, session: CaseSession) -> list[CaseSummary]:
    """Cases dashboard: disposition, fit with coverage, and cost per case."""
    if actor is None or session is None:
        return fixture_or_501("CP-25", fixtures.case_summaries)
    cases = await repo_list_cases(session, actor.workspace_id)
    return [await build_case_summary(session, actor.workspace_id, c) for c in cases]


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(case_id: str, actor: Actor, session: CaseSession) -> CaseDetail:
    """The finished-case memo aggregate, sections in PRD order."""

    def build() -> CaseDetail:
        detail = fixtures.case_detail(case_id)
        if detail is None:
            not_found("Case")
        return detail

    if actor is None or session is None:
        return fixture_or_501("CP-25", build)
    try:
        case = await _load_case(session, actor.workspace_id, case_id)
    except NotFound:
        not_found("Case")
    return await build_case_detail(session, actor.workspace_id, case)


@router.post("/{case_id}/identity", response_model=CaseOut)
async def pick_identity(
    case_id: str, body: IdentityPickIn, actor: Actor, session: CaseSession
) -> CaseOut:
    """Pick one candidate when identity is ambiguous or unresolved. Records who and when."""
    if actor is None or session is None:
        return fixture_or_501("CP-19", lambda: _fixture_case(case_id))
    try:
        case = await cases_service.pick_identity(session, actor, case_id, body)
    except NotFound:
        not_found("Case")
    return await evaluate.case_out(session, case)


@router.post("/{case_id}/verify", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_verify(case_id: str, actor: Actor, session: CaseSession) -> RunOut:
    """Start (or re-run) verification for the case."""

    def build() -> RunOut:
        case = _fixture_case(case_id)
        assert case.run is not None
        return case.run

    if actor is None or session is None:
        return fixture_or_501("CP-19", build)
    try:
        run = await cases_service.start_verify(session, actor, case_id)
    except NotFound:
        not_found("Case")
    return await run_events.load_run_out(session, actor.workspace_id, run.id)


@router.put("/{case_id}/criteria", response_model=CaseOut)
async def set_case_criteria(
    case_id: str, body: CaseCriteriaIn, user: CurrentUser, workspace: Workspace, session: Session
) -> CaseOut:
    """Strategy criteria for a direct-verify case, needed before any fit score is issued."""
    # Replaces the case's criteria and queues a re-evaluation (the run is in CaseOut.run).
    if workspace is None or session is None:
        return _fixture_case(case_id)
    try:
        await evaluate.set_case_criteria(
            session, workspace, _case_uuid(case_id), body.criteria, user_id=user.id
        )
        await session.commit()
        case = await _load_case(session, workspace, case_id)
        return await evaluate.case_out(session, case)
    except NotFound:
        not_found("Case")


@router.get("/{case_id}/assessments", response_model=list[AssessmentVersionOut])
async def list_assessments(
    case_id: str, workspace: Workspace, session: Session
) -> list[AssessmentVersionOut]:
    """Every assessment version, oldest first, each with its diff from the previous one."""
    if workspace is None or session is None:
        _fixture_case(case_id)
        return fixtures.assessments(case_id)
    try:
        case = await _load_case(session, workspace, case_id)
    except NotFound:
        not_found("Case")
    rows = await list_case_children(session, AssessmentVersion, workspace, case.id)
    rows.sort(key=lambda r: r.version)
    return await evaluate.list_versions_out(session, case.id, rows)


async def _load_case(session: AsyncSession, workspace: uuid.UUID, case_id: str) -> Case:
    return await repo_get_case(session, workspace, _case_uuid(case_id))
