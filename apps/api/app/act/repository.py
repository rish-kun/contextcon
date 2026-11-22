"""Storage for the Act step, behind a small Protocol.

`app/db/` (SQLAlchemy + Postgres) is being built separately and was not on `main` when
this module was written, so this file defines the Protocol plus an in-memory
implementation. The Postgres implementation must keep the same guarantees:

* `sends.send_key` UNIQUE and `sends.revision_id` UNIQUE.
* Partial unique index `sends(message_id) WHERE status IN ('sending','sent','unknown')`,
  so two concurrent `create_send` calls for one message cannot both insert; the loser
  gets an IntegrityError, which maps to `SendExistsError`.
* `transition_send` is a compare-and-set:
  `UPDATE sends SET ... WHERE id = :id AND status = ANY(:from) RETURNING *`.
* `add_revision`, `add_approval` and `create_send` lock the message row
  (`SELECT ... FOR UPDATE`) so an edit cannot slip in between an approval check and a
  send claim.
* Revisions and approvals are insert-only.
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, Protocol

from app.act.models import (
    ACTIVE_SEND_STATUSES,
    Approval,
    Message,
    MessageRevision,
    NotFoundError,
    SendExistsError,
    SendRecord,
    SendStatus,
    StaleRevisionError,
)


class ActRepository(Protocol):
    async def create_message(self, message: Message, first_revision: MessageRevision) -> None: ...

    async def get_message(self, message_id: str) -> Message | None: ...

    async def get_revision(self, revision_id: str) -> MessageRevision | None: ...

    async def list_revisions(self, message_id: str) -> list[MessageRevision]: ...

    async def add_revision(self, revision: MessageRevision) -> Message:
        """Append a revision and make it current. The repository assigns
        `revision.number` (previous count + 1) under the message lock.

        Raises `SendExistsError` if the message has an active send.
        """
        ...

    async def add_approval(self, approval: Approval) -> None:
        """Record an approval. Raises `StaleRevisionError` if `approval.revision_id` is
        not the message's current revision at write time."""
        ...

    async def get_approval(self, revision_id: str) -> Approval | None:
        """The latest approval of this revision, if any."""
        ...

    async def create_send(self, send: SendRecord) -> SendRecord:
        """Insert a send in status `sending` (or the given status).

        Raises `SendExistsError` if the revision already has a send or the message has
        an active send. Raises `StaleRevisionError` if the revision is not current.
        """
        ...

    async def get_send_for_revision(self, revision_id: str) -> SendRecord | None: ...

    async def get_latest_send(self, message_id: str) -> SendRecord | None: ...

    async def transition_send(
        self, send_id: str, from_statuses: Iterable[SendStatus], **changes: Any
    ) -> SendRecord | None:
        """Atomically apply `changes` if the send's status is in `from_statuses`.

        Returns the updated record, or None if the status had moved on (lost race).
        """
        ...

    async def count_sends_by_status(self, case_id: str) -> dict[SendStatus, int]: ...


class InMemoryActRepository:
    """Thread-safe in-memory implementation for tests and local runs.

    All methods hold one lock and never await while holding it, so they are atomic for
    both asyncio tasks and threads (FastAPI's sync test client runs in threads).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._messages: dict[str, Message] = {}
        self._revisions: dict[str, MessageRevision] = {}
        self._revisions_by_message: dict[str, list[str]] = {}
        self._approvals: dict[str, list[Approval]] = {}  # revision_id -> approvals
        self._sends: dict[str, SendRecord] = {}
        self._send_by_revision: dict[str, str] = {}
        self._send_keys: set[str] = set()
        self._sends_by_message: dict[str, list[str]] = {}

    async def create_message(self, message: Message, first_revision: MessageRevision) -> None:
        with self._lock:
            if message.id in self._messages:
                raise ValueError(f"message {message.id} exists")
            self._messages[message.id] = message
            self._revisions[first_revision.id] = first_revision
            self._revisions_by_message[message.id] = [first_revision.id]

    async def get_message(self, message_id: str) -> Message | None:
        with self._lock:
            return self._messages.get(message_id)

    async def get_revision(self, revision_id: str) -> MessageRevision | None:
        with self._lock:
            return self._revisions.get(revision_id)

    async def list_revisions(self, message_id: str) -> list[MessageRevision]:
        with self._lock:
            ids = self._revisions_by_message.get(message_id, [])
            return [self._revisions[i] for i in ids]

    async def add_revision(self, revision: MessageRevision) -> Message:
        with self._lock:
            message = self._require_message(revision.message_id)
            active = self._active_send(message.id)
            if active is not None:
                raise SendExistsError(f"Message cannot be edited: send is {active.status}.", active)
            revision = replace(revision, number=len(self._revisions_by_message[message.id]) + 1)
            self._revisions[revision.id] = revision
            self._revisions_by_message[message.id].append(revision.id)
            updated = replace(message, current_revision_id=revision.id)
            self._messages[message.id] = updated
            return updated

    async def add_approval(self, approval: Approval) -> None:
        with self._lock:
            message = self._require_message(approval.message_id)
            if message.current_revision_id != approval.revision_id:
                raise StaleRevisionError("Revision is no longer current.")
            self._approvals.setdefault(approval.revision_id, []).append(approval)

    async def get_approval(self, revision_id: str) -> Approval | None:
        with self._lock:
            approvals = self._approvals.get(revision_id)
            return approvals[-1] if approvals else None

    async def create_send(self, send: SendRecord) -> SendRecord:
        with self._lock:
            message = self._require_message(send.message_id)
            if message.current_revision_id != send.revision_id:
                raise StaleRevisionError("Revision is no longer current.")
            existing_id = self._send_by_revision.get(send.revision_id)
            if existing_id is not None:
                existing = self._sends[existing_id]
                raise SendExistsError(f"A send already exists ({existing.status}).", existing)
            active = self._active_send(send.message_id)
            if active is not None:
                raise SendExistsError(f"A send already exists ({active.status}).", active)
            if send.send_key in self._send_keys:
                raise ValueError("duplicate send key")
            self._sends[send.id] = send
            self._send_by_revision[send.revision_id] = send.id
            self._send_keys.add(send.send_key)
            self._sends_by_message.setdefault(send.message_id, []).append(send.id)
            return send

    async def get_send_for_revision(self, revision_id: str) -> SendRecord | None:
        with self._lock:
            send_id = self._send_by_revision.get(revision_id)
            return self._sends[send_id] if send_id else None

    async def get_latest_send(self, message_id: str) -> SendRecord | None:
        with self._lock:
            ids = self._sends_by_message.get(message_id)
            return self._sends[ids[-1]] if ids else None

    async def transition_send(
        self, send_id: str, from_statuses: Iterable[SendStatus], **changes: Any
    ) -> SendRecord | None:
        allowed = frozenset(from_statuses)
        with self._lock:
            current = self._sends.get(send_id)
            if current is None:
                raise NotFoundError("send not found")
            if current.status not in allowed:
                return None
            new_status = changes.get("status", current.status)
            if new_status in ACTIVE_SEND_STATUSES:
                other = self._active_send(current.message_id)
                if other is not None and other.id != send_id:
                    return None
            updated = replace(current, **changes)
            self._sends[send_id] = updated
            return updated

    async def count_sends_by_status(self, case_id: str) -> dict[SendStatus, int]:
        with self._lock:
            counts = Counter(s.status for s in self._sends.values() if s.case_id == case_id)
            return {status: counts.get(status, 0) for status in SendStatus}

    # --- internal (call with the lock held) -------------------------------------------

    def _require_message(self, message_id: str) -> Message:
        message = self._messages.get(message_id)
        if message is None:
            raise NotFoundError("message not found")
        return message

    def _active_send(self, message_id: str) -> SendRecord | None:
        for send_id in self._sends_by_message.get(message_id, []):
            send = self._sends[send_id]
            if send.status in ACTIVE_SEND_STATUSES:
                return send
        return None
