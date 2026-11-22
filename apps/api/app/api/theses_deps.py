"""Request dependencies for the Discover routes.

`current_actor` is the signed-in user's workspace (from `app.auth.deps.current_user`,
401 without a session). In fixture mode (`DEALPROOF_FIXTURES=1`) it returns None and
the routes serve the canned fixtures without touching the database. Tests override
`current_actor`, `db_sessionmaker` and `llm_factory`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api._base import fixtures_enabled
from app.auth.deps import current_user
from app.auth.sessions import AuthUser
from app.db.session import get_sessionmaker
from app.pipelines.discover.clients import factories


@dataclass(frozen=True)
class Actor:
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None


def current_actor(user: Annotated[AuthUser, Depends(current_user)]) -> Actor | None:
    """The signed-in user and their workspace; None in fixture mode."""
    if fixtures_enabled():
        return None
    return Actor(user.workspace_id, user.id)


ActorDep = Annotated[Actor | None, Depends(current_actor)]


def db_sessionmaker(actor: ActorDep) -> async_sessionmaker[AsyncSession] | None:
    return None if actor is None else get_sessionmaker()


SessionmakerDep = Annotated[async_sessionmaker[AsyncSession] | None, Depends(db_sessionmaker)]


async def db_session(sm: SessionmakerDep) -> AsyncIterator[AsyncSession | None]:
    if sm is None:
        yield None
        return
    async with sm() as session:
        yield session


def llm_factory() -> Any:
    """Builds the LLM client for criteria extraction (tests override this)."""
    return factories.llm


SessionDep = Annotated[AsyncSession | None, Depends(db_session)]
LlmFactoryDep = Annotated[Any, Depends(llm_factory)]
