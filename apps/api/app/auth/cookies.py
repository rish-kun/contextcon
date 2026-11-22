"""The `dp_session` cookie: httpOnly, SameSite=Lax, Path=/, Secure outside local dev.

The browser only ever talks to the web origin; the Next.js `/api/*` proxy passes this
`Set-Cookie` through unchanged. No `Domain` attribute is set, so the cookie is
host-only on the web origin.
"""

from datetime import timedelta

from fastapi import Request, Response

from app.auth.config import AuthSettings
from app.auth.sessions import SESSION_COOKIE


def cookie_secure(request: Request, settings: AuthSettings) -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    if settings.on_cloud_run:
        return True
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",")[0].strip().lower() == "https"


def set_session_cookie(
    response: Response, request: Request, token: str, ttl: timedelta, settings: AuthSettings
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        path="/",
        httponly=True,
        secure=cookie_secure(request, settings),
        samesite="lax",
    )


def clear_session_cookie(response: Response, request: Request, settings: AuthSettings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=cookie_secure(request, settings),
        samesite="lax",
    )


def client_ip(request: Request) -> str:
    """The caller's IP for rate limiting: the first `X-Forwarded-For` hop (set by the web
    proxy / Cloud Run front end), else the socket peer. Spoofable, which is why the
    limiter also caps failures per email."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"
