"""Postgres implementation of `ActRepository` over the Act tables.

Mapping onto `app/db/models.py`:

* A message is a `request_lists` row (`Message.id == request_list.id`). Its current
  revision is the `message_revisions` row with the highest `revision` number.
* `MessageRevision.entered_by_user_id` is `message_revisions.created_by` ("" when the
  revision was drafted by the system rather than typed by a person).
* A send is a `send_attempts` row. The service's `sending` state is stored as
  `pending` (the database name for "reserved before calling the provider").

Guarantees (each covered by tests in `tests/act`, run against Postgres):

* `send_attempts.send_key` and `send_attempts.message_revision_id` are UNIQUE, and the
  partial unique index `uq_send_attempts_active_per_list` allows one active send per
  request list. An IntegrityError from any of them maps to `SendExistsError`.
* `add_revision`, `add_approval`, `create_send` and `claim_retry` run in one
  transaction that first takes `SELECT ... FOR UPDATE` on the request list, so the
  current-revision and approval checks and the write are atomic.
* `transition_send` is `UPDATE ... WHERE id AND status = ANY(...) [AND generation]
  [AND attempts] RETURNING`, and bumps `generation`.
* Revisions and approvals are only ever inserted (the database rejects UPDATE and
  DELETE on them as well).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.act.models import (
    Approval,
    Message,
    MessageRevision,
    NotApprovedError,
    NotFoundError,
    SendExistsError,
    SendRecord,
    SendStatus,
    StaleRevisionError,
    ValidationError,
)
from app.db import models as m
from app.db.enums import SendStatus as DbSendStatus

_TO_DB: dict[SendStatus, str] = {
    SendStatus.SENDING: DbSendStatus.PENDING.value,
    SendStatus.SENT: DbSendStatus.SENT.value,
    SendStatus.SUPPRESSED_TEST_MODE: DbSendStatus.SUPPRESSED_TEST_MODE.value,
    SendStatus.FAILED: DbSendStatus.FAILED.value,
    SendStatus.UNKNOWN: DbSendStatus.UNKNOWN.value,
}
_FROM_DB: dict[str, SendStatus] = {v: k for k, v in _TO_DB.items()}
_ACTIVE_DB = (DbSendStatus.PENDING.value, DbSendStatus.SENT.value, DbSendStatus.UNKNOWN.value)

# SendRecord fields the service may change through a transition.
_MUTABLE_SEND_FIELDS = frozenset(
    {
        "status",
        "test_mode",
        "attempts",
        "dispatched_at",
        "last_attempt_at",
        "completed_at",
        "provider_message_id",
        "error",
        "payload",
    }
)


def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _require_uuid(value: str, what: str) -> uuid.UUID:
    parsed = _uuid(value)
    if parsed is None:
        raise NotFoundError(f"{what} not found")
    return parsed


def _revision(row: m.MessageRevision) -> MessageRevision:
    return MessageRevision(
        id=str(row.id),
        message_id=str(row.request_list_id),
        number=row.revision,
        subject=row.subject,
        body=row.body,
        recipient=row.recipient,
        entered_by_user_id=str(row.created_by) if row.created_by else "",
        created_at=row.created_at,
    )


def _approval(row: m.Approval, message_id: uuid.UUID) -> Approval:
    return Approval(
        id=str(row.id),
        message_id=str(message_id),
        revision_id=str(row.message_revision_id),
        approver_user_id=str(row.user_id),
        approver_display_name=row.user_display_name,
        approved_at=row.approved_at,
    )


def _send(row: m.SendAttempt, case_id: uuid.UUID) -> SendRecord:
    return SendRecord(
        id=str(row.id),
        message_id=str(row.request_list_id),
        case_id=str(case_id),
        revision_id=str(row.message_revision_id),
        approval_id=str(row.approval_id),
        send_key=row.send_key,
        status=_FROM_DB[row.status],
        test_mode=row.test_mode,
        attempts=row.attempts,
        created_at=row.created_at,
        dispatched_at=row.dispatched_at,
        last_attempt_at=row.last_attempt_at,
        completed_at=row.completed_at,
        provider_message_id=row.provider_message_id,
        error=row.error,
        generation=row.generation,
        payload=row.payload,
    )


def _send_query() -> Select[tuple[m.SendAttempt, uuid.UUID]]:
    return select(m.SendAttempt, m.RequestList.case_id).join(
        m.RequestList, m.RequestList.id == m.SendAttempt.request_list_id
    )


class PostgresActRepository:
    """`ActRepository` on Postgres. Each method runs in its own short transaction."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    # --- messages and revisions -------------------------------------------------------

    async def create_message(self, message: Message, first_revision: MessageRevision) -> None:
        case_id = _require_uuid(message.case_id, "case")
        message_id = _require_uuid(message.id, "message")
        try:
            async with self._sm() as session, session.begin():
                session.add(
                    m.RequestList(
                        id=message_id,
                        case_id=case_id,
                        status="draft",
                        created_at=message.created_at,
                    )
                )
                await session.flush()
                session.add(self._revision_row(first_revision, case_id, number=1))
                await session.flush()
        except IntegrityError as exc:
            raise ValidationError("Unknown case or user for this message.") from exc

    async def get_message(self, message_id: str) -> Message | None:
        list_id = _uuid(message_id)
        if list_id is None:
            return None
        async with self._sm() as session:
            row = await session.get(m.RequestList, list_id)
            if row is None:
                return None
            current = await self._current_revision_id(session, list_id)
            if current is None:
                return None  # a request list whose draft was never written
            return Message(
                id=str(row.id),
                case_id=str(row.case_id),
                current_revision_id=str(current),
                created_at=row.created_at,
            )

    async def get_revision(self, revision_id: str) -> MessageRevision | None:
        rev_id = _uuid(revision_id)
        if rev_id is None:
            return None
        async with self._sm() as session:
            row = await session.get(m.MessageRevision, rev_id)
            return _revision(row) if row else None

    async def list_revisions(self, message_id: str) -> list[MessageRevision]:
        list_id = _uuid(message_id)
        if list_id is None:
            return []
        async with self._sm() as session:
            rows = await session.execute(
                select(m.MessageRevision)
                .where(m.MessageRevision.request_list_id == list_id)
                .order_by(m.MessageRevision.revision)
            )
            return [_revision(r) for r in rows.scalars()]

    async def add_revision(self, revision: MessageRevision) -> Message:
        list_id = _require_uuid(revision.message_id, "message")
        async with self._sm() as session, session.begin():
            request_list = await self._lock(session, list_id)
            active = await self._active_send(session, list_id)
            if active is not None:
                raise SendExistsError(f"Message cannot be edited: send is {active.status}.", active)
            number = (
                await session.execute(
                    select(func.coalesce(func.max(m.MessageRevision.revision), 0)).where(
                        m.MessageRevision.request_list_id == list_id
                    )
                )
            ).scalar_one() + 1
            row = self._revision_row(revision, request_list.case_id, number=number)
            session.add(row)
            try:
                await session.flush()
            except IntegrityError as exc:
                raise ValidationError("Unknown user for this revision.") from exc
            return Message(
                id=str(list_id),
                case_id=str(request_list.case_id),
                current_revision_id=str(row.id),
                created_at=request_list.created_at,
            )

    # --- approvals --------------------------------------------------------------------

    async def add_approval(self, approval: Approval) -> None:
        list_id = _require_uuid(approval.message_id, "message")
        revision_id = _require_uuid(approval.revision_id, "revision")
        user_id = _uuid(approval.approver_user_id)
        if user_id is None:
            raise ValidationError("Approval needs a named, signed-in user.")
        async with self._sm() as session, session.begin():
            await self._lock(session, list_id)
            if await self._current_revision_id(session, list_id) != revision_id:
                raise StaleRevisionError("Revision is no longer current.")
            # One approval per (revision, user): approving the same revision twice keeps
            # the first record.
            stmt = (
                pg_insert(m.Approval)
                .values(
                    id=_require_uuid(approval.id, "approval"),
                    message_revision_id=revision_id,
                    user_id=user_id,
                    user_display_name=approval.approver_display_name,
                    approved_at=approval.approved_at,
                    created_at=approval.approved_at,
                )
                .on_conflict_do_nothing(index_elements=["message_revision_id", "user_id"])
            )
            try:
                await session.execute(stmt)
            except IntegrityError as exc:
                raise ValidationError("The approver is not a known user.") from exc

    async def get_approval(self, revision_id: str) -> Approval | None:
        rev_id = _uuid(revision_id)
        if rev_id is None:
            return None
        async with self._sm() as session:
            found = (
                await session.execute(
                    select(m.Approval, m.MessageRevision.request_list_id)
                    .join(m.MessageRevision, m.MessageRevision.id == m.Approval.message_revision_id)
                    .where(m.Approval.message_revision_id == rev_id)
                    .order_by(m.Approval.approved_at.desc(), m.Approval.created_at.desc())
                    .limit(1)
                )
            ).first()
            return _approval(found[0], found[1]) if found else None

    # --- sends ------------------------------------------------------------------------

    async def create_send(self, send: SendRecord) -> SendRecord:
        list_id = _require_uuid(send.message_id, "message")
        revision_id = _require_uuid(send.revision_id, "revision")
        approval_id = _require_uuid(send.approval_id, "approval")
        try:
            async with self._sm() as session, session.begin():
                request_list = await self._lock(session, list_id)
                if await self._current_revision_id(session, list_id) != revision_id:
                    raise StaleRevisionError("Revision is no longer current.")
                approval = await session.get(m.Approval, approval_id)
                if approval is None or approval.message_revision_id != revision_id:
                    raise NotApprovedError("The current revision has not been approved.")
                existing = await self._send_where(
                    session, m.SendAttempt.message_revision_id == revision_id
                )
                if existing is not None:
                    raise SendExistsError(f"A send already exists ({existing.status}).", existing)
                active = await self._active_send(session, list_id)
                if active is not None:
                    raise SendExistsError(f"A send already exists ({active.status}).", active)
                row = m.SendAttempt(
                    id=_require_uuid(send.id, "send"),
                    request_list_id=list_id,
                    message_revision_id=revision_id,
                    approval_id=approval_id,
                    send_key=send.send_key,
                    status=_TO_DB[send.status],
                    test_mode=send.test_mode,
                    attempts=send.attempts,
                    generation=send.generation,
                    payload=send.payload,
                    created_at=send.created_at,
                    dispatched_at=send.dispatched_at,
                    last_attempt_at=send.last_attempt_at,
                    completed_at=send.completed_at,
                    provider_message_id=send.provider_message_id,
                    error=send.error,
                )
                session.add(row)
                await session.flush()
                return _send(row, request_list.case_id)
        except IntegrityError:
            pass
        # Backstop for the unique indexes (send key, revision, one active per list).
        async with self._sm() as session:
            existing = await self._send_where(
                session,
                (m.SendAttempt.message_revision_id == revision_id)
                | (m.SendAttempt.send_key == send.send_key),
            ) or await self._active_send(session, list_id)
        if existing is None:  # pragma: no cover - the conflicting row is never deleted
            raise SendExistsError("A send already exists.", send)
        raise SendExistsError(f"A send already exists ({existing.status}).", existing)

    async def claim_retry(
        self, send_id: str, from_status: SendStatus, expected_generation: int, **changes: Any
    ) -> SendRecord | None:
        sid = _require_uuid(send_id, "send")
        try:
            return await self._claim_retry(sid, from_status, expected_generation, changes)
        except IntegrityError:
            return None  # another send of this message became active meanwhile

    async def _claim_retry(
        self,
        sid: uuid.UUID,
        from_status: SendStatus,
        expected_generation: int,
        changes: dict[str, Any],
    ) -> SendRecord | None:
        async with self._sm() as session, session.begin():
            current = await session.get(m.SendAttempt, sid)
            if current is None:
                raise NotFoundError("send not found")
            list_id, revision_id = current.request_list_id, current.message_revision_id
            await self._lock(session, list_id)
            if await self._current_revision_id(session, list_id) != revision_id:
                raise StaleRevisionError("The message was edited; this revision is superseded.")
            approved = (
                await session.execute(
                    select(m.Approval.id)
                    .where(m.Approval.message_revision_id == revision_id)
                    .limit(1)
                )
            ).first()
            if approved is None:
                raise NotApprovedError("The current revision has not been approved.")
            return await self._transition(
                session, sid, [from_status], expected_generation, None, changes
            )

    async def get_send_for_revision(self, revision_id: str) -> SendRecord | None:
        rev_id = _uuid(revision_id)
        if rev_id is None:
            return None
        async with self._sm() as session:
            return await self._send_where(session, m.SendAttempt.message_revision_id == rev_id)

    async def get_latest_send(self, message_id: str) -> SendRecord | None:
        list_id = _uuid(message_id)
        if list_id is None:
            return None
        async with self._sm() as session:
            return await self._send_where(session, m.SendAttempt.request_list_id == list_id)

    async def transition_send(
        self,
        send_id: str,
        from_statuses: Iterable[SendStatus],
        *,
        expected_generation: int | None = None,
        expected_attempts: int | None = None,
        **changes: Any,
    ) -> SendRecord | None:
        sid = _require_uuid(send_id, "send")
        try:
            async with self._sm() as session, session.begin():
                return await self._transition(
                    session,
                    sid,
                    list(from_statuses),
                    expected_generation,
                    expected_attempts,
                    changes,
                )
        except IntegrityError:
            return None  # the change would make a second send of this message active

    async def count_sends_by_status(self, case_id: str) -> dict[SendStatus, int]:
        counts = {status: 0 for status in SendStatus}
        cid = _uuid(case_id)
        if cid is None:
            return counts
        async with self._sm() as session:
            rows = await session.execute(
                select(m.SendAttempt.status, func.count())
                .join(m.RequestList, m.RequestList.id == m.SendAttempt.request_list_id)
                .where(m.RequestList.case_id == cid)
                .group_by(m.SendAttempt.status)
            )
            for status, n in rows.all():
                counts[_FROM_DB[status]] = n
        return counts

    # --- internals --------------------------------------------------------------------

    @staticmethod
    def _revision_row(
        revision: MessageRevision, case_id: uuid.UUID, *, number: int
    ) -> m.MessageRevision:
        return m.MessageRevision(
            id=_require_uuid(revision.id, "revision"),
            request_list_id=_require_uuid(revision.message_id, "message"),
            case_id=case_id,
            revision=number,
            subject=revision.subject,
            body=revision.body,
            recipient=revision.recipient,
            created_by=_uuid(revision.entered_by_user_id) if revision.entered_by_user_id else None,
            created_at=revision.created_at,
        )

    @staticmethod
    async def _lock(session: AsyncSession, list_id: uuid.UUID) -> m.RequestList:
        row = (
            await session.execute(
                select(m.RequestList).where(m.RequestList.id == list_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("message not found")
        return row

    @staticmethod
    async def _current_revision_id(session: AsyncSession, list_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await session.execute(
                select(m.MessageRevision.id)
                .where(m.MessageRevision.request_list_id == list_id)
                .order_by(m.MessageRevision.revision.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _send_where(session: AsyncSession, condition: Any) -> SendRecord | None:
        found = (
            await session.execute(
                _send_query()
                .where(condition)
                .order_by(m.SendAttempt.created_at.desc(), m.SendAttempt.id.desc())
                .limit(1)
            )
        ).first()
        return _send(found[0], found[1]) if found else None

    async def _active_send(self, session: AsyncSession, list_id: uuid.UUID) -> SendRecord | None:
        return await self._send_where(
            session,
            (m.SendAttempt.request_list_id == list_id) & m.SendAttempt.status.in_(_ACTIVE_DB),
        )

    @staticmethod
    async def _transition(
        session: AsyncSession,
        send_id: uuid.UUID,
        from_statuses: Iterable[SendStatus],
        expected_generation: int | None,
        expected_attempts: int | None,
        changes: dict[str, Any],
    ) -> SendRecord | None:
        unknown = set(changes) - _MUTABLE_SEND_FIELDS
        if unknown:
            raise ValueError(f"send fields cannot be changed: {sorted(unknown)}")
        values: dict[str, Any] = dict(changes)
        if "status" in values:
            values["status"] = _TO_DB[SendStatus(values["status"])]
        values["generation"] = m.SendAttempt.generation + 1
        values["updated_at"] = func.now()
        stmt = (
            update(m.SendAttempt)
            .where(
                m.SendAttempt.id == send_id,
                m.SendAttempt.status.in_([_TO_DB[s] for s in from_statuses]),
            )
            .values(**values)
            .returning(m.SendAttempt.id)
        )
        if expected_generation is not None:
            stmt = stmt.where(m.SendAttempt.generation == expected_generation)
        if expected_attempts is not None:
            stmt = stmt.where(m.SendAttempt.attempts == expected_attempts)
        updated = (await session.execute(stmt)).scalar_one_or_none()
        if updated is None:
            if await session.get(m.SendAttempt, send_id) is None:
                raise NotFoundError("send not found")
            return None
        session.expire_all()
        return await PostgresActRepository._send_where(session, m.SendAttempt.id == send_id)
