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


def client_ip(request: Request, settings: AuthSettings) -> str:
    """The caller's IP for rate limiting. Only `X-Forwarded-For` entries added by trusted
    proxies count (`AUTH_TRUSTED_PROXY_HOPS`); entries a client wrote itself sit further
    left and are ignored. Without trusted hops, the socket peer."""
    hops = settings.trusted_proxy_hops
    if hops:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        entries = [e for e in entries if e]
        if len(entries) >= hops:
            return entries[-hops]
    return request.client.host if request.client else "unknown"
