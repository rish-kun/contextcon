"""Auth routes: email + password sign-in, logout, and the signed-in user.

Accounts are created with `python -m app.auth.cli create-user` (no sign-up route).
The session is the httpOnly `dp_session` cookie (see `app.auth.cookies`).
"""

from datetime import timedelta

from fastapi import HTTPException, Request, Response, status

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router
from app.api.schemas.auth import LoginIn, UserOut
from app.api.schemas.common import ErrorOut
from app.auth.config import get_auth_settings
from app.auth.cookies import clear_session_cookie, client_ip_info, set_session_cookie
from app.auth.deps import CurrentUser
from app.auth.ratelimit import VerifierBusy, login_limiter
from app.auth.sessions import (
    SESSION_COOKIE,
    AuthUser,
    authenticate,
    create_session,
    normalize_email,
    purge_expired_sessions,
    revoke_session,
)
from app.db.session import get_sessionmaker

router = make_router(prefix="/auth", tags=["auth"])

BAD_CREDENTIALS = "Email or password is incorrect."


def _user_out(user: AuthUser) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, display_name=user.display_name)


@router.post(
    "/login",
    response_model=UserOut,
    responses={
        429: {"model": ErrorOut, "description": "Too many failed sign-ins; see Retry-After."},
        503: {"model": ErrorOut, "description": "Too many sign-ins at once; see Retry-After."},
    },
)
async def login(body: LoginIn, request: Request, response: Response) -> UserOut:
    """Sign in with email and password; sets the `dp_session` cookie."""
    if fixtures_enabled():
        response.set_cookie(SESSION_COOKIE, "fixture", httponly=True, samesite="lax")
        return fixtures.USER
    settings = get_auth_settings()
    email = normalize_email(body.email)
    ip, ip_trusted = client_ip_info(request, settings)
    limiter = login_limiter()
    # Counts as a failure until refunded.
    wait, reservation = limiter.acquire(email, ip, ip_trusted=ip_trusted)
    if reservation is None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    ttl = timedelta(hours=settings.session_ttl_hours)
    async with get_sessionmaker()() as db:
        try:
            user = await authenticate(db, email, body.password)
        except VerifierBusy:
            limiter.refund(reservation)  # no password was checked
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Too many sign-ins at once. Try again in a moment.",
                headers={"Retry-After": "2"},
            ) from None
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
        await purge_expired_sessions(db)
        token, _ = await create_session(db, user, ttl=ttl)
        signed_in = AuthUser.of(user)
        await db.commit()
    limiter.succeeded(reservation)
    set_session_cookie(response, request, token, ttl, settings)
    return _user_out(signed_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    """End the session and clear the cookie. Succeeds without a session too."""
    if fixtures_enabled():
        response.delete_cookie(SESSION_COOKIE)
        return
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        async with get_sessionmaker()() as db:
            await revoke_session(db, token)
            await db.commit()
    clear_session_cookie(response, request, get_auth_settings())


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    """The signed-in user. 401 without a valid session."""
    if fixtures_enabled():
        return fixtures.USER
    return _user_out(user)
