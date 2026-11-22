"""The failed sign-in limiter on its own (fake clock)."""

from app.auth.ratelimit import LoginRateLimiter


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
