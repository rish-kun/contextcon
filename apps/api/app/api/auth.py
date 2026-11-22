"""Auth routes. Stubs until CP-16 (named users, `dp_session` cookie)."""

from fastapi import Response, status

from app.api import fixtures
from app.api._base import fixture_or_501, fixtures_enabled, make_router, not_implemented
from app.api.schemas.auth import LoginIn, UserOut

OWNER = "CP-16"
SESSION_COOKIE = "dp_session"

router = make_router(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response) -> UserOut:
    """Sign in with email and password; sets the `dp_session` cookie."""
    if not fixtures_enabled():
        not_implemented(OWNER)
    response.set_cookie(SESSION_COOKIE, "fixture", httponly=True, samesite="lax")
    return fixtures.USER


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """End the session and clear the cookie."""
    if not fixtures_enabled():
        not_implemented(OWNER)
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me", response_model=UserOut)
def me() -> UserOut:
    """The signed-in user. 401 without a valid session."""
    return fixture_or_501(OWNER, lambda: fixtures.USER)
