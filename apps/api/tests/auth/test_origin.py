"""Unsafe browser requests sent straight to the API need an `Origin` from `WEB_ORIGIN`."""

import pytest

from app.settings import get_settings
from tests.auth.helpers import account, login

pytestmark = pytest.mark.asyncio


async def test_cross_site_post_refused(client, session) -> None:
    await account(session, "asha")
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = await client.request(
            method, "/auth/logout", headers={"origin": "https://evil.example"}
        )
        assert response.status_code == 403, method
    refused = await login(client, "asha@fund.example", headers={"origin": "null"})
    assert refused.status_code == 403 and "set-cookie" not in refused.headers


async def test_web_origin_and_no_origin_pass(client, session) -> None:
    await account(session, "asha")
    web = get_settings().cors_origins[0]
    assert (await login(client, "asha@fund.example", headers={"origin": web})).status_code == 200
    assert (await client.post("/auth/logout")).status_code == 204  # no Origin: not a browser


async def test_safe_methods_ignore_origin(client, session) -> None:
    response = await client.get("/health", headers={"origin": "https://evil.example"})
    assert response.status_code == 200
