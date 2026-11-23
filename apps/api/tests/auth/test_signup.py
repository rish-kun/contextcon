"""Self-serve sign-up, email verification, resend, and login while unverified."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.api.auth import EMAIL_NOT_VERIFIED, LINK_INVALID
from app.auth import verification
from app.auth.config import get_auth_settings
from app.auth.ratelimit import login_limiter, reset_login_limiter
from app.auth.sessions import SESSION_COOKIE, hash_token
from app.db.models import EmailVerificationToken, User, Workspace
from tests.auth.conftest import client_for
from tests.auth.helpers import PASSWORD, account, login

pytestmark = pytest.mark.asyncio

NEW_PASSWORD = "a brand new passphrase"


class Outbox:
    def __init__(self) -> None:
        self.sent: list[verification.OutgoingEmail] = []

    async def send(self, email: verification.OutgoingEmail) -> None:
        self.sent.append(email)

    def of_kind(self, kind: str) -> list[verification.OutgoingEmail]:
        return [e for e in self.sent if e.kind == kind]

    def last_token(self) -> str:
        found = re.search(r"/verify\?token=([A-Za-z0-9_-]+)", self.of_kind("verify_email")[-1].text)
        assert found, self.sent[-1].text
        return found.group(1)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    box = Outbox()
    monkeypatch.setattr(verification, "get_mailer", lambda: box)
    monkeypatch.setenv("AUTH_PUBLIC_WEB_URL", "https://app.dealproof.example")
    get_auth_settings.cache_clear()
    return box


async def signup(client, email="new@fund.example", password=NEW_PASSWORD, **extra):
    body = {"email": email, "display_name": "Neha Partner", "password": password, **extra}
    return await client.post("/auth/signup", json=body)


async def verify(client, token: str):
    return await client.post("/auth/verify", json={"token": token})


def _max_age(set_cookie: str) -> int:
    found = re.search(r"max-age=(\d+)", set_cookie, re.IGNORECASE)
    assert found, set_cookie
    return int(found.group(1))


async def test_signup_creates_unverified_user_and_workspace(client, session, outbox) -> None:
    response = await signup(client, " New@Fund.example ", organisation="Neha Capital")
    assert response.status_code == 202, response.text
    assert response.json() == {"status": "verification_sent", "email": "new@fund.example"}
    assert "set-cookie" not in response.headers  # nobody is signed in by sign-up

    user = (await session.execute(select(User))).scalar_one()
    assert user.email == "new@fund.example" and user.display_name == "Neha Partner"
    assert user.email_verified_at is None
    assert user.password_hash and NEW_PASSWORD not in user.password_hash
    ws = await session.get(Workspace, user.workspace_id)
    assert ws is not None and ws.name == "Neha Capital"

    [email] = outbox.sent
    assert email.to == "new@fund.example" and email.kind == "verify_email"
    assert "https://app.dealproof.example/verify?token=" in email.text
    token = outbox.last_token()
    row = (await session.execute(select(EmailVerificationToken))).scalar_one()
    assert row.token_hash == hash_token(token) != token  # only the hash is stored
    expected = datetime.now(UTC) + timedelta(hours=24)
    assert abs((row.expires_at - expected).total_seconds()) < 60


async def test_signup_without_organisation_gets_a_personal_workspace(
    client, session, outbox
) -> None:
    assert (await signup(client)).status_code == 202
    ws = (await session.execute(select(Workspace))).scalar_one()
    assert ws.name == "Neha Partner's workspace"


async def test_login_blocked_until_verified(client, session, outbox) -> None:
    await signup(client)
    blocked = await login(client, "new@fund.example", NEW_PASSWORD)
    assert blocked.status_code == 403
    assert blocked.json() == {"detail": EMAIL_NOT_VERIFIED}
    assert "set-cookie" not in blocked.headers
    assert len(login_limiter()) == 0  # the right password is not counted as a failure
    # A wrong password still reads as a plain bad sign-in, revealing nothing.
    wrong = await login(client, "new@fund.example", "not the password")
    assert wrong.status_code == 401


async def test_verify_signs_in_with_a_persistent_cookie(app, session, outbox) -> None:
    async with client_for(app) as client:
        await signup(client)
        response = await verify(client, outbox.last_token())
        assert response.status_code == 200, response.text
        assert response.json()["email"] == "new@fund.example"
        # Max-Age makes it a persistent cookie: it outlives a browser restart.
        assert _max_age(response.headers["set-cookie"]) == 24 * 3600
        assert (await client.get("/auth/me")).json()["display_name"] == "Neha Partner"
        token = client.cookies[SESSION_COOKIE]
    # A later visit (a new client holding the stored cookie) is still signed in.
    async with client_for(app, cookies={SESSION_COOKIE: token}) as later:
        assert (await later.get("/auth/me")).status_code == 200
    user = (await session.execute(select(User))).scalar_one()
    await session.refresh(user)
    assert user.email_verified_at is not None
    assert (await session.execute(select(EmailVerificationToken))).first() is None
    # From now on, email and password work as for any account.
    async with client_for(app) as fresh:
        assert (await login(fresh, "new@fund.example", NEW_PASSWORD)).status_code == 200


async def test_verify_link_is_single_use(app, session, outbox) -> None:
    async with client_for(app) as client:
        await signup(client)
        token = outbox.last_token()
        assert (await verify(client, token)).status_code == 200
    async with client_for(app) as other:
        reused = await verify(other, token)
        assert reused.status_code == 400 and reused.json() == {"detail": LINK_INVALID}
        assert "set-cookie" not in reused.headers


async def test_expired_link_is_refused(client, session, outbox) -> None:
    await signup(client)
    await session.execute(
        update(EmailVerificationToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await session.commit()
    response = await verify(client, outbox.last_token())
    assert response.status_code == 400 and response.json() == {"detail": LINK_INVALID}
    user = (await session.execute(select(User))).scalar_one()
    assert user.email_verified_at is None
    assert (await login(client, "new@fund.example", NEW_PASSWORD)).status_code == 403


async def test_unknown_token_is_refused(client, session, outbox) -> None:
    assert (await verify(client, "made-up-token")).status_code == 400


async def test_duplicate_verified_email_reveals_nothing(client, session, outbox) -> None:
    a = await account(session, "asha")
    fresh = await signup(client, "zed@fund.example")
    duplicate = await signup(client, "ASHA@fund.example", password="someone else's pw")
    assert duplicate.status_code == fresh.status_code == 202
    assert duplicate.json() == {"status": "verification_sent", "email": "asha@fund.example"}
    assert "set-cookie" not in duplicate.headers
    # The owner gets a "you already have an account" email instead of a link.
    [notice] = outbox.of_kind("existing_account")
    assert notice.to == "asha@fund.example"
    assert "https://app.dealproof.example/login" in notice.text
    assert [e.to for e in outbox.of_kind("verify_email")] == ["zed@fund.example"]
    # Nothing about the existing account changed: same workspace, same password.
    count = await session.scalar(select(func.count()).select_from(User))
    assert count == 2
    await session.refresh(a.user)
    assert a.user.workspace_id == a.workspace.id
    assert (await login(client, "asha@fund.example", PASSWORD)).status_code == 200


async def test_signup_again_while_unverified_sends_a_new_link(client, session, outbox) -> None:
    await signup(client)
    first = outbox.last_token()
    again = await signup(client, password="a different password")
    assert again.status_code == 202
    second = outbox.last_token()
    assert first != second
    assert await session.scalar(select(func.count()).select_from(User)) == 1
    assert (await verify(client, first)).status_code == 400  # replaced by the new link
    assert (await verify(client, second)).status_code == 200
    # The password chosen first still applies; a repeat sign-up never changes it.
    client.cookies.clear()
    assert (await login(client, "new@fund.example", NEW_PASSWORD)).status_code == 200


async def test_resend_sends_a_fresh_link(client, session, outbox) -> None:
    await signup(client)
    first = outbox.last_token()
    response = await client.post("/auth/verify/resend", json={"email": " NEW@fund.example"})
    assert response.status_code == 202
    assert response.json() == {"status": "verification_sent", "email": "new@fund.example"}
    second = outbox.last_token()
    assert second != first and len(outbox.of_kind("verify_email")) == 2
    assert (await verify(client, first)).status_code == 400
    assert (await verify(client, second)).status_code == 200


async def test_resend_reveals_nothing_for_unknown_or_verified(client, session, outbox) -> None:
    await account(session, "asha")
    for email in ("asha@fund.example", "nobody@fund.example"):
        response = await client.post("/auth/verify/resend", json={"email": email})
        assert response.status_code == 202
        assert response.json() == {"status": "verification_sent", "email": email}
    assert outbox.sent == []


async def test_resend_is_rate_limited(client, session, outbox) -> None:
    await signup(client)
    limit = get_auth_settings().resend_max_per_client
    for _ in range(limit):
        ok = await client.post("/auth/verify/resend", json={"email": "new@fund.example"})
        assert ok.status_code == 202
    blocked = await client.post("/auth/verify/resend", json={"email": "new@fund.example"})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    assert len(outbox.of_kind("verify_email")) == 1 + limit


async def test_signup_is_rate_limited_per_ip(client, session, outbox, monkeypatch) -> None:
    monkeypatch.setenv("AUTH_SIGNUP_MAX_PER_IP", "2")
    get_auth_settings.cache_clear()
    reset_login_limiter()
    assert (await signup(client, "one@fund.example")).status_code == 202
    assert (await signup(client, "two@fund.example")).status_code == 202
    blocked = await signup(client, "three@fund.example")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    assert await session.scalar(select(func.count()).select_from(User)) == 2


async def test_honeypot_creates_nothing(client, session, outbox) -> None:
    response = await signup(client, company_url="https://spam.example")
    assert response.status_code == 202
    assert await session.scalar(select(func.count()).select_from(User)) == 0
    assert outbox.sent == []


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"email": "not-an-email"}, "valid email"),
        ({"password": "short"}, "at least"),
        ({"display_name": "   "}, "name"),
    ],
)
async def test_signup_validation(client, session, outbox, body, detail) -> None:
    response = await signup(client, **body)
    assert response.status_code == 422 and detail in response.json()["detail"]
    assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_signup_can_be_switched_off(client, session, outbox, monkeypatch) -> None:
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    get_auth_settings.cache_clear()
    assert (await signup(client)).status_code == 403
    assert outbox.sent == []


async def test_cli_users_count_as_verified(session) -> None:
    a = await account(session, "asha")
    assert a.user.email_verified_at is not None


async def test_without_resend_the_link_goes_to_the_log(client, session, monkeypatch, caplog):
    monkeypatch.setenv("RESEND_API_KEY", "")
    monkeypatch.setenv("EMAIL_FROM", "")
    from app.settings import get_settings

    get_settings.cache_clear()
    try:
        with caplog.at_level("WARNING", logger="app.auth"):
            assert (await signup(client)).status_code == 202
    finally:
        get_settings.cache_clear()
    assert "/verify?token=" in caplog.text and "new@fund.example" in caplog.text


async def test_fixture_mode_serves_the_new_routes(client, monkeypatch) -> None:
    monkeypatch.setenv("DEALPROOF_FIXTURES", "1")
    assert (await signup(client)).status_code == 202
    assert (
        await client.post("/auth/verify/resend", json={"email": "a@b.example"})
    ).status_code == 202
    response = await verify(client, "anything")
    assert response.status_code == 200 and SESSION_COOKIE in response.headers["set-cookie"]
