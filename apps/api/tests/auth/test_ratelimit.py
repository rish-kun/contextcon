"""The failed sign-in limiter and the Argon2 slots on their own (fake clock)."""

import asyncio

import pytest

from app.auth.ratelimit import LoginRateLimiter, VerificationSlots, VerifierBusy


def test_rate_limiter_window_and_email_cap() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(per_client=2, per_email=3, window_seconds=60, clock=lambda: now[0])
    limiter.record_failure("e", "ip1")
    assert limiter.retry_after("e", "ip1") is None
    limiter.record_failure("e", "ip1")
    assert limiter.retry_after("e", "ip1") == 60
    assert limiter.retry_after("e", "ip2") is None
    limiter.record_failure("e", "ip2")  # third failure for this email from anywhere
    assert limiter.retry_after("e", "ip3") == 60  # email cap reached
    assert limiter.retry_after("other", "ip1") is None
    now[0] = 30
    assert limiter.retry_after("e", "ip1") == 30
    now[0] = 61
    assert limiter.retry_after("e", "ip1") is None
    assert limiter.retry_after("e", "ip3") is None


def test_acquire_reserves_and_success_refunds() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(per_client=2, per_email=2, window_seconds=60, clock=lambda: now[0])
    wait, first = limiter.acquire("e", "ip1")
    assert wait is None and first is not None
    now[0] = 1
    wait, second = limiter.acquire("e", "ip1")
    assert wait is None and second is not None
    # Both reservations count until settled: a third attempt is refused.
    assert limiter.acquire("e", "ip1") == (59, None)
    limiter.succeeded("e", "ip1", second)
    # The success refunded its own reservation and cleared the client key; the first
    # attempt (a failure) still counts against the email.
    assert limiter.retry_after("e", "ip2") is None
    wait, third = limiter.acquire("e", "ip2")
    assert wait is None
    assert limiter.acquire("e", "ip3")[0] is not None  # email cap: first + third


def test_ip_limit_spans_emails() -> None:
    """Distinct made-up emails from one IP share the per-IP budget."""
    limiter = LoginRateLimiter(
        per_client=5, per_email=5, per_ip=3, window_seconds=60, clock=lambda: 0.0
    )
    for i in range(3):
        assert limiter.acquire(f"user{i}@x.example", "ip1")[0] is None
    assert limiter.acquire("user99@x.example", "ip1")[0] == 60
    assert limiter.acquire("user99@x.example", "ip2")[0] is None


def test_global_limit_spans_ips_and_emails() -> None:
    limiter = LoginRateLimiter(
        per_client=5, per_email=5, per_ip=5, global_limit=4, window_seconds=60, clock=lambda: 0.0
    )
    for i in range(4):
        assert limiter.acquire(f"u{i}", f"ip{i}")[0] is None
    assert limiter.acquire("fresh", "fresh-ip")[0] == 60


def test_refund_gives_back_every_key() -> None:
    limiter = LoginRateLimiter(
        per_client=1, per_email=1, per_ip=1, global_limit=1, window_seconds=60, clock=lambda: 0.0
    )
    _, reservation = limiter.acquire("e", "ip")
    assert reservation is not None
    assert limiter.acquire("other", "other-ip")[0] is not None  # global cap
    limiter.refund("e", "ip", reservation)
    assert len(limiter) == 0
    assert limiter.acquire("e", "ip")[0] is None


def test_success_refunds_ip_and_global_too() -> None:
    limiter = LoginRateLimiter(
        per_client=5, per_email=5, per_ip=1, global_limit=1, window_seconds=60, clock=lambda: 0.0
    )
    _, reservation = limiter.acquire("e", "ip")
    assert reservation is not None
    limiter.succeeded("e", "ip", reservation)
    assert limiter.acquire("other", "ip")[0] is None


def test_expired_keys_are_swept() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(
        per_client=5, per_email=5, per_ip=50, window_seconds=60, clock=lambda: now[0]
    )
    for i in range(20):
        limiter.record_failure(f"one-off-{i}", f"10.0.0.{i}")
    assert len(limiter) == 60  # client, email and ip key per attempt
    now[0] = 61
    limiter.acquire("late", "10.9.9.9")  # the first call after a window sweeps
    assert len(limiter) == 3


def test_key_count_is_bounded() -> None:
    limiter = LoginRateLimiter(
        per_client=5, per_email=5, window_seconds=60, max_keys=10, clock=lambda: 0.0
    )
    for i in range(100):
        limiter.acquire(f"spray-{i}", "ip")
    assert len(limiter) == 10
    # The most recent keys survive eviction.
    assert ("email", "spray-99") in limiter._failures


@pytest.mark.asyncio
async def test_verification_slots_cap_concurrency() -> None:
    slots = VerificationSlots(limit=2, wait_seconds=0.05)
    running = 0
    peak = 0
    release = asyncio.Event()

    async def check() -> None:
        nonlocal running, peak
        async with slots.slot():
            running += 1
            peak = max(peak, running)
            await release.wait()
            running -= 1

    holders = [asyncio.create_task(check()) for _ in range(2)]
    await asyncio.sleep(0)
    with pytest.raises(VerifierBusy):
        async with slots.slot():
            pass
    release.set()
    await asyncio.gather(*holders)
    assert peak == 2
    async with slots.slot():  # free again
        pass
