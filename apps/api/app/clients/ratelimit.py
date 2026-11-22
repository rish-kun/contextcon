"""Client-side request pacing: at most N requests per key in any trailing window.

A sliding log per key (e.g. one per Crustdata endpoint). Bursts up to the limit
are allowed; once a key has used its quota for the trailing window, `acquire`
waits until the oldest request leaves the window.

No lock is needed: the check and the append happen with no `await` between them,
so on one event loop they cannot interleave. That also means one instance can be
shared process-wide without binding to a particular event loop.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limits: Mapping[str, int],
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.limits = dict(limits)
        self.window = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._logs: dict[str, deque[float]] = {}

    async def acquire(self, key: str) -> float:
        """Wait for a slot under `key`. Returns the seconds spent waiting."""
        limit = self.limits.get(key)
        if not limit:
            return 0.0
        log = self._logs.setdefault(key, deque())
        waited = 0.0
        while True:
            now = self._clock()
            while log and log[0] <= now - self.window:
                log.popleft()
            if len(log) < limit:
                log.append(now)
                return waited
            delay = log[0] + self.window - now
            waited += delay
            await self._sleep(delay)
