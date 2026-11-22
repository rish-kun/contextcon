"""Failed sign-in limiter (in-process, sliding window).

Two keys are counted: (email, client IP) with a tight limit, and the email alone with a
looser one, so rotating IPs (or a spoofed `X-Forwarded-For`) cannot guess a password
faster than the per-email cap. A success clears the (email, IP) key. Counts live in one
process; with several API instances each keeps its own, which still bounds guessing.
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

    def retry_after(self, email: str, ip: str) -> int | None:
        """Seconds until another attempt is allowed, or None if allowed now."""
        now = self._clock()
        wait = 0.0
        with self._lock:
            for key, limit in self._keys(email, ip):
                hits = self._prune(key, now)
                if len(hits) >= limit:
                    wait = max(wait, hits[len(hits) - limit] + self.window - now)
        return max(1, math.ceil(wait)) if wait > 0 else None

    def record_failure(self, email: str, ip: str) -> None:
        now = self._clock()
        with self._lock:
            for key, _ in self._keys(email, ip):
                self._failures[key].append(now)

    def record_success(self, email: str, ip: str) -> None:
        with self._lock:
            self._failures.pop(("client", email, ip), None)

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
