import asyncio
import json

import httpx2 as httpx
import pytest

from app.act.resend import SEND_KEY_TAG, EmailProviderError, ResendClient


def _client(handler) -> ResendClient:
    return ResendClient("re_test_key", transport=httpx.MockTransport(handler))


def _send(client: ResendClient):
    return asyncio.run(
        client.send_email(
            idempotency_key="dp-send-abc",
            sender="DealProof <r@example.test>",
            to="seller@example.test",
            subject="Documents request",
            text="Hello",
            tags={SEND_KEY_TAG: "dp-send-abc"},
        )
    )


def test_send_posts_with_idempotency_key_auth_and_tag() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "em_1"})

    result = _send(_client(handler))

    assert result.outcome == "accepted"
    assert result.provider_message_id == "em_1"
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["Idempotency-Key"] == "dp-send-abc"
    assert request.headers["Authorization"] == "Bearer re_test_key"
    body = json.loads(request.content)
    assert body == {
        "from": "DealProof <r@example.test>",
        "to": ["seller@example.test"],
        "subject": "Documents request",
        "text": "Hello",
        "tags": [{"name": SEND_KEY_TAG, "value": "dp-send-abc"}],
    }


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (422, {"name": "validation_error", "message": "bad to"}, "rejected"),
        (401, {"name": "missing_api_key"}, "rejected"),
        (429, {"name": "rate_limit_exceeded"}, "rejected"),
        (409, {"name": "invalid_idempotent_request"}, "indeterminate"),
        (409, {"name": "concurrent_idempotent_requests"}, "indeterminate"),
        (500, {"name": "internal_server_error"}, "indeterminate"),
        (200, {"unexpected": True}, "indeterminate"),
    ],
)
def test_send_classifies_provider_responses(status: int, body: dict, outcome: str) -> None:
    result = _send(_client(lambda request: httpx.Response(status, json=body)))
    assert result.outcome == outcome
    assert result.provider_message_id is None


def test_timeout_is_indeterminate_and_connect_error_is_rejected() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lost", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert _send(_client(timeout)).outcome == "indeterminate"
    assert _send(_client(refused)).outcome == "rejected"


def test_list_and_get_parse_resend_shapes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/emails":
            assert request.url.params["limit"] == "50"
            assert request.url.params["after"] == "em_9"
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "has_more": True,
                    "data": [
                        {
                            "id": "em_8",
                            "to": ["seller@example.test"],
                            "subject": "Documents request",
                            "created_at": "2026-04-03 22:13:42.674981+00",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "object": "email",
                "id": "em_8",
                "to": ["seller@example.test"],
                "subject": "Documents request",
                "tags": [{"name": SEND_KEY_TAG, "value": "dp-send-abc"}],
            },
        )

    client = _client(handler)
    page = asyncio.run(client.list_emails(limit=50, after="em_9"))
    assert page.has_more is True
    (item,) = page.data
    assert item.id == "em_8" and item.to == ("seller@example.test",)
    assert item.created_at is not None and item.created_at.utcoffset().total_seconds() == 0

    detail = asyncio.run(client.get_email("em_8"))
    assert detail.tags == {SEND_KEY_TAG: "dp-send-abc"}


def test_lookup_errors_raise_provider_error() -> None:
    client = _client(lambda request: httpx.Response(503, json={"name": "unavailable"}))
    with pytest.raises(EmailProviderError):
        asyncio.run(client.list_emails())
