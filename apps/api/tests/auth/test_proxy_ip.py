"""The signed client IP from the web proxy (`X-DealProof-Client-IP` + `X-DealProof-Proxy`)."""

import time

import pytest
from starlette.requests import Request

from app.auth.config import get_auth_settings
from app.auth.cookies import client_ip_info
from app.auth.proxy import MAX_SKEW_SECONDS, sign, verified_client_ip
from tests.auth.helpers import PASSWORD, account, login

SECRET = "s3cret-shared-with-the-web-proxy"


def _headers(ip: str, *, secret: str = SECRET, at: int | None = None) -> dict[str, str]:
    t = int(time.time()) if at is None else at
    return {"x-dealproof-client-ip": ip, "x-dealproof-proxy": sign(secret, ip, t)}


def test_valid_signature_is_trusted() -> None:
    h = _headers("203.0.113.9", at=1_000)
    assert verified_client_ip(SECRET, h["x-dealproof-client-ip"], h["x-dealproof-proxy"], now=1_010)


@pytest.mark.parametrize(
    ("secret", "ip", "header", "now"),
    [
        ("", "203.0.113.9", sign(SECRET, "203.0.113.9", 1_000), 1_000),  # no secret configured
        (SECRET, "203.0.113.9", sign("wrong", "203.0.113.9", 1_000), 1_000),  # wrong key
        (SECRET, "198.51.100.1", sign(SECRET, "203.0.113.9", 1_000), 1_000),  # IP swapped
        (SECRET, "203.0.113.9", sign(SECRET, "203.0.113.9", 1_000), 1_000 + MAX_SKEW_SECONDS + 1),
        (SECRET, "not-an-ip", sign(SECRET, "not-an-ip", 1_000), 1_000),
        (SECRET, "203.0.113.9", "garbage", 1_000),
        (SECRET, "203.0.113.9", "t=1000,sig=ü", 1_000),
        (SECRET, "203.0.113.9", None, 1_000),
    ],
)
def test_invalid_signatures_are_ignored(secret, ip, header, now) -> None:
    assert verified_client_ip(secret, ip, header, now=now) is None


@pytest.mark.asyncio
async def test_signed_ip_separates_browsers_behind_the_proxy(client, session, monkeypatch) -> None:
    monkeypatch.setenv("PROXY_SHARED_SECRET", SECRET)
    get_auth_settings.cache_clear()
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    for _ in range(limit):
        r = await login(client, "asha@fund.example", "wrong", headers=_headers("203.0.113.7"))
        assert r.status_code == 401
    blocked = await login(client, "asha@fund.example", PASSWORD, headers=_headers("203.0.113.7"))
    assert blocked.status_code == 429
    other = await login(client, "asha@fund.example", PASSWORD, headers=_headers("198.51.100.2"))
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_unsigned_client_ip_header_is_ignored(client, session, monkeypatch) -> None:
    monkeypatch.setenv("PROXY_SHARED_SECRET", SECRET)
    get_auth_settings.cache_clear()
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    for i in range(limit):
        forged = _headers(f"10.0.0.{i}", secret="guessed")
        await login(client, "asha@fund.example", "wrong", headers=forged)
    # Every forged IP fell back to the same socket peer, so the limit applies.
    fresh = _headers("10.9.9.9", secret="guessed")
    assert (await login(client, "asha@fund.example", PASSWORD, headers=fresh)).status_code == 429


@pytest.mark.asyncio
async def test_without_a_secret_the_header_is_ignored(client, session) -> None:
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    for i in range(limit):
        await login(client, "asha@fund.example", "wrong", headers=_headers(f"10.0.0.{i}"))
    blocked = await login(client, "asha@fund.example", PASSWORD, headers=_headers("10.9.9.9"))
    assert blocked.status_code == 429


def _request(headers: dict[str, str], peer: str = "10.1.1.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("env", "headers", "expected"),
    [
        ({}, {}, ("10.1.1.1", True)),  # local: the peer is the caller
        ({"K_SERVICE": "api"}, {}, ("10.1.1.1", False)),  # Cloud Run, no secret: shared
        ({"K_SERVICE": "api", "PROXY_SHARED_SECRET": SECRET}, {}, ("10.1.1.1", True)),
        (
            {"K_SERVICE": "api", "PROXY_SHARED_SECRET": SECRET},
            _headers("203.0.113.9"),
            ("203.0.113.9", True),
        ),
        (
            {"K_SERVICE": "api", "PROXY_SHARED_SECRET": SECRET, "AUTH_TRUSTED_PROXY_HOPS": "1"},
            {"x-forwarded-for": "6.6.6.6, 198.51.100.4"},
            ("198.51.100.4", True),
        ),
    ],
)
def test_client_ip_info(monkeypatch, env, headers, expected) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_auth_settings.cache_clear()
    assert client_ip_info(_request(headers), get_auth_settings()) == expected
