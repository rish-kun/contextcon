import asyncio
import inspect
import uuid
from collections import Counter

import pytest

from app.act.models import (
    Actor,
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
)
from app.act.resend import SEND_KEY_TAG
from app.act.service import ActService, SendConfig
from tests.act.conftest import ActEnv
from tests.act.fakes import RECIPIENT, FakeClock, send_current


def run(coro):
    return asyncio.run(coro)


async def _draft(act: ActEnv, service: ActService, **overrides):
    fields = {"subject": "Documents request", "body": "Please share...", "recipient": RECIPIENT}
    fields.update(overrides)
    return await service.create_message(act.case, act.alice, **fields)


async def _approved(act: ActEnv, service: ActService):
    state = await _draft(act, service)
    return await service.approve(
        act.case, state.message.id, act.bob, revision_id=state.current_revision.id
    )


# --- revisions and approval -----------------------------------------------------------


def test_edit_after_approval_requires_reapproval(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()

    async def scenario():
        approved = await _approved(act, service)
        assert approved.status is MessageStatus.APPROVED
        message_id = approved.message.id
        rev1 = approved.current_revision

        edited = await service.revise(
            act.case,
            message_id,
            act.alice,
            subject="Documents request (v2)",
            body="Updated",
            recipient=RECIPIENT,
        )
        assert edited.status is MessageStatus.DRAFT
        assert edited.approval is None
        assert [r.number for r in edited.revisions] == [1, 2]
        assert edited.revisions[0] == rev1  # earlier revision untouched

        with pytest.raises(NotApprovedError):
            await send_current(service, act.case, message_id, act.bob)
        # The old approval cannot be reused for the new revision.
        with pytest.raises(StaleRevisionError):
            await service.approve(act.case, message_id, act.bob, revision_id=rev1.id)

        reapproved = await service.approve(
            act.case, message_id, act.bob, revision_id=edited.current_revision.id
        )
        assert reapproved.approval.revision_id == edited.current_revision.id
        send = await send_current(service, act.case, message_id, act.bob)
        assert send.status is SendStatus.SENT
        assert send.revision_id == edited.current_revision.id

    run(scenario())
    (email,) = fake.emails
    assert email.subject == "Documents request (v2)"
    assert email.text == "Updated"


def test_approval_records_named_user_and_timestamp(act: ActEnv) -> None:
    service, _, _, clock = act.make_service()
    state = run(_approved(act, service))
    assert state.approval.approver_user_id == act.bob.user_id
    assert state.approval.approver_display_name == "Bob Manager"
    assert state.approval.approved_at == clock.now
    assert state.approval.revision_id == state.current_revision.id

    anonymous = Actor(user_id="u-x", display_name="  ")
    draft = run(_draft(act, service))
    with pytest.raises(ValidationError):
        run(
            service.approve(
                act.case, draft.message.id, anonymous, revision_id=draft.current_revision.id
            )
        )


def test_revise_with_stale_base_revision_is_rejected(act: ActEnv) -> None:
    service, _, _, _ = act.make_service()

    async def scenario():
        state = await _draft(act, service)
        base = state.current_revision.id
        await service.revise(
            act.case, state.message.id, act.alice, subject="s2", body="b2", recipient=RECIPIENT
        )
        with pytest.raises(StaleRevisionError):
            await service.revise(
                act.case,
                state.message.id,
                act.alice,
                subject="s3",
                body="b3",
                recipient=RECIPIENT,
                base_revision_id=base,
            )

    run(scenario())


def test_recipient_must_be_a_typed_email_address(act: ActEnv) -> None:
    service, _, _, _ = act.make_service()
    for bad in ("", "not-an-email", "a@b.c, d@e.f", "Seller <s@x.io>"):
        with pytest.raises(ValidationError):
            run(_draft(act, service, recipient=bad))
    state = run(_draft(act, service, recipient="  Seller@Example.test "))
    assert state.current_revision.recipient == "Seller@Example.test"
    assert state.current_revision.entered_by_user_id == act.alice.user_id


def test_message_is_scoped_to_its_case(act: ActEnv) -> None:
    service, _, _, _ = act.make_service()
    state = run(_draft(act, service))
    with pytest.raises(NotFoundError):
        run(service.get_state(act.other_case, state.message.id))


# --- sending ----------------------------------------------------------------------------


def test_send_without_approval_is_rejected(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    state = run(_draft(act, service))
    with pytest.raises(NotApprovedError):
        run(send_current(service, act.case, state.message.id, act.bob))
    assert fake.send_requests == []
    assert run(service.get_state(act.case, state.message.id)).status is MessageStatus.DRAFT


def test_send_twice_sends_once(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()

    async def scenario():
        state = await _approved(act, service)
        first = await send_current(service, act.case, state.message.id, act.bob)
        with pytest.raises(SendExistsError) as second:
            await send_current(service, act.case, state.message.id, act.bob)
        return first, second.value.send

    first, existing = run(scenario())
    assert first.status is SendStatus.SENT
    assert first.provider_message_id == "em_1"
    assert existing.id == first.id
    assert len(fake.send_requests) == 1
    assert fake.delivered == 1
    request = fake.send_requests[0]
    assert request.headers["Idempotency-Key"] == first.send_key
    assert fake.emails[0].tags == {SEND_KEY_TAG: first.send_key}


def test_concurrent_sends_dispatch_once(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.send_delay = 0.05  # keep the first send in flight while the others arrive

    async def scenario():
        state = await _approved(act, service)
        return await asyncio.gather(
            *(send_current(service, act.case, state.message.id, act.bob) for _ in range(5)),
            return_exceptions=True,
        )

    results = run(scenario())
    sent = [r for r in results if not isinstance(r, Exception)]
    rejected = [r for r in results if isinstance(r, SendExistsError)]
    assert len(sent) == 1 and sent[0].status is SendStatus.SENT
    assert len(rejected) == 4
    assert len(fake.send_requests) == 1
    assert fake.delivered == 1


class YieldingRepository:
    """Wraps a repository and yields to the event loop before every call, like a real DB
    round trip, so concurrent sends all pass the read checks and race into
    `create_send`."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: Counter[str] = Counter()

    def __getattr__(self, name: str):
        attr = getattr(self._inner, name)
        if name.startswith("_") or not inspect.iscoroutinefunction(attr):
            return attr

        async def wrapper(*args, **kwargs):
            self.calls[name] += 1
            await asyncio.sleep(0)
            return await attr(*args, **kwargs)

        return wrapper


def test_concurrent_sends_racing_into_the_claim_dispatch_once(act: ActEnv) -> None:
    _, fake, _, clock = act.make_service()
    repo = YieldingRepository(act.new_repo())
    config = SendConfig(enabled=True, sender="x@example.test")
    service = ActService(repo, config, fake.client(), clock=clock)

    async def scenario():
        state = await _approved(act, service)
        return await asyncio.gather(
            *(send_current(service, act.case, state.message.id, act.bob) for _ in range(5)),
            return_exceptions=True,
        )

    results = run(scenario())
    assert repo.calls["create_send"] == 5  # every caller passed the checks and tried to claim
    assert sum(1 for r in results if not isinstance(r, Exception)) == 1
    assert all(isinstance(r, SendExistsError) for r in results if isinstance(r, Exception))
    assert len(fake.send_requests) == 1
    assert fake.delivered == 1


def test_no_send_and_no_edit_once_sent(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()

    async def scenario():
        state = await _approved(act, service)
        message_id = state.message.id
        await send_current(service, act.case, message_id, act.bob)
        with pytest.raises(SendExistsError):
            await service.revise(
                act.case, message_id, act.alice, subject="x", body="y", recipient=RECIPIENT
            )
        with pytest.raises(SendExistsError):
            await service.approve(
                act.case, message_id, act.bob, revision_id=state.current_revision.id
            )
        with pytest.raises(SendExistsError):
            await send_current(service, act.case, message_id, act.bob)
        return await service.get_state(act.case, message_id)

    final = run(scenario())
    assert final.status is MessageStatus.SENT
    assert len(final.revisions) == 1
    assert fake.delivered == 1


def test_lost_response_is_unknown_then_reconcile_finds_sent_without_resend(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.lose_response_after_accept = 1
    fake.add_unrelated_email(subject="Documents request")  # same subject, no tag: not ours

    async def scenario():
        state = await _approved(act, service)
        message_id = state.message.id
        first = await send_current(service, act.case, message_id, act.bob)
        assert first.status is SendStatus.UNKNOWN
        assert (await service.get_state(act.case, message_id)).status is MessageStatus.UNKNOWN
        # The user clicks send again: DealProof looks the message up instead of resending.
        resolved = await send_current(service, act.case, message_id, act.bob)
        return first, resolved

    first, resolved = run(scenario())
    assert resolved.status is SendStatus.SENT
    assert resolved.id == first.id
    assert resolved.provider_message_id == fake.emails[-1].id
    assert len(fake.send_requests) == 1  # never re-posted
    assert fake.delivered == 2  # the unrelated email plus ours, once
    assert fake.lookup_requests  # it did ask the provider


def test_reconcile_endpoint_resolves_unknown_without_dispatch(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.lose_response_after_accept = 1

    async def scenario():
        state = await _approved(act, service)
        await send_current(service, act.case, state.message.id, act.bob)
        return await service.reconcile(act.case, state.message.id)

    resolved = run(scenario())
    assert resolved.status is SendStatus.SENT
    assert len(fake.send_requests) == 1


def test_unknown_and_absent_at_provider_retries_with_same_key(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.reject_next_with = 500  # server error before anything was queued

    async def scenario():
        state = await _approved(act, service)
        first = await send_current(service, act.case, state.message.id, act.bob)
        assert first.status is SendStatus.UNKNOWN
        reconciled = await service.reconcile(act.case, state.message.id)
        assert reconciled.status is SendStatus.UNKNOWN  # reconcile alone never dispatches
        assert len(fake.send_requests) == 1
        retried = await send_current(service, act.case, state.message.id, act.bob)
        return first, retried

    first, retried = run(scenario())
    assert retried.status is SendStatus.SENT
    assert retried.attempts == 2
    keys = {r.headers["Idempotency-Key"] for r in fake.send_requests}
    assert keys == {first.send_key}
    assert fake.delivered == 1


def test_unknown_stays_unknown_when_lookup_fails(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.lose_response_after_accept = 1

    async def scenario():
        state = await _approved(act, service)
        await send_current(service, act.case, state.message.id, act.bob)
        fake.fail_lookups = True
        return await send_current(service, act.case, state.message.id, act.bob)

    result = run(scenario())
    assert result.status is SendStatus.UNKNOWN
    assert "provider lookup failed" in result.error
    assert len(fake.send_requests) == 1


def test_stale_sending_becomes_unknown_and_reconciles(act: ActEnv) -> None:
    service, fake, repo, clock = act.make_service()

    async def scenario():
        state = await _approved(act, service)
        # Simulate a process that claimed the send, reached Resend, then died.
        fake.lose_response_after_accept = 1
        send = await send_current(service, act.case, state.message.id, act.bob)
        await repo.transition_send(send.id, [SendStatus.UNKNOWN], status=SendStatus.SENDING)
        with pytest.raises(SendExistsError):  # still fresh: treated as in progress
            await send_current(service, act.case, state.message.id, act.bob)
        clock.advance(minutes=5)
        return await send_current(service, act.case, state.message.id, act.bob)

    result = run(scenario())
    assert result.status is SendStatus.SENT
    assert len(fake.send_requests) == 1


def test_rejected_send_is_failed_and_can_be_retried_once(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.reject_next_with = 422

    async def scenario():
        state = await _approved(act, service)
        failed = await send_current(service, act.case, state.message.id, act.bob)
        assert failed.status is SendStatus.FAILED
        assert "422" in failed.error
        retried = await send_current(service, act.case, state.message.id, act.bob)
        with pytest.raises(SendExistsError):
            await send_current(service, act.case, state.message.id, act.bob)
        return failed, retried

    failed, retried = run(scenario())
    assert retried.status is SendStatus.SENT and retried.send_key == failed.send_key
    assert fake.delivered == 1


def test_test_mode_suppresses_and_counts_separately(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service(enabled=False)

    async def scenario():
        state = await _approved(act, service)
        send = await send_current(service, act.case, state.message.id, act.bob)
        with pytest.raises(SendExistsError):
            await send_current(service, act.case, state.message.id, act.bob)
        return state, send, await service.send_summary(act.case)

    state, send, summary = run(scenario())
    assert send.status is SendStatus.SUPPRESSED_TEST_MODE
    assert send.test_mode is True
    assert send.provider_message_id is None
    assert fake.send_requests == [] and fake.lookup_requests == []
    assert summary[SendStatus.SUPPRESSED_TEST_MODE] == 1
    assert summary[SendStatus.SENT] == 0
    final = run(service.get_state(act.case, state.message.id))
    assert final.status is MessageStatus.SUPPRESSED_TEST_MODE


def test_suppressed_message_can_be_sent_for_real_once_enabled(act: ActEnv) -> None:
    # Two configurations sharing one store: the flag flipped between sends.
    test_mode, fake, repo, clock = act.make_service(enabled=False)
    live = ActService(
        repo, SendConfig(enabled=True, sender="x@example.test"), fake.client(), clock=clock
    )

    async def scenario():
        state = await _approved(act, test_mode)
        await send_current(test_mode, act.case, state.message.id, act.bob)
        sent = await send_current(live, act.case, state.message.id, act.bob)
        with pytest.raises(SendExistsError):
            await send_current(live, act.case, state.message.id, act.bob)
        return sent, await live.send_summary(act.case)

    sent, summary = run(scenario())
    assert sent.status is SendStatus.SENT and sent.test_mode is False
    assert fake.delivered == 1
    assert summary[SendStatus.SENT] == 1


def test_enabled_without_sender_or_key_refuses_before_claiming(act: ActEnv) -> None:
    service = ActService(act.new_repo(), SendConfig(enabled=True, sender=""), None)

    async def scenario():
        state = await _approved(act, service)
        with pytest.raises(EmailNotConfiguredError):
            await send_current(service, act.case, state.message.id, act.bob)
        return await service.get_state(act.case, state.message.id)

    assert run(scenario()).status is MessageStatus.APPROVED


# --- review regressions: approval binding, generations, payloads, windows -------------


class EditDuringRetry:
    """Hands back the existing send, then lets a concurrent edit land before the retry
    is claimed (the edit a stale caller would not see)."""

    def __init__(self, inner, edit) -> None:
        self._inner = inner
        self._edit = edit
        self.armed = False

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    async def get_send_for_revision(self, revision_id: str):
        found = await self._inner.get_send_for_revision(revision_id)
        if self.armed and found is not None:
            self.armed = False
            await self._edit()
        return found


def test_create_send_refuses_an_approval_of_another_revision(act: ActEnv) -> None:
    from dataclasses import replace

    service, fake, repo, clock = act.make_service()

    async def scenario():
        approved = await _approved(act, service)
        message_id = approved.message.id
        edited = await service.revise(
            act.case, message_id, act.alice, subject="v2", body="b2", recipient=RECIPIENT
        )
        latest = await repo.get_latest_send(message_id)
        assert latest is None
        # Forge a claim that pairs the new revision with the old revision's approval.
        record = SendRecord(
            id=str(uuid.uuid4()),
            message_id=message_id,
            case_id=act.case,
            revision_id=edited.current_revision.id,
            approval_id=approved.approval.id,
            send_key="dp-send-forged",
            status=SendStatus.SENDING,
            test_mode=False,
            attempts=1,
            created_at=clock.now,
        )
        with pytest.raises(NotApprovedError):
            await repo.create_send(record)
        with pytest.raises(StaleRevisionError):
            await repo.create_send(replace(record, revision_id=approved.current_revision.id))

    run(scenario())
    assert fake.send_requests == []


def test_retry_after_a_concurrent_edit_never_sends_the_superseded_body(act: ActEnv) -> None:
    clock = FakeClock()
    holder: dict = {}

    async def edit():
        await holder["service"].revise(
            act.case, holder["id"], act.alice, subject="v2", body="new body", recipient=RECIPIENT
        )

    repo = EditDuringRetry(act.new_repo(), edit)
    service, fake, _, _ = act.make_service(repo=repo, clock=clock)
    holder["service"] = service
    fake.reject_next_with = 422

    async def scenario():
        state = await _approved(act, service)
        holder["id"] = state.message.id
        failed = await send_current(service, act.case, state.message.id, act.bob)
        assert failed.status is SendStatus.FAILED
        repo.armed = True
        with pytest.raises(StaleRevisionError):
            await send_current(service, act.case, state.message.id, act.bob)
        return await service.get_state(act.case, state.message.id)

    final = run(scenario())
    assert len(fake.send_requests) == 1  # only the first, rejected attempt
    assert fake.delivered == 0
    assert final.status is MessageStatus.DRAFT
    assert final.send.status is SendStatus.FAILED


def test_stale_snapshot_cannot_expire_or_finish_a_newer_attempt(act: ActEnv) -> None:
    service, fake, repo, clock = act.make_service()
    fake.reject_next_with = 422

    async def scenario():
        state = await _approved(act, service)
        old = await send_current(service, act.case, state.message.id, act.bob)  # failed, attempt 1
        retried = await send_current(
            service, act.case, state.message.id, act.bob
        )  # sent, attempt 2
        assert retried.status is SendStatus.SENT and retried.generation > old.generation
        # A caller still holding the attempt-1 snapshot loses every compare-and-set.
        assert (
            await repo.transition_send(
                old.id,
                [SendStatus.FAILED, SendStatus.SENT],
                expected_generation=old.generation,
                status=SendStatus.UNKNOWN,
            )
            is None
        )
        assert (
            await repo.transition_send(
                old.id,
                [SendStatus.SENT],
                expected_attempts=old.attempts,
                status=SendStatus.FAILED,
            )
            is None
        )
        return await repo.get_latest_send(state.message.id)

    final = run(scenario())
    assert final.status is SendStatus.SENT


def test_retry_resends_the_persisted_payload_exactly(act: ActEnv) -> None:
    first, fake, repo, clock = act.make_service(sender="Old <old@example.test>")
    fake.reject_next_with = 422
    # Same store, but the configured sender changed between attempts.
    second, _, _, _ = act.make_service(
        repo=repo, fake=fake, clock=clock, sender="New <new@example.test>"
    )

    async def scenario():
        state = await _approved(act, first)
        failed = await send_current(first, act.case, state.message.id, act.bob)
        assert failed.payload["from"] == "Old <old@example.test>"
        return await send_current(second, act.case, state.message.id, act.bob)

    sent = run(scenario())
    assert sent.status is SendStatus.SENT
    a, b = fake.send_requests
    assert a.content == b.content
    assert a.headers["Idempotency-Key"] == b.headers["Idempotency-Key"]


def test_idempotency_payload_mismatch_is_unknown_not_failed(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()
    fake.reject_next_with = 409

    async def scenario():
        state = await _approved(act, service)
        return await send_current(service, act.case, state.message.id, act.bob)

    result = run(scenario())
    assert result.status is SendStatus.UNKNOWN
    assert "409" in result.error


def test_unknown_is_not_retried_after_the_idempotency_window(act: ActEnv) -> None:
    service, fake, _, clock = act.make_service()
    fake.reject_next_with = 500  # nothing queued; a lookup would find nothing

    async def scenario():
        state = await _approved(act, service)
        first = await send_current(service, act.case, state.message.id, act.bob)
        assert first.status is SendStatus.UNKNOWN
        clock.advance(hours=24)
        late = await send_current(service, act.case, state.message.id, act.bob)
        assert late.status is SendStatus.UNKNOWN
        assert "confirm the outcome manually" in late.error
        assert len(fake.send_requests) == 1
        settled = await service.confirm_outcome(
            act.case, state.message.id, act.bob, delivered=False, note="not in Resend logs"
        )
        assert settled.status is SendStatus.FAILED
        assert "Bob Manager" in settled.error
        return await send_current(service, act.case, state.message.id, act.bob)

    retried = run(scenario())
    assert retried.status is SendStatus.SENT
    assert len(fake.send_requests) == 2
    assert fake.delivered == 1


def test_unknown_stays_unknown_when_sending_is_disabled(act: ActEnv) -> None:
    live, fake, repo, clock = act.make_service()
    fake.reject_next_with = 500
    test_mode, _, _, _ = act.make_service(enabled=False, repo=repo, fake=fake, clock=clock)

    async def scenario():
        state = await _approved(act, live)
        first = await send_current(live, act.case, state.message.id, act.bob)
        assert first.status is SendStatus.UNKNOWN
        again = await send_current(test_mode, act.case, state.message.id, act.bob)
        return again, await test_mode.get_state(act.case, state.message.id)

    again, state = run(scenario())
    assert again.status is SendStatus.UNKNOWN
    assert "sending is disabled" in again.error
    assert state.status is MessageStatus.UNKNOWN
    assert len(fake.send_requests) == 1


def test_confirm_outcome_needs_an_unknown_send_and_a_named_user(act: ActEnv) -> None:
    service, fake, _, _ = act.make_service()

    async def scenario():
        state = await _approved(act, service)
        sent = await send_current(service, act.case, state.message.id, act.bob)
        assert sent.status is SendStatus.SENT
        with pytest.raises(SendExistsError):
            await service.confirm_outcome(act.case, state.message.id, act.bob, delivered=False)
        nameless = Actor(user_id=act.bob.user_id, display_name=" ")
        with pytest.raises(ValidationError):
            await service.confirm_outcome(act.case, state.message.id, nameless, delivered=True)

    run(scenario())


def test_approval_needs_a_typed_recipient(act: ActEnv) -> None:
    service, _, repo, clock = act.make_service()
    message_id = str(uuid.uuid4())
    revision = MessageRevision(
        id=str(uuid.uuid4()),
        message_id=message_id,
        number=1,
        subject="Documents for our review",
        body="Drafted body",
        recipient="",  # a drafted revision: no recipient yet
        entered_by_user_id="",
        created_at=clock.now,
    )
    message = Message(
        id=message_id, case_id=act.case, current_revision_id=revision.id, created_at=clock.now
    )

    async def scenario():
        await repo.create_message(message, revision)
        with pytest.raises(ValidationError):
            await service.approve(act.case, message_id, act.bob, revision_id=revision.id)
        edited = await service.revise(
            act.case,
            message_id,
            act.alice,
            subject=revision.subject,
            body=revision.body,
            recipient=RECIPIENT,
        )
        return await service.approve(
            act.case, message_id, act.bob, revision_id=edited.current_revision.id
        )

    approved = run(scenario())
    assert approved.status is MessageStatus.APPROVED
    assert [r.number for r in approved.revisions] == [1, 2]
