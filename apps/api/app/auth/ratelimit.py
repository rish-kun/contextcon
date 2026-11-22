"""Sign-in attempt limiter (in-process, sliding window).

Two keys are counted: (email, client IP) with a tight limit, and the email alone with a
looser one, so rotating or spoofed client IPs cannot guess a password faster than the
per-email cap. The trade-off: someone who knows an email can lock it out of password
sign-in for one window (existing sessions keep working).

`acquire` checks and reserves an attempt in one step under the lock, so a burst of
parallel guesses cannot all pass the check before the first failure is recorded. A
successful sign-in refunds its reservation and clears the (email, IP) key. Counts live in
one process; with several API instances each keeps its own, which still bounds guessing.
"""

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class LoginRateLimiter:
    def __init__(
        self,
        *,
        per_client: int,
        per_email: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_client = per_client
        self.per_email = per_email
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[tuple[str, ...], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _keys(self, email: str, ip: str) -> list[tuple[tuple[str, ...], int]]:
        return [(("client", email, ip), self.per_client), (("email", email), self.per_email)]

    def _prune(self, key: tuple[str, ...], now: float) -> deque[float]:
        hits = self._failures[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if not hits:
            del self._failures[key]
            return deque()
        return hits

    def _wait(self, email: str, ip: str, now: float) -> float:
        wait = 0.0
        for key, limit in self._keys(email, ip):
            hits = self._prune(key, now)
            if len(hits) >= limit:
                wait = max(wait, hits[len(hits) - limit] + self.window - now)
        return wait

    @staticmethod
    def _seconds(wait: float) -> int | None:
        return max(1, math.ceil(wait)) if wait > 0 else None

    def retry_after(self, email: str, ip: str) -> int | None:
        """Seconds until another attempt is allowed, or None if allowed now."""
        with self._lock:
            return self._seconds(self._wait(email, ip, self._clock()))

    def acquire(self, email: str, ip: str) -> tuple[int | None, float | None]:
        """Atomically check and reserve one attempt (counted as a failure until
        `succeeded` refunds it). Returns (retry_after, None) when limited, else
        (None, reservation)."""
        now = self._clock()
        with self._lock:
            wait = self._wait(email, ip, now)
            if wait > 0:
                return self._seconds(wait), None
            for key, _ in self._keys(email, ip):
                self._failures[key].append(now)
            return None, now

    def succeeded(self, email: str, ip: str, reservation: float) -> None:
        """Refund a successful attempt's reservation and clear the (email, IP) failures."""
        with self._lock:
            self._failures.pop(("client", email, ip), None)
            hits = self._failures.get(("email", email))
            if hits is not None:
                try:
                    hits.remove(reservation)
                except ValueError:
                    pass
                if not hits:
                    del self._failures[("email", email)]

    def record_failure(self, email: str, ip: str) -> None:
        now = self._clock()
        with self._lock:
            for key, _ in self._keys(email, ip):
                self._failures[key].append(now)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


_limiter: LoginRateLimiter | None = None


def login_limiter() -> LoginRateLimiter:
    """The process-wide limiter, configured from `AuthSettings`."""
    global _limiter
    if _limiter is None:
        from app.auth.config import get_auth_settings

        cfg = get_auth_settings()
        _limiter = LoginRateLimiter(
            per_client=cfg.login_max_failures_per_client,
            per_email=cfg.login_max_failures_per_email,
            window_seconds=cfg.login_window_seconds,
        )
    return _limiter
