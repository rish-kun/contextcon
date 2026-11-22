"""Case routes. Create/identity/verify: CP-19. Assessments: CP-22. Memo aggregate: CP-25."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import fixtures
from app.api._base import fixture_or_501, fixtures_enabled, make_router, not_found
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
from app.db.session import get_session
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
def create_case(body: CaseCreate) -> CaseOut:
    """Open a case from a shortlist item, or from a name and website. Starts a verify run."""
    return fixture_or_501("CP-19", lambda: _fixture_case(fixtures.CASE_ID))


@router.get("", response_model=list[CaseSummary])
def list_cases() -> list[CaseSummary]:
    """Cases dashboard: disposition, fit with coverage, and cost per case."""
    return fixture_or_501("CP-25", fixtures.case_summaries)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str) -> CaseDetail:
    """The finished-case memo aggregate, sections in PRD order."""

    def build() -> CaseDetail:
        detail = fixtures.case_detail(case_id)
        if detail is None:
            not_found("Case")
        return detail

    return fixture_or_501("CP-25", build)


@router.post("/{case_id}/identity", response_model=CaseOut)
def pick_identity(case_id: str, body: IdentityPickIn) -> CaseOut:
    """Pick one candidate when identity is ambiguous or unresolved. Records who and when."""
    return fixture_or_501("CP-19", lambda: _fixture_case(case_id))


@router.post("/{case_id}/verify", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def start_verify(case_id: str) -> RunOut:
    """Start (or re-run) verification for the case."""

    def build() -> RunOut:
        case = _fixture_case(case_id)
        assert case.run is not None
        return case.run

    return fixture_or_501("CP-19", build)


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
