"""FastAPI dependencies for routes that need a signed-in user.

    from app.auth.deps import CurrentUser, WorkspaceId, AuthorizedCaseId, load_case

    @router.get("/cases/{case_id}")
    async def get_case(case_id: AuthorizedCaseId, user: CurrentUser) -> CaseOut: ...

- `current_user` → `AuthUser` (id, workspace_id, email, display_name). 401 without a
  live `dp_session` cookie.
- `current_workspace_id` → the user's workspace `uuid.UUID`. Pass it to every
  `app.db.repo` call; never take a workspace id from the request.
- `authorize_case` → the `{case_id}` path parameter as a `uuid.UUID`, after checking the
  case is in the user's workspace. 404 (never 403) otherwise, so ids do not leak.
- `load_case(db, workspace_id, case_id)` → the `Case` row or 404, for handler bodies.

Fixture mode (`DEALPROOF_FIXTURES=1`, never in production) needs no database: every
request is the fixture user, and `authorize_case` accepts the fixture case ids only.
"""

import uuid
from functools import cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._base import fixtures_enabled
from app.auth.sessions import SESSION_COOKIE, AuthUser, resolve_session
from app.db import repo
from app.db.models import Case
from app.db.session import get_sessionmaker

FIXTURE_WORKSPACE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "dealproof:fixture-workspace")


@cache
def fixture_user() -> AuthUser:
    from app.api import fixtures  # lazy: fixtures imports the Act router, which imports us

    return AuthUser(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"dealproof:{fixtures.USER_ID}"),
        workspace_id=FIXTURE_WORKSPACE_ID,
        email=fixtures.USER.email,
        display_name=fixtures.USER.display_name,
    )


def unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")


async def current_user(request: Request) -> AuthUser:
    """The signed-in user, from the `dp_session` cookie. 401 if missing or expired."""
    if fixtures_enabled():
        return fixture_user()
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthorized()
    async with get_sessionmaker()() as db:
        user = await resolve_session(db, token)
    if user is None:
        raise unauthorized()
    return user


CurrentUser = Annotated[AuthUser, Depends(current_user)]


async def current_workspace_id(user: CurrentUser) -> uuid.UUID:
    """The workspace every query of this request is scoped to."""
    return user.workspace_id


WorkspaceId = Annotated[uuid.UUID, Depends(current_workspace_id)]


def parse_id(value: str, what: str) -> uuid.UUID:
    """A path id as a UUID; anything else is reported as not found."""
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.") from None


async def load_case(db: AsyncSession, workspace_id: uuid.UUID, case_id: str | uuid.UUID) -> Case:
    """The case if it is in `workspace_id`, else 404."""
    cid = case_id if isinstance(case_id, uuid.UUID) else parse_id(case_id, "Case")
    try:
        return await repo.get_case(db, workspace_id, cid)
    except repo.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found.") from None


async def check_case_access(user: AuthUser, case_id: str) -> uuid.UUID:
    """Raise 404 unless `case_id` is a case in the user's workspace; returns its id.

    In fixture mode only the fixture case ids pass, and they are returned as a stable
    UUID derived from the id (fixture handlers read the raw path parameter instead)."""
    if fixtures_enabled():
        from app.api import fixtures

        if fixtures.case_out(case_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found.")
        return uuid.uuid5(uuid.NAMESPACE_URL, f"dealproof:{case_id}")
    async with get_sessionmaker()() as db:
        case = await load_case(db, user.workspace_id, case_id)
    return case.id


async def authorize_case(case_id: str, user: CurrentUser) -> uuid.UUID:
    """Dependency for routes with a `{case_id}` path parameter (see `check_case_access`)."""
    return await check_case_access(user, case_id)


AuthorizedCaseId = Annotated[uuid.UUID, Depends(authorize_case)]
