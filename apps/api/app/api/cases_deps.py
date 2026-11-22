"""Dependencies for the CP-19 case routes.

`get_case_actor` is the signed-in user (`app.auth.deps.current_user`, 401 without a
session) and the workspace every query is scoped to. In fixture mode it is None, and
the routes serve fixtures without opening a database session. Tests override
`get_case_actor` / `get_case_session` through `app.dependency_overrides`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._base import fixtures_enabled
from app.auth.deps import CurrentUser
from app.db.session import get_sessionmaker


@dataclass(frozen=True)
class CaseActor:
    """The signed-in user, and the workspace every case query is scoped to."""

    workspace_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str


async def get_case_actor(user: CurrentUser) -> CaseActor | None:
    if fixtures_enabled():
        return None
    return CaseActor(
        workspace_id=user.workspace_id, user_id=user.id, display_name=user.display_name
    )


async def get_case_session(
    actor: Annotated[CaseActor | None, Depends(get_case_actor)],
) -> AsyncIterator[AsyncSession | None]:
    """One session per request, opened only for a signed-in (non-fixture) caller."""
    if actor is None:
        yield None
        return
    async with get_sessionmaker()() as session:
        yield session


Actor = Annotated[CaseActor | None, Depends(get_case_actor)]
CaseSession = Annotated[AsyncSession | None, Depends(get_case_session)]
