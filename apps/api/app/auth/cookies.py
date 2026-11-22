"""The `dp_session` cookie: httpOnly, SameSite=Lax, Path=/, Secure outside local dev.

The browser only ever talks to the web origin; the Next.js `/api/*` proxy passes this
`Set-Cookie` through unchanged. No `Domain` attribute is set, so the cookie is
host-only on the web origin.
"""

from datetime import timedelta

from fastapi import Request, Response

from app.auth.config import AuthSettings
from app.auth.proxy import CLIENT_IP_HEADER, PROXY_HEADER, verified_client_ip
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


def client_ip_info(request: Request, settings: AuthSettings) -> tuple[str, bool]:
    """The caller's IP for rate limiting, and whether it identifies one client.

    The IP, in order of trust:

    1. `X-DealProof-Client-IP`, only when the web proxy signed it with
       `PROXY_SHARED_SECRET` (browser → web proxy → API; see `app.auth.proxy`).
    2. The `X-Forwarded-For` entry `AUTH_TRUSTED_PROXY_HOPS` places from the right, i.e.
       the address the nearest trusted front end saw. Entries a client wrote itself sit
       further left and are ignored.
    3. The socket peer. With uvicorn's `--forwarded-allow-ips`, this is already the
       address a trusted proxy reported, so that flag must name only real proxies.

    On Cloud Run without `PROXY_SHARED_SECRET`, every browser reaches the API from the web
    service's address, so 2 and 3 are reported as shared (False) and the per-IP sign-in
    limit is skipped rather than locking every browser out together.
    """
    secret = settings.proxy_shared_secret.get_secret_value()
    forwarded = verified_client_ip(
        secret, request.headers.get(CLIENT_IP_HEADER), request.headers.get(PROXY_HEADER)
    )
    if forwarded:
        return forwarded, True
    own = bool(secret) or not settings.on_cloud_run
    hops = settings.trusted_proxy_hops
    if hops:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        entries = [e for e in entries if e]
        if len(entries) >= hops:
            return entries[-hops], own
    return (request.client.host if request.client else "unknown"), own


def client_ip(request: Request, settings: AuthSettings) -> str:
    """The caller's IP for rate limiting (see `client_ip_info`)."""
    return client_ip_info(request, settings)[0]
