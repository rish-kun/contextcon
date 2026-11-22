"""Investor discovery routes (CP-18).

The ranking is historical: investors ranked by comparable investments found in the
record. It never predicts investment, and v1 stops at the shortlist (no outreach).

The workspace and user come from the signed-in session (`app.auth.deps`): 401 without
one, and another workspace's search is 404. Fixture mode needs no database and serves
the fixture search. Tests may override `investor_session` with their database.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.schemas.investors import (
    InvestorSearchIn,
    InvestorSearchOut,
    InvestorSearchSummary,
)
from app.auth.deps import CurrentUser, WorkspaceId
from app.db import repo
from app.db.session import get_sessionmaker
from app.pipelines import investors as pipeline

OWNER = "CP-18"

router = make_router(prefix="/investor-searches", tags=["investors"])


async def investor_session() -> AsyncIterator[AsyncSession | None]:
    """A database session, or None in fixture mode."""
    if fixtures_enabled():
        yield None
        return
    async with get_sessionmaker()() as session:
        yield session


Session = Annotated[AsyncSession | None, Depends(investor_session)]


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        not_found("Investor search")


@router.post("", response_model=InvestorSearchOut, status_code=status.HTTP_201_CREATED)
async def create_investor_search(
    body: InvestorSearchIn, user: CurrentUser, workspace_id: WorkspaceId, session: Session
) -> InvestorSearchOut:
    """Start an investor search for a business profile. Includes the run to follow."""
    if session is None:
        return fixtures.investor_search().model_copy(update={"profile": body})
    row, _ = await pipeline.start_investor_search(session, workspace_id, body, created_by=user.id)
    return await pipeline.load_investor_search(session, workspace_id, row.id)


@router.get("", response_model=list[InvestorSearchSummary])
async def list_investor_searches(
    workspace_id: WorkspaceId, session: Session
) -> list[InvestorSearchSummary]:
    if session is None:
        return fixtures.investor_summaries()
    return await pipeline.list_investor_searches(session, workspace_id)


@router.get("/{search_id}", response_model=InvestorSearchOut)
async def get_investor_search(
    search_id: str, workspace_id: WorkspaceId, session: Session
) -> InvestorSearchOut:
    """Ranked investors with the comparable rounds behind each entry."""
    if session is None:
        if search_id != fixtures.INVESTOR_SEARCH_ID:
            not_found("Investor search")
        return fixtures.investor_search()
    try:
        return await pipeline.load_investor_search(session, workspace_id, _uuid(search_id))
    except repo.NotFound:
        not_found("Investor search")
