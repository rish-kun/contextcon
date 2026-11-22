"""Act-step records: immutable message revisions, approvals bound to one revision,
and the send record that guarantees a message leaves at most once.

Every record is a frozen dataclass. A revision is never updated: an edit is a new
revision. A send record changes only through compare-and-set status transitions in
the repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SendStatus(StrEnum):
    SENDING = "sending"
    SENT = "sent"
    SUPPRESSED_TEST_MODE = "suppressed_test_mode"
    FAILED = "failed"
    UNKNOWN = "unknown"


class MessageStatus(StrEnum):
    """What the UI shows for a message: `draft → approved → <send status>`."""

    DRAFT = "draft"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    SUPPRESSED_TEST_MODE = "suppressed_test_mode"
    FAILED = "failed"
    UNKNOWN = "unknown"


# A send in one of these states means the message has left or may have left. While a
# message has such a send, it cannot be edited and no other send may start. In Postgres
# this is a partial unique index on sends(message_id) WHERE status IN (...).
ACTIVE_SEND_STATUSES: frozenset[SendStatus] = frozenset(
    {SendStatus.SENDING, SendStatus.SENT, SendStatus.UNKNOWN}
)


@dataclass(frozen=True, slots=True)
class Actor:
    """The signed-in person acting. Approval needs both an id and a display name."""

    user_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    case_id: str
    current_revision_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRevision:
    """One immutable version of the email.

    The recipient is always typed in by a person (`entered_by_user_id`). DealProof never
    scrapes or infers contact details.
    """

    id: str
    message_id: str
    number: int
    subject: str
    body: str
    recipient: str
    entered_by_user_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Approval:
    """A named person approving exactly one revision."""

    id: str
    message_id: str
    revision_id: str
    approver_user_id: str
    approver_display_name: str
    approved_at: datetime


@dataclass(frozen=True, slots=True)
class SendRecord:
    """The single send of one approved revision.

    `send_key` is persisted before dispatch and doubles as the provider idempotency
    key, so a retry of the same send can never produce a second email at the provider.
    """

    id: str
    message_id: str
    case_id: str
    revision_id: str
    approval_id: str
    send_key: str
    status: SendStatus
    test_mode: bool
    attempts: int
    created_at: datetime
    # First hand-off to the provider (also the look-back anchor for reconciliation).
    dispatched_at: datetime | None = None
    # Latest hand-off; a send stuck in `sending` long after this is treated as unknown.
    last_attempt_at: datetime | None = None
    completed_at: datetime | None = None
    provider_message_id: str | None = None
    error: str | None = None
    # Bumped by every status transition. Each transition names the generation it read,
    # so a stale snapshot can never overwrite a newer attempt's state.
    generation: int = 1
    # The exact request handed to the provider (from, to, subject, text, tags). Every
    # retry re-sends these bytes, so the provider's idempotency check never sees a
    # different payload under the same key.
    payload: dict[str, Any] | None = field(default=None, compare=False)


# --- errors -------------------------------------------------------------------------


class ActError(Exception):
    """Base for Act-step errors. Routers map subclasses to HTTP status codes."""


class NotFoundError(ActError):
    pass


class ValidationError(ActError):
    pass


class ConflictError(ActError):
    pass


class NotApprovedError(ConflictError):
    """The current revision has no approval (never approved, or edited since)."""


class StaleRevisionError(ConflictError):
    """The caller acted on a revision that is no longer current."""


class DeliveryModeChangedError(ConflictError):
    """The caller confirmed a test-mode send but sending is now live, or the reverse."""


class SendExistsError(ConflictError):
    """The message has left, may have left, or is leaving right now."""

    def __init__(self, message: str, send: SendRecord) -> None:
        super().__init__(message)
        self.send = send


class EmailNotConfiguredError(ActError):
    """Real sending is enabled but the API key or sender address is missing."""


# --- validation ---------------------------------------------------------------------

# Deliberately simple: one address, no display name, no whitespace. Provider-side
# validation still applies; this catches typos before approval.
_EMAIL_RE = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")

MAX_SUBJECT_LEN = 300
MAX_BODY_LEN = 50_000


def normalise_recipient(value: str) -> str:
    recipient = value.strip()
    if not _EMAIL_RE.match(recipient) or len(recipient) > 320:
        raise ValidationError("Recipient must be a single email address.")
    return recipient


def validate_content(subject: str, body: str) -> tuple[str, str]:
    subject = subject.strip()
    if not subject:
        raise ValidationError("Subject is required.")
    if len(subject) > MAX_SUBJECT_LEN or "\n" in subject or "\r" in subject:
        raise ValidationError(f"Subject must be one line of at most {MAX_SUBJECT_LEN} chars.")
    if not body.strip():
        raise ValidationError("Body is required.")
    if len(body) > MAX_BODY_LEN:
        raise ValidationError(f"Body must be at most {MAX_BODY_LEN} characters.")
    return subject, body
