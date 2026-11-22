"""The client IP that the web proxy vouches for, signed with `PROXY_SHARED_SECRET`.

Intended deployment: browser → web proxy (Next.js `/api/*`, Cloud Run) → API (Cloud Run).
The API's socket peer is then Google's front end, and `X-Forwarded-For` holds whatever
the caller wrote plus what each front end appended, so neither identifies the browser on
its own. The web proxy therefore sends:

    X-DealProof-Client-IP: <the browser's IP, as the web service's front end saw it>
    X-DealProof-Proxy: t=<unix seconds>,sig=<hex HMAC-SHA256(secret, "<t>\\n<ip>")>

The API trusts `X-DealProof-Client-IP` only when the signature verifies and `t` is within
`MAX_SKEW_SECONDS` of now. Anyone calling the API directly (or the proxy without the
secret configured) is limited by their own address instead: the socket peer, or the
`X-Forwarded-For` entry that `AUTH_TRUSTED_PROXY_HOPS` trusted front ends appended (see
`app.auth.cookies.client_ip`). The web side lives in `apps/web/lib/api/proxy-auth.ts`.
"""

import hashlib
import hmac
import ipaddress
import time

CLIENT_IP_HEADER = "x-dealproof-client-ip"
PROXY_HEADER = "x-dealproof-proxy"
MAX_SKEW_SECONDS = 300


def _mac(secret: str, ip: str, timestamp: int) -> str:
    return hmac.new(secret.encode(), f"{timestamp}\n{ip}".encode(), hashlib.sha256).hexdigest()


def sign(secret: str, ip: str, timestamp: int) -> str:
    """The `X-DealProof-Proxy` value for `ip` at `timestamp` (also used by tests)."""
    return f"t={timestamp},sig={_mac(secret, ip, timestamp)}"


def _parse(value: str) -> tuple[int, str] | None:
    fields = dict(part.strip().partition("=")[::2] for part in value.split(","))
    try:
        return int(fields["t"]), fields["sig"]
    except (KeyError, ValueError):
        return None


def verified_client_ip(
    secret: str,
    client_ip: str | None,
    proxy_header: str | None,
    *,
    now: float | None = None,
) -> str | None:
    """The forwarded client IP if the proxy signature checks out, else None."""
    if not secret or not client_ip or not proxy_header:
        return None
    client_ip = client_ip.strip()
    try:
        ipaddress.ip_address(client_ip)
    except ValueError:
        return None
    parsed = _parse(proxy_header)
    if parsed is None:
        return None
    timestamp, sig = parsed
    if abs((time.time() if now is None else now) - timestamp) > MAX_SKEW_SECONDS:
        return None
    if not hmac.compare_digest(_mac(secret, client_ip, timestamp).encode(), sig.lower().encode()):
        return None
    return client_ip
