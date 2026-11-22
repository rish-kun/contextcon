"""In-process fake of the Resend API, served through httpx's MockTransport.

No test ever opens a network connection or sends a real email.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx2 as httpx

from app.act.models import Actor
from app.act.repository import InMemoryActRepository
from app.act.resend import ResendClient
from app.act.service import ActService, SendConfig

ALICE = Actor(user_id="u-alice", display_name="Alice Analyst")
BOB = Actor(user_id="u-bob", display_name="Bob Manager")
SENDER = "DealProof <requests@example.test>"
RECIPIENT = "seller@example.test"


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 22, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@dataclass
class StoredEmail:
    id: str
    to: list[str]
    subject: str
    sender: str
    text: str
    tags: dict[str, str]
    created_at: datetime


@dataclass
class FakeResend:
    """Behaves like Resend for POST /emails, GET /emails and GET /emails/{id}."""

    clock: FakeClock
    emails: list[StoredEmail] = field(default_factory=list)
    idempotency: dict[str, str] = field(default_factory=dict)
    send_requests: list[httpx.Request] = field(default_factory=list)
    lookup_requests: list[httpx.Request] = field(default_factory=list)
    # Knobs for failure scenarios.
    lose_response_after_accept: int = 0  # accept, then raise ReadTimeout (N times)
    reject_next_with: int | None = None  # respond with this 4xx/5xx status once
    send_delay: float = 0.0  # seconds to await inside POST /emails
    fail_lookups: bool = False
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    @property
    def delivered(self) -> int:
        """Emails Resend actually accepted (would have left)."""
        return len(self.emails)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def client(self) -> ResendClient:
        return ResendClient("re_test_key", transport=self.transport())

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/emails":
            return await self._send(request)
        self.lookup_requests.append(request)
        if self.fail_lookups:
            return httpx.Response(503, json={"name": "internal_server_error"})
        if request.method == "GET" and path == "/emails":
            return self._list(request)
        if request.method == "GET" and path.startswith("/emails/"):
            return self._get(path.removeprefix("/emails/"))
        return httpx.Response(404, json={"name": "not_found"})

    async def _send(self, request: httpx.Request) -> httpx.Response:
        self.send_requests.append(request)
        if self.send_delay:
            await asyncio.sleep(self.send_delay)
        if self.reject_next_with is not None:
            status, self.reject_next_with = self.reject_next_with, None
            return httpx.Response(status, json={"name": "error", "message": f"status {status}"})
        key = request.headers.get("Idempotency-Key")
        payload = json.loads(request.content)
        if key and key in self.idempotency:
            email_id = self.idempotency[key]  # replay: same response, nothing sent
        else:
            email_id = f"em_{next(self._ids)}"
            self.emails.append(
                StoredEmail(
                    id=email_id,
                    to=payload["to"],
                    subject=payload["subject"],
                    sender=payload["from"],
                    text=payload["text"],
                    tags={t["name"]: t["value"] for t in payload.get("tags", [])},
                    created_at=self.clock(),
                )
            )
            if key:
                self.idempotency[key] = email_id
        if self.lose_response_after_accept:
            self.lose_response_after_accept -= 1
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(200, json={"id": email_id})

    def _list(self, request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params.get("limit", 20))
        after = request.url.params.get("after")
        newest_first = list(reversed(self.emails))
        start = 0
        if after:
            start = next(i for i, e in enumerate(newest_first) if e.id == after) + 1
        page = newest_first[start : start + limit]
        return httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": start + limit < len(newest_first),
                "data": [
                    {
                        "id": e.id,
                        "to": e.to,
                        "from": e.sender,
                        "subject": e.subject,
                        # Resend's documented format: "2026-04-03 22:13:42.674981+00"
                        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S.%f+00"),
                        "last_event": "sent",
                    }
                    for e in page
                ],
            },
        )

    def _get(self, email_id: str) -> httpx.Response:
        for e in self.emails:
            if e.id == email_id:
                return httpx.Response(
                    200,
                    json={
                        "object": "email",
                        "id": e.id,
                        "to": e.to,
                        "from": e.sender,
                        "subject": e.subject,
                        "tags": [{"name": k, "value": v} for k, v in e.tags.items()],
                    },
                )
        return httpx.Response(404, json={"name": "not_found"})

    def add_unrelated_email(self, subject: str = "Other", to: str = RECIPIENT) -> None:
        self.emails.append(
            StoredEmail(
                id=f"em_{next(self._ids)}",
                to=[to],
                subject=subject,
                sender=SENDER,
                text="unrelated",
                tags={},
                created_at=self.clock(),
            )
        )


def make_service(
    *, enabled: bool = True, fake: FakeResend | None = None, clock: FakeClock | None = None
) -> tuple[ActService, FakeResend, InMemoryActRepository, FakeClock]:
    clock = clock or FakeClock()
    fake = fake or FakeResend(clock=clock)
    repo = InMemoryActRepository()
    service = ActService(
        repo, SendConfig(enabled=enabled, sender=SENDER), fake.client(), clock=clock
    )
    return service, fake, repo, clock
