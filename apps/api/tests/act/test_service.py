import asyncio
import inspect
from collections import Counter

import pytest

from app.act.models import (
    Actor,
    EmailNotConfiguredError,
    MessageStatus,
    NotApprovedError,
    NotFoundError,
    SendExistsError,
    SendStatus,
    StaleRevisionError,
    ValidationError,
)
from app.act.repository import InMemoryActRepository
from app.act.resend import SEND_KEY_TAG
from app.act.service import ActService, SendConfig
from tests.act.fakes import ALICE, BOB, RECIPIENT, make_service

CASE = "case-1"


def run(coro):
    return asyncio.run(coro)


async def _draft(service: ActService, **overrides):
    fields = {"subject": "Documents request", "body": "Please share...", "recipient": RECIPIENT}
    fields.update(overrides)
    return await service.create_message(CASE, ALICE, **fields)


async def _approved(service: ActService):
    state = await _draft(service)
    return await service.approve(CASE, state.message.id, BOB, revision_id=state.current_revision.id)


# --- revisions and approval -----------------------------------------------------------


def test_edit_after_approval_requires_reapproval() -> None:
    service, fake, _, _ = make_service()

    async def scenario():
        approved = await _approved(service)
        assert approved.status is MessageStatus.APPROVED
        message_id = approved.message.id
        rev1 = approved.current_revision

        edited = await service.revise(
            CASE,
            message_id,
            ALICE,
            subject="Documents request (v2)",
            body="Updated",
            recipient=RECIPIENT,
        )
        assert edited.status is MessageStatus.DRAFT
        assert edited.approval is None
        assert [r.number for r in edited.revisions] == [1, 2]
        assert edited.revisions[0] == rev1  # earlier revision untouched

        with pytest.raises(NotApprovedError):
            await service.send(CASE, message_id, BOB)
        # The old approval cannot be reused for the new revision.
        with pytest.raises(StaleRevisionError):
            await service.approve(CASE, message_id, BOB, revision_id=rev1.id)

        reapproved = await service.approve(
            CASE, message_id, BOB, revision_id=edited.current_revision.id
        )
        assert reapproved.approval.revision_id == edited.current_revision.id
        send = await service.send(CASE, message_id, BOB)
        assert send.status is SendStatus.SENT
        assert send.revision_id == edited.current_revision.id

    run(scenario())
    (email,) = fake.emails
    assert email.subject == "Documents request (v2)"
    assert email.text == "Updated"


def test_approval_records_named_user_and_timestamp() -> None:
    service, _, _, clock = make_service()
    state = run(_approved(service))
    assert state.approval.approver_user_id == "u-bob"
    assert state.approval.approver_display_name == "Bob Manager"
    assert state.approval.approved_at == clock.now
    assert state.approval.revision_id == state.current_revision.id

    anonymous = Actor(user_id="u-x", display_name="  ")
    draft = run(_draft(service))
    with pytest.raises(ValidationError):
        run(
            service.approve(
                CASE, draft.message.id, anonymous, revision_id=draft.current_revision.id
            )
        )


def test_revise_with_stale_base_revision_is_rejected() -> None:
    service, _, _, _ = make_service()

    async def scenario():
        state = await _draft(service)
        base = state.current_revision.id
        await service.revise(
            CASE, state.message.id, ALICE, subject="s2", body="b2", recipient=RECIPIENT
        )
        with pytest.raises(StaleRevisionError):
            await service.revise(
                CASE,
                state.message.id,
                ALICE,
                subject="s3",
                body="b3",
                recipient=RECIPIENT,
                base_revision_id=base,
            )

    run(scenario())


def test_recipient_must_be_a_typed_email_address() -> None:
    service, _, _, _ = make_service()
    for bad in ("", "not-an-email", "a@b.c, d@e.f", "Seller <s@x.io>"):
        with pytest.raises(ValidationError):
            run(_draft(service, recipient=bad))
    state = run(_draft(service, recipient="  Seller@Example.test "))
    assert state.current_revision.recipient == "Seller@Example.test"
    assert state.current_revision.entered_by_user_id == ALICE.user_id


def test_message_is_scoped_to_its_case() -> None:
    service, _, _, _ = make_service()
    state = run(_draft(service))
    with pytest.raises(NotFoundError):
        run(service.get_state("other-case", state.message.id))


# --- sending ----------------------------------------------------------------------------


def test_send_without_approval_is_rejected() -> None:
    service, fake, _, _ = make_service()
    state = run(_draft(service))
    with pytest.raises(NotApprovedError):
        run(service.send(CASE, state.message.id, BOB))
    assert fake.send_requests == []
    assert run(service.get_state(CASE, state.message.id)).status is MessageStatus.DRAFT


def test_send_twice_sends_once() -> None:
    service, fake, _, _ = make_service()

    async def scenario():
        state = await _approved(service)
        first = await service.send(CASE, state.message.id, BOB)
        with pytest.raises(SendExistsError) as second:
            await service.send(CASE, state.message.id, BOB)
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


def test_concurrent_sends_dispatch_once() -> None:
    service, fake, _, _ = make_service()
    fake.send_delay = 0.05  # keep the first send in flight while the others arrive

    async def scenario():
        state = await _approved(service)
        return await asyncio.gather(
            *(service.send(CASE, state.message.id, BOB) for _ in range(5)),
            return_exceptions=True,
        )

    results = run(scenario())
    sent = [r for r in results if not isinstance(r, Exception)]
    rejected = [r for r in results if isinstance(r, SendExistsError)]
    assert len(sent) == 1 and sent[0].status is SendStatus.SENT
    assert len(rejected) == 4
    assert len(fake.send_requests) == 1
    assert fake.delivered == 1


class YieldingRepository(InMemoryActRepository):
    """Yields to the event loop before every call, like a real DB round trip, so
    concurrent sends all pass the read checks and race into `create_send`."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: Counter[str] = Counter()

    def __getattribute__(self, name: str):
        attr = super().__getattribute__(name)
        if name.startswith("_") or not inspect.iscoroutinefunction(attr):
            return attr

        async def wrapper(*args, **kwargs):
            self.calls[name] += 1
            await asyncio.sleep(0)
            return await attr(*args, **kwargs)

        return wrapper


def test_concurrent_sends_racing_into_the_claim_dispatch_once() -> None:
    _, fake, _, clock = make_service()
    repo = YieldingRepository()
    config = SendConfig(enabled=True, sender="x@example.test")
    service = ActService(repo, config, fake.client(), clock=clock)

    async def scenario():
        state = await _approved(service)
        return await asyncio.gather(
            *(service.send(CASE, state.message.id, BOB) for _ in range(5)),
            return_exceptions=True,
        )

    results = run(scenario())
    assert repo.calls["create_send"] == 5  # every caller passed the checks and tried to claim
    assert sum(1 for r in results if not isinstance(r, Exception)) == 1
    assert all(isinstance(r, SendExistsError) for r in results if isinstance(r, Exception))
    assert len(fake.send_requests) == 1
    assert fake.delivered == 1


def test_no_send_and_no_edit_once_sent() -> None:
    service, fake, _, _ = make_service()

    async def scenario():
        state = await _approved(service)
        message_id = state.message.id
        await service.send(CASE, message_id, BOB)
        with pytest.raises(SendExistsError):
            await service.revise(
                CASE, message_id, ALICE, subject="x", body="y", recipient=RECIPIENT
            )
        with pytest.raises(SendExistsError):
            await service.approve(CASE, message_id, BOB, revision_id=state.current_revision.id)
        with pytest.raises(SendExistsError):
            await service.send(CASE, message_id, BOB)
        return await service.get_state(CASE, message_id)

    final = run(scenario())
    assert final.status is MessageStatus.SENT
    assert len(final.revisions) == 1
    assert fake.delivered == 1


def test_lost_response_is_unknown_then_reconcile_finds_sent_without_resend() -> None:
    service, fake, _, _ = make_service()
    fake.lose_response_after_accept = 1
    fake.add_unrelated_email(subject="Documents request")  # same subject, no tag: not ours

    async def scenario():
        state = await _approved(service)
        message_id = state.message.id
        first = await service.send(CASE, message_id, BOB)
        assert first.status is SendStatus.UNKNOWN
        assert (await service.get_state(CASE, message_id)).status is MessageStatus.UNKNOWN
        # The user clicks send again: DealProof looks the message up instead of resending.
        resolved = await service.send(CASE, message_id, BOB)
        return first, resolved

    first, resolved = run(scenario())
    assert resolved.status is SendStatus.SENT
    assert resolved.id == first.id
    assert resolved.provider_message_id == fake.emails[-1].id
    assert len(fake.send_requests) == 1  # never re-posted
    assert fake.delivered == 2  # the unrelated email plus ours, once
    assert fake.lookup_requests  # it did ask the provider


def test_reconcile_endpoint_resolves_unknown_without_dispatch() -> None:
    service, fake, _, _ = make_service()
    fake.lose_response_after_accept = 1

    async def scenario():
        state = await _approved(service)
        await service.send(CASE, state.message.id, BOB)
        return await service.reconcile(CASE, state.message.id)

    resolved = run(scenario())
    assert resolved.status is SendStatus.SENT
    assert len(fake.send_requests) == 1


def test_unknown_and_absent_at_provider_retries_with_same_key() -> None:
    service, fake, _, _ = make_service()
    fake.reject_next_with = 500  # server error before anything was queued

    async def scenario():
        state = await _approved(service)
        first = await service.send(CASE, state.message.id, BOB)
        assert first.status is SendStatus.UNKNOWN
        reconciled = await service.reconcile(CASE, state.message.id)
        assert reconciled.status is SendStatus.UNKNOWN  # reconcile alone never dispatches
        assert len(fake.send_requests) == 1
        retried = await service.send(CASE, state.message.id, BOB)
        return first, retried

    first, retried = run(scenario())
    assert retried.status is SendStatus.SENT
    assert retried.attempts == 2
    keys = {r.headers["Idempotency-Key"] for r in fake.send_requests}
    assert keys == {first.send_key}
    assert fake.delivered == 1


def test_unknown_stays_unknown_when_lookup_fails() -> None:
    service, fake, _, _ = make_service()
    fake.lose_response_after_accept = 1

    async def scenario():
        state = await _approved(service)
        await service.send(CASE, state.message.id, BOB)
        fake.fail_lookups = True
        return await service.send(CASE, state.message.id, BOB)

    result = run(scenario())
    assert result.status is SendStatus.UNKNOWN
    assert "provider lookup failed" in result.error
    assert len(fake.send_requests) == 1


def test_stale_sending_becomes_unknown_and_reconciles() -> None:
    service, fake, repo, clock = make_service()

    async def scenario():
        state = await _approved(service)
        # Simulate a process that claimed the send, reached Resend, then died.
        fake.lose_response_after_accept = 1
        send = await service.send(CASE, state.message.id, BOB)
        await repo.transition_send(send.id, [SendStatus.UNKNOWN], status=SendStatus.SENDING)
        with pytest.raises(SendExistsError):  # still fresh: treated as in progress
            await service.send(CASE, state.message.id, BOB)
        clock.advance(minutes=5)
        return await service.send(CASE, state.message.id, BOB)

    result = run(scenario())
    assert result.status is SendStatus.SENT
    assert len(fake.send_requests) == 1


def test_rejected_send_is_failed_and_can_be_retried_once() -> None:
    service, fake, _, _ = make_service()
    fake.reject_next_with = 422

    async def scenario():
        state = await _approved(service)
        failed = await service.send(CASE, state.message.id, BOB)
        assert failed.status is SendStatus.FAILED
        assert "422" in failed.error
        retried = await service.send(CASE, state.message.id, BOB)
        with pytest.raises(SendExistsError):
            await service.send(CASE, state.message.id, BOB)
        return failed, retried

    failed, retried = run(scenario())
    assert retried.status is SendStatus.SENT and retried.send_key == failed.send_key
    assert fake.delivered == 1


def test_test_mode_suppresses_and_counts_separately() -> None:
    service, fake, _, _ = make_service(enabled=False)

    async def scenario():
        state = await _approved(service)
        send = await service.send(CASE, state.message.id, BOB)
        with pytest.raises(SendExistsError):
            await service.send(CASE, state.message.id, BOB)
        return state, send, await service.send_summary(CASE)

    state, send, summary = run(scenario())
    assert send.status is SendStatus.SUPPRESSED_TEST_MODE
    assert send.test_mode is True
    assert send.provider_message_id is None
    assert fake.send_requests == [] and fake.lookup_requests == []
    assert summary[SendStatus.SUPPRESSED_TEST_MODE] == 1
    assert summary[SendStatus.SENT] == 0
    final = run(service.get_state(CASE, state.message.id))
    assert final.status is MessageStatus.SUPPRESSED_TEST_MODE


def test_suppressed_message_can_be_sent_for_real_once_enabled() -> None:
    # Two configurations sharing one store: the flag flipped between sends.
    test_mode, fake, repo, clock = make_service(enabled=False)
    live = ActService(
        repo, SendConfig(enabled=True, sender="x@example.test"), fake.client(), clock=clock
    )

    async def scenario():
        state = await _approved(test_mode)
        await test_mode.send(CASE, state.message.id, BOB)
        sent = await live.send(CASE, state.message.id, BOB)
        with pytest.raises(SendExistsError):
            await live.send(CASE, state.message.id, BOB)
        return sent, await live.send_summary(CASE)

    sent, summary = run(scenario())
    assert sent.status is SendStatus.SENT and sent.test_mode is False
    assert fake.delivered == 1
    assert summary[SendStatus.SENT] == 1


def test_enabled_without_sender_or_key_refuses_before_claiming() -> None:
    service = ActService(InMemoryActRepository(), SendConfig(enabled=True, sender=""), None)

    async def scenario():
        state = await _approved(service)
        with pytest.raises(EmailNotConfiguredError):
            await service.send(CASE, state.message.id, BOB)
        return await service.get_state(CASE, state.message.id)

    assert run(scenario()).status is MessageStatus.APPROVED
