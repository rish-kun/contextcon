"""Auth routes: sign-up with email verification, sign-in, logout, the signed-in user.

- `POST /auth/signup` creates an unverified user in a new workspace and emails a
  verification link. The answer is the same 202 whether or not the email already has an
  account (an existing account gets a "you already have an account" email, or a new link
  if it is still unverified), so the route does not reveal who is registered.
- `POST /auth/verify` uses the link's token once, marks the email verified and signs the
  person in, exactly as `/auth/login` does.
- `POST /auth/verify/resend` sends a new link to an unverified account (same 202).
- `POST /auth/login` refuses an unverified account with 403 `EMAIL_NOT_VERIFIED`, and
  only after the password matched.

Admins can still create (already verified) accounts with `python -m app.auth.cli`.
The session is the httpOnly `dp_session` cookie (see `app.auth.cookies`): persistent,
with `Max-Age` equal to `AUTH_SESSION_TTL_HOURS`, so it survives a browser restart.
"""

import re
from datetime import timedelta

from fastapi import BackgroundTasks, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router
from app.api.schemas.auth import (
    LoginIn,
    ResendVerificationIn,
    SignupIn,
    UserOut,
    VerificationSentOut,
    VerifyIn,
)
from app.api.schemas.common import ErrorOut
from app.auth import verification
from app.auth.config import get_auth_settings
from app.auth.cookies import clear_session_cookie, client_ip_info, set_session_cookie
from app.auth.deps import CurrentUser
from app.auth.ratelimit import VerifierBusy, login_limiter, resend_limiter, signup_limiter
from app.auth.sessions import (
    SESSION_COOKIE,
    AuthUser,
    authenticate,
    create_session,
    find_user_by_email,
    hash_password_async,
    normalize_email,
    purge_expired_sessions,
    revoke_session,
)
from app.db import repo
from app.db.session import get_sessionmaker

router = make_router(prefix="/auth", tags=["auth"])

BAD_CREDENTIALS = "Email or password is incorrect."
# The web login form matches this exact text to offer "send a new link".
EMAIL_NOT_VERIFIED = "Confirm your email address before you log in."
LINK_INVALID = "This link has expired or has already been used."

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _user_out(user: AuthUser) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, display_name=user.display_name)


def _too_many(wait: int | None, what: str) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many {what}. Try again later.",
        headers={"Retry-After": str(wait or 1)},
    )


def _busy(what: str) -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        f"Too many {what} at once. Try again in a moment.",
        headers={"Retry-After": "2"},
    )


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _workspace_name(organisation: str, display_name: str) -> str:
    return (organisation.strip() or f"{display_name}'s workspace")[:200]


@router.post(
    "/signup",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VerificationSentOut,
    responses={
        403: {"model": ErrorOut, "description": "Sign-up is closed (AUTH_SIGNUP_ENABLED=false)."},
        422: {"model": ErrorOut, "description": "Invalid email, name or password."},
        429: {"model": ErrorOut, "description": "Too many sign-ups; see Retry-After."},
        503: {"model": ErrorOut, "description": "Too busy; see Retry-After."},
    },
)
async def signup(
    body: SignupIn, request: Request, background: BackgroundTasks
) -> VerificationSentOut:
    """Create an unverified account and its workspace, and email a verification link.

    The same 202 for a new email and a registered one. Never signs anyone in, and never
    reads or changes an existing account's password."""
    settings = get_auth_settings()
    email = normalize_email(body.email)
    display_name = body.display_name.strip()
    if not _EMAIL.match(email):
        raise _invalid("Enter a valid email address.")
    if not display_name:
        raise _invalid("Enter your name. Approvals are recorded against a named person.")
    if len(body.password) < settings.min_password_length:
        raise _invalid(f"Use a password of at least {settings.min_password_length} characters.")
    sent = VerificationSentOut(email=email)
    if fixtures_enabled():
        return sent
    if not settings.signup_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-up is closed on this deployment.")
    ip, ip_trusted = client_ip_info(request, settings)
    limiter = signup_limiter()
    wait, reservation = limiter.acquire(email, ip, ip_trusted=ip_trusted)
    if reservation is None:
        raise _too_many(wait, "sign-up attempts")
    if body.company_url.strip():
        return sent  # honeypot: a bot filled the hidden field
    try:
        # Hashed for every request, so a registered email answers as slowly as a new one.
        password_hash = await hash_password_async(body.password)
    except VerifierBusy:
        limiter.refund(reservation)
        raise _busy("sign-ups") from None

    ttl = timedelta(hours=settings.verification_ttl_hours)
    async with get_sessionmaker()() as db:
        existing = await find_user_by_email(db, email)
        if existing is not None and existing.email_verified_at is not None:
            background.add_task(
                verification.send_existing_account_email, existing.email, existing.display_name
            )
            return sent
        if existing is not None:
            # Signed up before and never verified: send a fresh link, change nothing else.
            to, name = existing.email, existing.display_name
            token = await verification.issue_token(db, existing.id, ttl=ttl)
        else:
            ws = await repo.create_workspace(db, _workspace_name(body.organisation, display_name))
            user = await repo.create_user(db, ws.id, email=email, display_name=display_name)
            user.password_hash = password_hash
            to, name = user.email, user.display_name
            token = await verification.issue_token(db, user.id, ttl=ttl)
        try:
            await db.commit()
        except IntegrityError:
            # A concurrent sign-up with the same email won; it sends its own link.
            return sent
    background.add_task(verification.send_verification_email, to, name, token, ttl=ttl)
    return sent


@router.post(
    "/verify",
    response_model=UserOut,
    responses={400: {"model": ErrorOut, "description": "Unknown, expired or used link."}},
)
async def verify_email(body: VerifyIn, request: Request, response: Response) -> UserOut:
    """Use a verification link's token (once): verify the email and sign in."""
    settings = get_auth_settings()
    ttl = timedelta(hours=settings.session_ttl_hours)
    if fixtures_enabled():
        response.set_cookie(SESSION_COOKIE, "fixture", httponly=True, samesite="lax")
        return fixtures.USER
    async with get_sessionmaker()() as db:
        user = await verification.consume_token(db, body.token.strip())
        if user is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, LINK_INVALID)
        await purge_expired_sessions(db)
        token, _ = await create_session(db, user, ttl=ttl)
        signed_in = AuthUser.of(user)
        await db.commit()
    set_session_cookie(response, request, token, ttl, settings)
    return _user_out(signed_in)


@router.post(
    "/verify/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VerificationSentOut,
    responses={429: {"model": ErrorOut, "description": "Too many requests; see Retry-After."}},
)
async def resend_verification(
    body: ResendVerificationIn, request: Request, background: BackgroundTasks
) -> VerificationSentOut:
    """Email a new verification link if this email has an unverified account. The same
    202 otherwise. Older links of that account stop working."""
    settings = get_auth_settings()
    email = normalize_email(body.email)
    sent = VerificationSentOut(email=email)
    if fixtures_enabled():
        return sent
    ip, ip_trusted = client_ip_info(request, settings)
    wait, reservation = resend_limiter().acquire(email, ip, ip_trusted=ip_trusted)
    if reservation is None:
        raise _too_many(wait, "requests for a new link")
    ttl = timedelta(hours=settings.verification_ttl_hours)
    async with get_sessionmaker()() as db:
        user = await find_user_by_email(db, email)
        if user is None or user.email_verified_at is not None:
            return sent
        to, name = user.email, user.display_name
        token = await verification.issue_token(db, user.id, ttl=ttl)
        await db.commit()
    background.add_task(verification.send_verification_email, to, name, token, ttl=ttl)
    return sent


@router.post(
    "/login",
    response_model=UserOut,
    responses={
        403: {"model": ErrorOut, "description": "Email not verified yet (EMAIL_NOT_VERIFIED)."},
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
            raise _busy("sign-ins") from None
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
        if user.email_verified_at is None:
            limiter.refund(reservation)  # the password was right; not a failed guess
            raise HTTPException(status.HTTP_403_FORBIDDEN, EMAIL_NOT_VERIFIED)
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
