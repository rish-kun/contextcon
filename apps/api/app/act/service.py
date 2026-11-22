"""Act-step service: edit → approve → send exactly once.

State machine for one message (what `MessageState.status` reports):

    draft ──approve(current revision)──▶ approved ──send──▶ sending
    sending ──provider accepted──────────▶ sent                 (terminal)
    sending ──EMAIL_SEND_ENABLED=false───▶ suppressed_test_mode (nothing left)
    sending ──provider rejected──────────▶ failed               (definitely not sent)
    sending ──timeout / lost response────▶ unknown              (may have been sent)
    unknown ──reconcile: found───────────▶ sent
    unknown ──reconcile: absent, on send─▶ sending (same send key, same payload)
    unknown ──confirm_outcome (a person)─▶ sent | failed
    failed  ──send again─────────────────▶ sending (same send key, same payload)
    suppressed_test_mode ──send, real sending now enabled──▶ sending

Rules:
* An edit creates a new revision and drops the message back to `draft`; approval binds
  to one revision id, so the new revision needs a fresh approval. Edits are refused
  while a send is `sending`, `sent` or `unknown`.
* The send record, with its unique send key, is persisted before the provider call.
  The key is the provider idempotency key and is reused by every retry of that send.
* The exact provider payload is persisted with the send and re-sent byte for byte on
  every retry, so the provider's idempotency check never sees a different payload.
* `unknown` is never retried blindly: the provider is searched first for an email
  tagged with the send key. Only a complete search that finds nothing allows a retry,
  and only while Resend's 24-hour idempotency window still deduplicates
  (`idempotency_window`, 23 h by default). After that, or while sending is disabled,
  the send stays `unknown` until a person confirms the outcome (`confirm_outcome`).
* A retry re-checks, under the message lock, that its revision is still current and
  approved, and every transition compares the generation it read, so a stale caller
  can neither send a superseded body nor overwrite a newer attempt.
* A send stuck in `sending` (process died mid-call) becomes `unknown` once it is older
  than `stale_sending_after`, then follows the same reconcile path.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.act.models import (
    ACTIVE_SEND_STATUSES,
    Actor,
    Approval,
    EmailNotConfiguredError,
    Message,
    MessageRevision,
    MessageStatus,
    NotApprovedError,
    NotFoundError,
    SendExistsError,
    SendRecord,
    SendStatus,
    StaleRevisionError,
    ValidationError,
    normalise_recipient,
    validate_content,
)
from app.act.repository import ActRepository
from app.act.resend import SEND_KEY_TAG, EmailProvider, EmailProviderError


@dataclass(frozen=True, slots=True)
class SendConfig:
    enabled: bool
    sender: str = ""
    stale_sending_after: timedelta = timedelta(minutes=2)
    # How far before the first dispatch the provider search looks (clock skew margin).
    reconcile_lookback: timedelta = timedelta(minutes=10)
    reconcile_max_pages: int = 10
    reconcile_page_size: int = 100
    # Resend keeps idempotency keys for 24 hours; stop automatic retries an hour early.
    idempotency_window: timedelta = timedelta(hours=23)


@dataclass(frozen=True, slots=True)
class MessageState:
    message: Message
    revisions: list[MessageRevision]
    current_revision: MessageRevision
    approval: Approval | None  # approval of the current revision only
    send: SendRecord | None  # latest send of this message
    status: MessageStatus


@dataclass(frozen=True, slots=True)
class Lookup:
    outcome: Literal["found", "absent", "inconclusive"]
    provider_message_id: str | None = None
    note: str = ""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def _new_send_key() -> str:
    # Valid as both a Resend Idempotency-Key and a tag value ([A-Za-z0-9_-], ≤256).
    return f"dp-send-{uuid.uuid4().hex}"


class ActService:
    def __init__(
        self,
        repo: ActRepository,
        config: SendConfig,
        provider: EmailProvider | None = None,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._repo = repo
        self._config = config
        self._provider = provider
        self._clock = clock

    # --- drafting and approval --------------------------------------------------------

    async def create_message(
        self, case_id: str, actor: Actor, *, subject: str, body: str, recipient: str
    ) -> MessageState:
        subject, body = validate_content(subject, body)
        recipient = normalise_recipient(recipient)
        now = self._clock()
        message_id = _new_id()
        revision = MessageRevision(
            id=_new_id(),
            message_id=message_id,
            number=1,
            subject=subject,
            body=body,
            recipient=recipient,
            entered_by_user_id=actor.user_id,
            created_at=now,
        )
        message = Message(
            id=message_id, case_id=case_id, current_revision_id=revision.id, created_at=now
        )
        await self._repo.create_message(message, revision)
        return await self.get_state(case_id, message_id)

    async def revise(
        self,
        case_id: str,
        message_id: str,
        actor: Actor,
        *,
        subject: str,
        body: str,
        recipient: str,
        base_revision_id: str | None = None,
    ) -> MessageState:
        """Create a new immutable revision. Any approval of earlier revisions stops
        counting. `base_revision_id`, if given, must be the current revision."""
        message = await self._require_message(case_id, message_id)
        if base_revision_id is not None and base_revision_id != message.current_revision_id:
            raise StaleRevisionError("The message changed since you loaded it.")
        subject, body = validate_content(subject, body)
        recipient = normalise_recipient(recipient)
        revision = MessageRevision(
            id=_new_id(),
            message_id=message_id,
            number=0,  # assigned by the repository
            subject=subject,
            body=body,
            recipient=recipient,
            entered_by_user_id=actor.user_id,
            created_at=self._clock(),
        )
        await self._repo.add_revision(revision)
        return await self.get_state(case_id, message_id)

    async def approve(
        self, case_id: str, message_id: str, actor: Actor, *, revision_id: str
    ) -> MessageState:
        """Bind a named approver and a timestamp to exactly one revision."""
        if not actor.user_id.strip() or not actor.display_name.strip():
            raise ValidationError("Approval needs a named, signed-in user.")
        message = await self._require_message(case_id, message_id)
        if revision_id != message.current_revision_id:
            raise StaleRevisionError("Only the current revision can be approved.")
        revision = await self._repo.get_revision(revision_id)
        if revision is None:  # pragma: no cover - revisions are never deleted
            raise NotFoundError("Revision not found.")
        # A drafted revision has no recipient yet; it must be typed in (an edit) first.
        try:
            normalise_recipient(revision.recipient)
        except ValidationError as exc:
            raise ValidationError("Enter the recipient's email address before approving.") from exc
        validate_content(revision.subject, revision.body)
        latest = await self._repo.get_latest_send(message_id)
        if latest is not None and latest.status in ACTIVE_SEND_STATUSES:
            raise SendExistsError(f"Message is already {latest.status}.", latest)
        approval = Approval(
            id=_new_id(),
            message_id=message_id,
            revision_id=revision_id,
            approver_user_id=actor.user_id,
            approver_display_name=actor.display_name.strip(),
            approved_at=self._clock(),
        )
        await self._repo.add_approval(approval)
        return await self.get_state(case_id, message_id)

    # --- sending ----------------------------------------------------------------------

    async def send(self, case_id: str, message_id: str, actor: Actor) -> SendRecord:
        """Send the approved current revision at most once.

        Raises `NotApprovedError` without an approval of the current revision and
        `SendExistsError` when the message has been sent, is being sent, or (in test
        mode) was already suppressed.
        """
        message = await self._require_message(case_id, message_id)
        revision_id = message.current_revision_id
        existing = await self._repo.get_send_for_revision(revision_id)
        if existing is not None:
            return await self._resume(existing)

        latest = await self._repo.get_latest_send(message_id)
        if latest is not None and latest.status in ACTIVE_SEND_STATUSES:
            raise SendExistsError(f"Message is already {latest.status}.", latest)
        approval = await self._repo.get_approval(revision_id)
        if approval is None:
            raise NotApprovedError("The current revision has not been approved.")
        self._require_configured()
        revision = await self._repo.get_revision(revision_id)
        if revision is None:  # pragma: no cover - revisions are never deleted
            raise NotFoundError("Revision not found.")

        now = self._clock()
        send_key = _new_send_key()
        claimed = await self._repo.create_send(
            SendRecord(
                id=_new_id(),
                message_id=message_id,
                case_id=case_id,
                revision_id=revision_id,
                approval_id=approval.id,
                send_key=send_key,
                status=SendStatus.SENDING,
                test_mode=not self._config.enabled,
                attempts=1,
                created_at=now,
                dispatched_at=now,
                last_attempt_at=now,
                payload=self._payload(revision, send_key),
            )
        )
        return await self._dispatch(claimed)

    async def reconcile(self, case_id: str, message_id: str) -> SendRecord:
        """Resolve an `unknown` (or stale `sending`) send by asking the provider.

        Never dispatches. Other statuses are returned unchanged.
        """
        await self._require_message(case_id, message_id)
        send = await self._repo.get_latest_send(message_id)
        if send is None:
            raise NotFoundError("This message has no send to reconcile.")
        send = await self._expire_if_stale(send)
        if send.status is not SendStatus.UNKNOWN:
            return send
        resolved, _ = await self._reconcile_unknown(send)
        return resolved

    async def confirm_outcome(
        self, case_id: str, message_id: str, actor: Actor, *, delivered: bool, note: str = ""
    ) -> SendRecord:
        """A named person settles an `unknown` send after checking outside DealProof
        (e.g. in the Resend dashboard or with the recipient). Never dispatches.

        `delivered=True` records `sent`; `False` records `failed`, after which a normal
        send retries with the same key and payload.
        """
        if not actor.user_id.strip() or not actor.display_name.strip():
            raise ValidationError("Confirming an outcome needs a named, signed-in user.")
        await self._require_message(case_id, message_id)
        send = await self._repo.get_latest_send(message_id)
        if send is None:
            raise NotFoundError("This message has no send to confirm.")
        send = await self._expire_if_stale(send)
        if send.status is not SendStatus.UNKNOWN:
            raise SendExistsError(f"Only an unknown send can be confirmed ({send.status}).", send)
        who = actor.display_name.strip()
        detail = f": {note.strip()[:500]}" if note.strip() else ""
        verdict = "delivered" if delivered else "not delivered"
        updated = await self._repo.transition_send(
            send.id,
            [SendStatus.UNKNOWN],
            expected_generation=send.generation,
            status=SendStatus.SENT if delivered else SendStatus.FAILED,
            error=f"confirmed {verdict} by {who}{detail}",
            completed_at=self._clock(),
        )
        if updated is None:
            current = await self._reload(send)
            raise SendExistsError(f"Send moved to {current.status} concurrently.", current)
        return updated

    async def send_summary(self, case_id: str) -> dict[SendStatus, int]:
        """Counts per send status. `sent` is real provider acceptance;
        `suppressed_test_mode` is counted separately and never as sent."""
        return await self._repo.count_sends_by_status(case_id)

    # --- reads ------------------------------------------------------------------------

    async def get_state(self, case_id: str, message_id: str) -> MessageState:
        message = await self._require_message(case_id, message_id)
        revisions = await self._repo.list_revisions(message_id)
        current = next(r for r in revisions if r.id == message.current_revision_id)
        approval = await self._repo.get_approval(current.id)
        send = await self._repo.get_latest_send(message_id)
        if send is not None and (
            send.revision_id == current.id or send.status in ACTIVE_SEND_STATUSES
        ):
            status = MessageStatus(send.status.value)
        elif approval is not None:
            status = MessageStatus.APPROVED
        else:
            status = MessageStatus.DRAFT
        return MessageState(
            message=message,
            revisions=revisions,
            current_revision=current,
            approval=approval,
            send=send,
            status=status,
        )

    # --- internals --------------------------------------------------------------------

    async def _require_message(self, case_id: str, message_id: str) -> Message:
        message = await self._repo.get_message(message_id)
        if message is None or message.case_id != case_id:
            raise NotFoundError("Message not found.")
        return message

    def _require_configured(self) -> None:
        if not self._config.enabled:
            return
        if self._provider is None or not self._config.sender:
            raise EmailNotConfiguredError(
                "Email sending is enabled but the provider key or sender is missing."
            )

    async def _resume(self, send: SendRecord) -> SendRecord:
        """Handle a send call for a revision that already has a send record."""
        send = await self._expire_if_stale(send)
        match send.status:
            case SendStatus.SENT:
                raise SendExistsError("This message has already been sent.", send)
            case SendStatus.SENDING:
                raise SendExistsError("This message is being sent right now.", send)
            case SendStatus.SUPPRESSED_TEST_MODE if not self._config.enabled:
                raise SendExistsError("Already processed in test mode; nothing was sent.", send)
            case SendStatus.UNKNOWN:
                resolved, lookup = await self._reconcile_unknown(send)
                if lookup.outcome != "absent":
                    return resolved
                if not self._config.enabled:
                    # Never turn a possibly-sent email into "suppressed": keep it unknown.
                    return await self._annotate(
                        resolved, "sending is disabled; the earlier attempt is still unknown"
                    )
                if self._past_idempotency_window(resolved):
                    return await self._annotate(
                        resolved,
                        "provider idempotency window has passed; confirm the outcome manually",
                    )
                return await self._retry(resolved, from_status=SendStatus.UNKNOWN)
            case SendStatus.FAILED | SendStatus.SUPPRESSED_TEST_MODE:
                self._require_configured()
                return await self._retry(send, from_status=send.status)
        raise AssertionError(f"unhandled status {send.status}")  # pragma: no cover

    async def _retry(self, send: SendRecord, *, from_status: SendStatus) -> SendRecord:
        now = self._clock()
        payload = send.payload
        if from_status is SendStatus.SUPPRESSED_TEST_MODE or payload is None:
            # Nothing reached the provider under this key yet, so the payload may be
            # rebuilt (e.g. the sender address was only configured afterwards).
            revision = await self._repo.get_revision(send.revision_id)
            if revision is None:  # pragma: no cover - revisions are never deleted
                raise NotFoundError("Revision not found.")
            payload = self._payload(revision, send.send_key)
        claimed = await self._repo.claim_retry(
            send.id,
            from_status,
            send.generation,
            status=SendStatus.SENDING,
            test_mode=not self._config.enabled,
            attempts=send.attempts + 1,
            last_attempt_at=now,
            dispatched_at=send.dispatched_at or now,
            completed_at=None,
            error=None,
            payload=payload,
        )
        if claimed is None:
            current = await self._reload(send)
            raise SendExistsError(f"Send moved to {current.status} concurrently.", current)
        return await self._dispatch(claimed)

    async def _dispatch(self, send: SendRecord) -> SendRecord:
        """Hand a claimed (`sending`) send to the provider and record the outcome."""
        if send.test_mode:
            return await self._finish(send, SendStatus.SUPPRESSED_TEST_MODE)
        payload = send.payload
        if payload is None or self._provider is None:  # pragma: no cover - guarded earlier
            return await self._finish(send, SendStatus.FAILED, error="internal: not dispatchable")
        try:
            result = await self._provider.send_email(
                idempotency_key=send.send_key,
                sender=payload["from"],
                to=payload["to"],
                subject=payload["subject"],
                text=payload["text"],
                tags=dict(payload["tags"]),
            )
        except Exception as exc:  # outcome unknown: it must never be retried blindly
            return await self._finish(send, SendStatus.UNKNOWN, error=f"dispatch error: {exc!r}")
        match result.outcome:
            case "accepted":
                return await self._finish(
                    send, SendStatus.SENT, provider_message_id=result.provider_message_id
                )
            case "rejected":
                return await self._finish(send, SendStatus.FAILED, error=result.error)
            case _:
                return await self._finish(send, SendStatus.UNKNOWN, error=result.error)

    async def _finish(
        self,
        send: SendRecord,
        status: SendStatus,
        *,
        provider_message_id: str | None = None,
        error: str | None = None,
    ) -> SendRecord:
        terminal = status is not SendStatus.UNKNOWN
        # A confirmed acceptance also settles a send that was meanwhile expired to
        # `unknown`; any other outcome only applies while the send is still ours.
        from_statuses = [SendStatus.SENDING]
        if status is SendStatus.SENT:
            from_statuses.append(SendStatus.UNKNOWN)
        # Fenced on the attempt number: a newer attempt (after an expiry and retry) owns
        # the record now, and this older attempt's outcome must not overwrite it.
        updated = await self._repo.transition_send(
            send.id,
            from_statuses,
            expected_attempts=send.attempts,
            status=status,
            provider_message_id=provider_message_id or send.provider_message_id,
            error=error,
            completed_at=self._clock() if terminal else None,
        )
        return updated if updated is not None else await self._reload(send)

    async def _expire_if_stale(self, send: SendRecord) -> SendRecord:
        if send.status is not SendStatus.SENDING:
            return send
        started = send.last_attempt_at or send.created_at
        if self._clock() - started < self._config.stale_sending_after:
            return send
        updated = await self._repo.transition_send(
            send.id,
            [SendStatus.SENDING],
            expected_generation=send.generation,
            status=SendStatus.UNKNOWN,
            error="send did not finish; outcome unknown",
        )
        return updated if updated is not None else await self._reload(send)

    async def _reconcile_unknown(self, send: SendRecord) -> tuple[SendRecord, Lookup]:
        lookup = await self._lookup(send)
        if lookup.outcome == "found":
            updated = await self._repo.transition_send(
                send.id,
                [SendStatus.UNKNOWN],
                expected_generation=send.generation,
                status=SendStatus.SENT,
                provider_message_id=lookup.provider_message_id,
                error=None,
                completed_at=self._clock(),
            )
        else:
            updated = await self._repo.transition_send(
                send.id,
                [SendStatus.UNKNOWN],
                expected_generation=send.generation,
                error=f"reconcile: {lookup.note}",
            )
        if updated is None:
            # Someone else resolved or retried it meanwhile; never act on stale state.
            current = await self._reload(send)
            return current, Lookup("inconclusive", note="send changed concurrently")
        return updated, lookup

    async def _lookup(self, send: SendRecord) -> Lookup:
        """Search the provider for an email tagged with this send key."""
        if self._provider is None:
            return Lookup("inconclusive", note="no email provider configured")
        if send.payload is not None:
            subject, recipient = send.payload["subject"], send.payload["to"]
        else:
            revision = await self._repo.get_revision(send.revision_id)
            if revision is None:  # pragma: no cover - revisions are never deleted
                return Lookup("inconclusive", note="revision missing")
            subject, recipient = revision.subject, revision.recipient
        anchor = send.dispatched_at or send.created_at
        cutoff = anchor - self._config.reconcile_lookback
        recipient = recipient.lower()
        after: str | None = None
        try:
            for _ in range(self._config.reconcile_max_pages):
                page = await self._provider.list_emails(
                    limit=self._config.reconcile_page_size, after=after
                )
                for item in page.data:
                    if item.created_at is not None and item.created_at < cutoff:
                        return Lookup("absent", note="no email with this send key")
                    if item.subject != subject:
                        continue
                    if not any(recipient in to.lower() for to in item.to):
                        continue
                    detail = await self._provider.get_email(item.id)
                    if detail.tags.get(SEND_KEY_TAG) == send.send_key:
                        return Lookup("found", provider_message_id=detail.id)
                if not page.has_more or not page.data:
                    return Lookup("absent", note="no email with this send key")
                after = page.data[-1].id
        except EmailProviderError as exc:
            return Lookup("inconclusive", note=f"provider lookup failed: {exc}")
        return Lookup("inconclusive", note="search window exceeded the page limit")

    def _payload(self, revision: MessageRevision, send_key: str) -> dict[str, object]:
        return {
            "from": self._config.sender,
            "to": revision.recipient,
            "subject": revision.subject,
            "text": revision.body,
            "tags": {SEND_KEY_TAG: send_key},
        }

    def _past_idempotency_window(self, send: SendRecord) -> bool:
        anchor = send.dispatched_at or send.created_at
        return self._clock() - anchor >= self._config.idempotency_window

    async def _annotate(self, send: SendRecord, note: str) -> SendRecord:
        """Record why an `unknown` send was left alone; never changes its status."""
        updated = await self._repo.transition_send(
            send.id, [SendStatus.UNKNOWN], expected_generation=send.generation, error=note
        )
        return updated if updated is not None else await self._reload(send)

    async def _reload(self, send: SendRecord) -> SendRecord:
        current = await self._repo.get_send_for_revision(send.revision_id)
        if current is None:  # pragma: no cover - sends are never deleted
            raise NotFoundError("send not found")
        return current
