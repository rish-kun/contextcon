"""Minimal Resend client (httpx, no SDK).

API facts (resend.com/docs, checked 2026-11-22):
* `POST /emails` with `Authorization: Bearer <key>` and `Idempotency-Key: <key>`
  (up to 256 chars, kept for 24 hours; a repeat with the same key returns the original
  response without sending again). Success returns `{"id": ...}`.
* `GET /emails?limit=&after=` lists sent emails newest first:
  `{"object": "list", "has_more": bool, "data": [{id, to, from, subject, created_at, ...}]}`.
* `GET /emails/{id}` returns one email including `tags: [{name, value}]`.
* Tag names and values allow ASCII letters, digits, `_` and `-` only.

`send_email` never raises for provider or network trouble. It classifies the result:
`accepted` (we have an id), `rejected` (the provider definitely did not accept it) or
`indeterminate` (it may have been accepted; the caller must reconcile before retrying).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

import httpx2 as httpx

RESEND_BASE_URL = "https://api.resend.com"
SEND_KEY_TAG = "dealproof_send_key"

SendOutcome = Literal["accepted", "rejected", "indeterminate"]


@dataclass(frozen=True, slots=True)
class SendResult:
    outcome: SendOutcome
    provider_message_id: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class EmailSummary:
    id: str
    to: tuple[str, ...]
    subject: str
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class EmailPage:
    data: tuple[EmailSummary, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class EmailDetail:
    id: str
    to: tuple[str, ...]
    subject: str
    tags: dict[str, str] = field(default_factory=dict)


class EmailProviderError(Exception):
    """A lookup call failed (network or non-2xx). Lookups are read-only, so callers may
    simply leave state unchanged and try again later."""


class EmailProvider(Protocol):
    async def send_email(
        self,
        *,
        idempotency_key: str,
        sender: str,
        to: str,
        subject: str,
        text: str,
        tags: dict[str, str],
    ) -> SendResult: ...

    async def list_emails(self, *, limit: int = 100, after: str | None = None) -> EmailPage: ...

    async def get_email(self, email_id: str) -> EmailDetail: ...


class ResendClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = RESEND_BASE_URL,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Resend API key is required")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "dealproof-api",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_email(
        self,
        *,
        idempotency_key: str,
        sender: str,
        to: str,
        subject: str,
        text: str,
        tags: dict[str, str],
    ) -> SendResult:
        payload = {
            "from": sender,
            "to": [to],
            "subject": subject,
            "text": text,
            "tags": [{"name": k, "value": v} for k, v in tags.items()],
        }
        try:
            response = await self._client.post(
                "/emails", json=payload, headers={"Idempotency-Key": idempotency_key}
            )
        except httpx.ConnectError as exc:
            # The connection was never established, so the request never reached
            # Resend. (ConnectTimeout is a TimeoutException, handled below as unknown.)
            return SendResult("rejected", error=f"connect error: {exc!r}")
        except httpx.TransportError as exc:
            # Timeouts, dropped connections, protocol errors: the request may have
            # been accepted and only the response lost.
            return SendResult("indeterminate", error=f"{type(exc).__name__}: {exc!r}")
        return _classify_send_response(response)

    async def list_emails(self, *, limit: int = 100, after: str | None = None) -> EmailPage:
        params: dict[str, str | int] = {"limit": limit}
        if after:
            params["after"] = after
        body = await self._get_json("/emails", params=params)
        items = tuple(
            EmailSummary(
                id=str(item["id"]),
                to=_as_tuple(item.get("to")),
                subject=str(item.get("subject") or ""),
                created_at=_parse_time(item.get("created_at")),
            )
            for item in body.get("data") or []
        )
        return EmailPage(data=items, has_more=bool(body.get("has_more")))

    async def get_email(self, email_id: str) -> EmailDetail:
        body = await self._get_json(f"/emails/{email_id}")
        tags = {
            str(t.get("name")): str(t.get("value"))
            for t in body.get("tags") or []
            if isinstance(t, dict)
        }
        return EmailDetail(
            id=str(body["id"]),
            to=_as_tuple(body.get("to")),
            subject=str(body.get("subject") or ""),
            tags=tags,
        )

    async def _get_json(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise EmailProviderError(f"{type(exc).__name__}: {exc!r}") from exc
        if response.status_code != 200:
            raise EmailProviderError(f"HTTP {response.status_code}: {_error_text(response)}")
        try:
            body = response.json()
        except ValueError as exc:
            raise EmailProviderError("invalid JSON from provider") from exc
        if not isinstance(body, dict):
            raise EmailProviderError("unexpected response shape")
        return body


def _classify_send_response(response: httpx.Response) -> SendResult:
    status = response.status_code
    if 200 <= status < 300:
        try:
            email_id = response.json().get("id")
        except (ValueError, AttributeError):
            email_id = None
        if email_id:
            return SendResult("accepted", provider_message_id=str(email_id))
        return SendResult("indeterminate", error=f"HTTP {status} without an email id")
    detail = _error_text(response)
    if status == 409 and "concurrent" in detail:
        # Another request with this idempotency key is still being processed.
        return SendResult("indeterminate", error=f"HTTP 409: {detail}")
    if status >= 500:
        # A server error can happen after the email was queued.
        return SendResult("indeterminate", error=f"HTTP {status}: {detail}")
    # 4xx (validation, auth, rate limit, idempotency payload mismatch): not accepted.
    return SendResult("rejected", error=f"HTTP {status}: {detail}")


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(body, dict):
        name = body.get("name") or body.get("type") or ""
        message = body.get("message") or ""
        return f"{name} {message}".strip() or str(body)[:300]
    return str(body)[:300]


def _as_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    if isinstance(value, str):
        return (value,)
    return ()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
