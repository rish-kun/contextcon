"""Sign-in attempt limiter (in-process, sliding window) and the Argon2 concurrency cap.

Four keys are counted per attempt, each with its own limit:

- (email, client IP): tight. Stops one client guessing one account.
- email: looser. Rotating or spoofed client IPs cannot guess one password faster than
  this. Someone who knows an email can lock it out of password sign-in for one window
  (existing sessions keep working).
- client IP: across every email. A stream of distinct, made-up emails from one client
  would otherwise get a fresh budget (and an Argon2 check) on every request.
- global: across every client. Bounds the total Argon2 work an attacker with many IPs
  can force. When it trips, password sign-in pauses for everyone until the window
  slides (existing sessions keep working); the default is set well above real traffic.

`acquire` checks and reserves an attempt in one step under the lock, so a burst of
parallel guesses cannot all pass the check before the first failure is recorded. A
successful sign-in refunds its reservation everywhere and clears the (email, IP) key.

Memory is bounded: emptied keys are dropped, a full sweep of expired keys runs at most
once per window, and at most `max_keys` keys are kept (least recently hit evicted first).

Counts live in one process. With several API instances each keeps its own, so the
effective limits are multiplied by the instance count. That is accepted for the demo
(a handful of instances at most); a shared store (Postgres or Redis) would fix it.
"""

import asyncio
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

Key = tuple[str, ...]


class LoginRateLimiter:
    def __init__(
        self,
        *,
        per_client: int,
        per_email: int,
        window_seconds: float,
        per_ip: int | None = None,
        global_limit: int | None = None,
        max_keys: int = 100_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_client = per_client
        self.per_email = per_email
        self.per_ip = per_ip
        self.global_limit = global_limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        # Least recently hit first, so eviction drops the stalest key.
        self._failures: OrderedDict[Key, deque[float]] = OrderedDict()
        self._last_sweep = clock()
        self._lock = threading.Lock()

    def _keys(self, email: str, ip: str) -> list[tuple[Key, int]]:
        keys: list[tuple[Key, int]] = [
            (("client", email, ip), self.per_client),
            (("email", email), self.per_email),
        ]
        if self.per_ip is not None:
            keys.append((("ip", ip), self.per_ip))
        if self.global_limit is not None:
            keys.append((("global",), self.global_limit))
        return keys

    def _prune(self, key: Key, now: float) -> deque[float]:
        hits = self._failures.get(key)
        if hits is None:
            return deque()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if not hits:
            del self._failures[key]
        return hits

    def _sweep(self, now: float) -> None:
        """Drop every expired key, at most once per window."""
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        for key in list(self._failures):
            self._prune(key, now)

    def _hit(self, key: Key, now: float) -> None:
        hits = self._failures.get(key)
        if hits is None:
            hits = self._failures[key] = deque()
        else:
            self._failures.move_to_end(key)
        hits.append(now)
        while len(self._failures) > self.max_keys:
            self._failures.popitem(last=False)

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

    def __len__(self) -> int:
        """Keys currently held (for tests and monitoring)."""
        with self._lock:
            return len(self._failures)

    def retry_after(self, email: str, ip: str) -> int | None:
        """Seconds until another attempt is allowed, or None if allowed now."""
        with self._lock:
            return self._seconds(self._wait(email, ip, self._clock()))

    def acquire(self, email: str, ip: str) -> tuple[int | None, float | None]:
        """Atomically check and reserve one attempt (counted as a failure until
        `succeeded` or `refund` gives it back). Returns (retry_after, None) when
        limited, else (None, reservation)."""
        now = self._clock()
        with self._lock:
            self._sweep(now)
            wait = self._wait(email, ip, now)
            if wait > 0:
                return self._seconds(wait), None
            for key, _ in self._keys(email, ip):
                self._hit(key, now)
            return None, now

    def _refund(self, email: str, ip: str, reservation: float) -> None:
        for key, _ in self._keys(email, ip):
            hits = self._failures.get(key)
            if hits is None:
                continue
            try:
                hits.remove(reservation)
            except ValueError:
                pass
            if not hits:
                del self._failures[key]

    def refund(self, email: str, ip: str, reservation: float) -> None:
        """Give back a reservation for an attempt that never checked a password."""
        with self._lock:
            self._refund(email, ip, reservation)

    def succeeded(self, email: str, ip: str, reservation: float) -> None:
        """Refund a successful attempt's reservation and clear the (email, IP) failures."""
        with self._lock:
            self._refund(email, ip, reservation)
            self._failures.pop(("client", email, ip), None)

    def record_failure(self, email: str, ip: str) -> None:
        now = self._clock()
        with self._lock:
            for key, _ in self._keys(email, ip):
                self._hit(key, now)

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
            per_ip=cfg.login_max_failures_per_ip,
            global_limit=cfg.login_max_failures_global,
            window_seconds=cfg.login_window_seconds,
            max_keys=cfg.login_max_tracked_keys,
        )
    return _limiter


def reset_login_limiter() -> None:
    """Forget the limiter so the next `login_limiter()` re-reads settings (tests)."""
    global _limiter
    _limiter = None


# --- Argon2 concurrency cap -------------------------------------------------------


class VerifierBusy(Exception):
    """No password-check slot freed up in time."""


class VerificationSlots:
    """Caps concurrent Argon2 verifications (each takes ~50 MB and a CPU core for tens of
    milliseconds). A caller waits up to `wait_seconds` for a slot, then gets
    `VerifierBusy` instead of queueing without bound. One semaphore per event loop."""

    def __init__(self, limit: int, wait_seconds: float) -> None:
        self.limit = limit
        self.wait_seconds = wait_seconds
        self._sems: dict[int, asyncio.Semaphore] = {}

    def _sem(self) -> asyncio.Semaphore:
        loop_id = id(asyncio.get_running_loop())
        sem = self._sems.get(loop_id)
        if sem is None:
            self._sems = {loop_id: (sem := asyncio.Semaphore(self.limit))}
        return sem

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        sem = self._sem()
        try:
            await asyncio.wait_for(sem.acquire(), self.wait_seconds)
        except TimeoutError:
            raise VerifierBusy from None
        try:
            yield
        finally:
            sem.release()


_slots: VerificationSlots | None = None


def verification_slots() -> VerificationSlots:
    """The process-wide Argon2 cap, configured from `AuthSettings`."""
    global _slots
    if _slots is None:
        from app.auth.config import get_auth_settings

        cfg = get_auth_settings()
        _slots = VerificationSlots(
            cfg.login_max_concurrent_verifications, cfg.login_verification_wait_seconds
        )
    return _slots


def reset_verification_slots() -> None:
    global _slots
    _slots = None
