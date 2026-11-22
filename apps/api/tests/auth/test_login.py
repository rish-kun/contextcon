"""Sign-in, sessions, logout, expiry and the login rate limit, through the real app."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.auth.config import get_auth_settings
from app.auth.sessions import SESSION_COOKIE, hash_token
from app.db.models import AuthSession
from tests.auth.conftest import client_for
from tests.auth.helpers import PASSWORD, account, login

pytestmark = pytest.mark.asyncio


def _cookie_attrs(set_cookie: str) -> dict[str, str]:
    parts = [p.strip() for p in set_cookie.split(";")]
    attrs = {}
    for part in parts[1:]:
        key, _, value = part.partition("=")
        attrs[key.lower()] = value
    return attrs


async def test_login_sets_cookie(client, session) -> None:
    a = await account(session, "asha")
    response = await login(client, "  ASHA@fund.example ")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": str(a.user.id),
        "email": "asha@fund.example",
        "display_name": "Asha Analyst",
    }
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{SESSION_COOKIE}=")
    attrs = _cookie_attrs(set_cookie)
    assert "httponly" in attrs and attrs["samesite"].lower() == "lax" and attrs["path"] == "/"
    assert int(attrs["max-age"]) == 24 * 3600
    assert "secure" not in attrs  # plain http in tests, AUTH_COOKIE_SECURE=false
    assert "domain" not in attrs  # host-only on the web origin

    token = client.cookies[SESSION_COOKIE]
    rows = list((await session.execute(select(AuthSession))).scalars())
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(token) != token  # only the hash is stored

    me = await client.get("/auth/me")
    assert me.status_code == 200 and me.json()["display_name"] == "Asha Analyst"


async def test_bad_password_401(client, session) -> None:
    await account(session, "asha")
    wrong = await login(client, "asha@fund.example", "not the password")
    unknown = await login(client, "nobody@fund.example", "not the password")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # does not reveal which emails exist
    assert "set-cookie" not in wrong.headers
    assert (await client.get("/auth/me")).status_code == 401


async def test_protected_route_requires_session(client, session) -> None:
    await account(session, "asha")
    assert (await client.get("/auth/me")).status_code == 401
    client.cookies.set(SESSION_COOKIE, "forged-token")
    assert (await client.get("/auth/me")).status_code == 401


async def test_logout_invalidates(app, session) -> None:
    await account(session, "asha")
    async with client_for(app) as client:
        await login(client, "asha@fund.example")
        token = client.cookies[SESSION_COOKIE]
        response = await client.post("/auth/logout")
        assert response.status_code == 204
        assert _cookie_attrs(response.headers["set-cookie"])["max-age"] == "0"
    # Replaying the old cookie after logout fails: the server-side session is gone.
    async with client_for(app, cookies={SESSION_COOKIE: token}) as replay:
        assert (await replay.get("/auth/me")).status_code == 401
    assert (await session.execute(select(AuthSession))).first() is None


async def test_session_expiry(client, session) -> None:
    await account(session, "asha")
    await login(client, "asha@fund.example")
    assert (await client.get("/auth/me")).status_code == 200
    await session.execute(
        update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await session.commit()
    assert (await client.get("/auth/me")).status_code == 401


async def test_expired_sessions_are_purged_on_login(app, session) -> None:
    await account(session, "asha")
    async with client_for(app) as first:
        await login(first, "asha@fund.example")
    await session.execute(
        update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await session.commit()
    async with client_for(app) as second:
        await login(second, "asha@fund.example")
    rows = list((await session.execute(select(AuthSession))).scalars())
    assert len(rows) == 1 and rows[0].expires_at > datetime.now(UTC)


async def test_login_rate_limited_per_email_and_ip(client, session, monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_HOPS", "1")
    get_auth_settings.cache_clear()
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    ip_a = {"x-forwarded-for": "203.0.113.7"}
    for i in range(limit):
        # Entries left of the trusted hop are client-written and ignored.
        spoof = {"x-forwarded-for": f"10.0.0.{i}, 203.0.113.7"}
        assert (await login(client, "asha@fund.example", "wrong", headers=spoof)).status_code == 401
    blocked = await login(client, "asha@fund.example", PASSWORD, headers=ip_a)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    # Another client IP is counted separately (up to the looser per-email cap).
    ip_b = {"x-forwarded-for": "198.51.100.2"}
    assert (await login(client, "asha@fund.example", PASSWORD, headers=ip_b)).status_code == 200


async def test_parallel_guesses_cannot_outrun_the_limit(client, session) -> None:
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    responses = await asyncio.gather(
        *(login(client, "asha@fund.example", f"guess {i}") for i in range(limit * 3))
    )
    codes = sorted(r.status_code for r in responses)
    assert codes.count(401) == limit
    assert codes.count(429) == limit * 2


async def test_forwarded_for_ignored_without_trusted_hops(client, session) -> None:
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    for i in range(limit):
        await login(
            client, "asha@fund.example", "wrong", headers={"x-forwarded-for": f"10.0.0.{i}"}
        )
    fresh = {"x-forwarded-for": "10.9.9.9"}
    assert (await login(client, "asha@fund.example", PASSWORD, headers=fresh)).status_code == 429


async def test_success_clears_client_failures(client, session) -> None:
    await account(session, "asha")
    limit = get_auth_settings().login_max_failures_per_client
    for _ in range(limit - 1):
        await login(client, "asha@fund.example", "wrong")
    assert (await login(client, "asha@fund.example")).status_code == 200
    for _ in range(limit - 1):
        assert (await login(client, "asha@fund.example", "wrong")).status_code == 401


@pytest.mark.parametrize(
    ("env", "headers", "secure"),
    [
        ({}, {"x-forwarded-proto": "https"}, True),
        ({"K_SERVICE": "dealproof-api"}, {}, True),
        ({}, {}, False),
        ({"AUTH_COOKIE_SECURE": "true"}, {}, True),
    ],
)
async def test_cookie_secure_in_production(app, session, monkeypatch, env, headers, secure) -> None:
    monkeypatch.delenv("AUTH_COOKIE_SECURE")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_auth_settings.cache_clear()
    await account(session, "asha")
    async with client_for(app) as client:
        response = await login(client, "asha@fund.example", headers=headers)
    assert response.status_code == 200
    assert ("secure" in _cookie_attrs(response.headers["set-cookie"])) is secure
