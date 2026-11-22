import pytest

from app.clients.ratelimit import SlidingWindowRateLimiter

pytestmark = pytest.mark.anyio


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_allows_limit_per_window_then_waits_for_oldest() -> None:
    t = FakeTime()
    limiter = SlidingWindowRateLimiter({"enrich": 3}, clock=t.clock, sleep=t.sleep)
    for _ in range(3):
        assert await limiter.acquire("enrich") == 0
        t.now += 1
    # 4th request at t=3 must wait until the first (t=0) leaves the 60 s window.
    assert await limiter.acquire("enrich") == pytest.approx(57)
    assert t.now == pytest.approx(60)


async def test_keys_are_independent_and_unknown_keys_are_unlimited() -> None:
    t = FakeTime()
    limiter = SlidingWindowRateLimiter({"a": 1, "b": 1}, clock=t.clock, sleep=t.sleep)
    await limiter.acquire("a")
    await limiter.acquire("b")
    for _ in range(100):
        await limiter.acquire("other")
    assert t.sleeps == []
    await limiter.acquire("a")
    assert t.sleeps == [60]
