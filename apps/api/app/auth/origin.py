"""Refuse cross-site state changes sent by a browser straight to the API.

Browser traffic normally arrives through the web proxy, which checks `Origin` itself and
does not forward it (`apps/web/lib/api/proxy-rules.ts`, `isSameOriginRequest`). A browser
that calls the API directly always sends `Origin` on POST/PUT/PATCH/DELETE, so an unsafe
request whose `Origin` is not one of `WEB_ORIGIN` gets 403 here. Requests without `Origin`
(the web proxy, the web server's own calls, curl) are not browser cross-site requests and
pass; they still need a session like any other request.
"""

from collections.abc import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed = frozenset(o.rstrip("/") for o in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"].upper() in UNSAFE_METHODS:
            origin = next((v for k, v in scope["headers"] if k == b"origin"), None)
            if origin is not None and origin.decode("latin-1").rstrip("/") not in self.allowed:
                response = JSONResponse({"detail": "Cross-site request refused."}, 403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
