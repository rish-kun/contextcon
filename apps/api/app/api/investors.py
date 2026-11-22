"""Investor discovery routes (CP-18).

The ranking is historical: investors ranked by comparable investments found in the
record. It never predicts investment, and v1 stops at the shortlist (no outreach).

Workspace access is an injectable dependency because `app/auth` is not on main yet.
The integrator wires it once auth exists:

    app.dependency_overrides[get_investor_actor] = <returns InvestorActor(workspace, user)>

Until then the routes fail closed with 501 (outside fixture mode), so nothing reads or
writes without a workspace. Tests override `investor_session` with their database.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.schemas.investors import (
    InvestorSearchIn,
    InvestorSearchOut,
    InvestorSearchSummary,
)
from app.db import repo
from app.db.session import get_sessionmaker
from app.pipelines import investors as pipeline

OWNER = "CP-18"

router = make_router(prefix="/investor-searches", tags=["investors"])


@dataclass(frozen=True)
class InvestorActor:
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None


async def get_investor_actor() -> InvestorActor | None:
    """The caller's workspace. None in fixture mode; 501 until auth is wired."""
    if fixtures_enabled():
        return None
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Not implemented yet: investor searches need workspace auth (CP-16).",
    )


async def investor_session(
    actor: Annotated[InvestorActor | None, Depends(get_investor_actor)],
) -> AsyncIterator[AsyncSession | None]:
    if actor is None:
        yield None
        return
    async with get_sessionmaker()() as session:
        yield session


Actor = Annotated[InvestorActor | None, Depends(get_investor_actor)]
Session = Annotated[AsyncSession | None, Depends(investor_session)]


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        not_found("Investor search")


@router.post("", response_model=InvestorSearchOut, status_code=status.HTTP_201_CREATED)
async def create_investor_search(
    body: InvestorSearchIn, actor: Actor, session: Session
) -> InvestorSearchOut:
    """Start an investor search for a business profile. Includes the run to follow."""
    if actor is None or session is None:
        return fixtures.investor_search().model_copy(update={"profile": body})
    row, _ = await pipeline.start_investor_search(
        session, actor.workspace_id, body, created_by=actor.user_id
    )
    return await pipeline.load_investor_search(session, actor.workspace_id, row.id)


@router.get("", response_model=list[InvestorSearchSummary])
async def list_investor_searches(actor: Actor, session: Session) -> list[InvestorSearchSummary]:
    if actor is None or session is None:
        return fixtures.investor_summaries()
    return await pipeline.list_investor_searches(session, actor.workspace_id)


@router.get("/{search_id}", response_model=InvestorSearchOut)
async def get_investor_search(search_id: str, actor: Actor, session: Session) -> InvestorSearchOut:
    """Ranked investors with the comparable rounds behind each entry."""
    if actor is None or session is None:
        if search_id != fixtures.INVESTOR_SEARCH_ID:
            not_found("Investor search")
        return fixtures.investor_search()
    try:
        return await pipeline.load_investor_search(session, actor.workspace_id, _uuid(search_id))
    except repo.NotFound:
        not_found("Investor search")
