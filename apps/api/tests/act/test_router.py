from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from app.act.deps import authorize_case, get_act_service, get_actor
from app.act.models import Actor
from app.act.router import router
from tests.act.fakes import RECIPIENT, make_service

USERS = {
    "alice": Actor(user_id="u-alice", display_name="Alice Analyst"),
    "bob": Actor(user_id="u-bob", display_name="Bob Manager"),
}
BASE = "/cases/case-1/messages"


def _build(enabled: bool = True):
    service, fake, _, _ = make_service(enabled=enabled)
    app = FastAPI()
    app.include_router(router)

    async def actor(x_user: str = Header(default="alice")) -> Actor:
        if x_user not in USERS:
            raise HTTPException(401)
        return USERS[x_user]

    async def case_access(case_id: str) -> str:
        if case_id != "case-1":
            raise HTTPException(404, "case not found")
        return case_id

    app.dependency_overrides[get_actor] = actor
    app.dependency_overrides[authorize_case] = case_access
    app.dependency_overrides[get_act_service] = lambda: service
    return TestClient(app), fake


@pytest.fixture
def api():
    return _build()


def _create(client: TestClient) -> dict:
    response = client.post(
        BASE, json={"subject": "Documents request", "body": "Please share", "recipient": RECIPIENT}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client: TestClient, message: dict) -> dict:
    response = client.post(
        f"{BASE}/{message['id']}/approve",
        json={"revision_id": message["current_revision"]["id"]},
        headers={"x-user": "bob"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_full_flow_and_second_send_conflicts(api) -> None:
    client, fake = api
    message = _create(client)
    assert message["status"] == "draft"

    approved = _approve(client, message)
    assert approved["status"] == "approved"
    assert approved["approval"]["approver_display_name"] == "Bob Manager"

    sent = client.post(f"{BASE}/{message['id']}/send", headers={"x-user": "bob"})
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    again = client.post(f"{BASE}/{message['id']}/send", headers={"x-user": "bob"})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "send_exists"
    assert again.json()["detail"]["send"]["status"] == "sent"

    status = client.get(f"{BASE}/{message['id']}").json()
    assert status["status"] == "sent"
    assert fake.delivered == 1


def test_send_without_approval_is_409(api) -> None:
    client, fake = api
    message = _create(client)
    response = client.post(f"{BASE}/{message['id']}/send")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_approved"
    assert fake.send_requests == []


def test_edit_after_approval_returns_to_draft(api) -> None:
    client, _ = api
    message = _create(client)
    _approve(client, message)
    edited = client.post(
        f"{BASE}/{message['id']}/revisions",
        json={
            "subject": "Documents request",
            "body": "Edited",
            "recipient": RECIPIENT,
            "base_revision_id": message["current_revision"]["id"],
        },
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["status"] == "draft" and body["approval"] is None
    assert body["current_revision"]["number"] == 2

    stale = client.post(
        f"{BASE}/{message['id']}/approve",
        json={"revision_id": message["current_revision"]["id"]},
        headers={"x-user": "bob"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_revision"


def test_concurrent_http_sends_dispatch_once(api) -> None:
    client, fake = api
    fake.send_delay = 0.05
    message = _create(client)
    _approve(client, message)

    def send(_: int) -> int:
        return client.post(f"{BASE}/{message['id']}/send", headers={"x-user": "bob"}).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(send, range(4)))

    assert codes == [200, 409, 409, 409]
    assert len(fake.send_requests) == 1


def test_test_mode_summary_counts_suppressed_separately() -> None:
    client, fake = _build(enabled=False)
    message = _create(client)
    _approve(client, message)
    sent = client.post(f"{BASE}/{message['id']}/send", headers={"x-user": "bob"})
    assert sent.json()["status"] == "suppressed_test_mode"
    assert sent.json()["test_mode"] is True

    summary = client.get(f"{BASE}/send-summary").json()
    assert summary["suppressed_test_mode"] == 1
    assert summary["sent"] == 0
    assert fake.send_requests == []


def test_invalid_recipient_is_422_and_other_case_is_404(api) -> None:
    client, _ = api
    bad = client.post(BASE, json={"subject": "s", "body": "b", "recipient": "nope"})
    assert bad.status_code == 422
    message = _create(client)
    assert client.get(f"/cases/case-2/messages/{message['id']}").status_code == 404


def test_router_without_session_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the real auth dependencies and no `dp_session` cookie nothing runs."""
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        BASE, json={"subject": "s", "body": "b", "recipient": RECIPIENT}
    )
    assert response.status_code == 401
