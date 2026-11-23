"""Sign-in attempt limiter (in-process, sliding window) and the Argon2 concurrency cap.

Up to four keys are counted per attempt, each with its own limit:

- (email, client IP): tight. Stops one client guessing one account.
- email: looser. Rotating or spoofed client IPs cannot guess one password faster than
  this. Someone who knows an email can lock it out of password sign-in for one window
  (existing sessions keep working).
- client IP: across every email. A stream of distinct, made-up emails from one client
  would otherwise get a fresh budget (and an Argon2 check) on every request. Counted only
  when the caller says the IP is really the client's (`ip_trusted`); otherwise every
  browser behind one proxy would share it.
- global: across every client. Bounds the total Argon2 work an attacker with many IPs
  can force. When it trips, sign-in pauses for new (email, IP) pairs until the window
  slides; the default is set well above real traffic.

An (email, IP) pair that signed in successfully is remembered for `known_ttl_seconds` and
skips the per-IP and global keys, so a flood from elsewhere does not lock returning users
out. IPv6 addresses are grouped by /64, since one host usually controls a whole /64.

`acquire` checks and reserves an attempt in one step under the lock, so a burst of
parallel guesses cannot all pass the check before the first failure is recorded. A
successful sign-in refunds its reservation everywhere and clears the (email, IP) key.

Memory is bounded: emptied keys are dropped, a full sweep of expired keys runs at most
once per window, and at most `max_keys` keys (and known pairs) are kept, least recently
used evicted first.

Counts live in one process. With several API instances each keeps its own, so the
effective limits are multiplied by the instance count. That is accepted for the demo
(a handful of instances at most); a shared store (Postgres or Redis) would fix it.
"""

import asyncio
import ipaddress
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

Key = tuple[str, ...]


def ip_bucket(ip: str) -> str:
    """The unit an IP is counted under: itself for IPv4, its /64 for IPv6."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


@dataclass(frozen=True, slots=True)
class Reservation:
    """One reserved attempt: when, and which keys it was counted under."""

    email: str
    ip: str
    at: float
    keys: tuple[Key, ...]


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
        known_ttl_seconds: float = 30 * 24 * 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_client = per_client
        self.per_email = per_email
        self.per_ip = per_ip
        self.global_limit = global_limit
        self.window = window_seconds
        self.max_keys = max_keys
        self.known_ttl = known_ttl_seconds
        self._clock = clock
        # Least recently hit first, so eviction drops the stalest key.
        self._failures: OrderedDict[Key, deque[float]] = OrderedDict()
        # (email, ip bucket) pairs that signed in, with when the memory expires.
        self._known: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._last_sweep = clock()
        self._lock = threading.Lock()

    def _is_known(self, email: str, ip: str, now: float) -> bool:
        expires = self._known.get((email, ip))
        if expires is None:
            return False
        if expires <= now:
            del self._known[(email, ip)]
            return False
        return True

    def _keys(self, email: str, ip: str, ip_trusted: bool, now: float) -> list[tuple[Key, int]]:
        keys: list[tuple[Key, int]] = [
            (("client", email, ip), self.per_client),
            (("email", email), self.per_email),
        ]
        if self._is_known(email, ip, now):
            return keys
        if self.per_ip is not None and ip_trusted:
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
        """Drop every expired key and known pair, at most once per window."""
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        for key in list(self._failures):
            self._prune(key, now)
        for pair, expires in list(self._known.items()):
            if expires <= now:
                del self._known[pair]

    def _hit(self, key: Key, now: float) -> None:
        hits = self._failures.get(key)
        if hits is None:
            hits = self._failures[key] = deque()
        else:
            self._failures.move_to_end(key)
        hits.append(now)
        while len(self._failures) > self.max_keys:
            self._failures.popitem(last=False)

    def _wait(self, keys: list[tuple[Key, int]], now: float) -> float:
        wait = 0.0
        for key, limit in keys:
            hits = self._prune(key, now)
            if len(hits) >= limit:
                wait = max(wait, hits[len(hits) - limit] + self.window - now)
        return wait

    @staticmethod
    def _seconds(wait: float) -> int | None:
        return max(1, math.ceil(wait)) if wait > 0 else None

    def __len__(self) -> int:
        """Failure keys currently held (for tests and monitoring)."""
        with self._lock:
            return len(self._failures)

    def retry_after(self, email: str, ip: str, *, ip_trusted: bool = True) -> int | None:
        """Seconds until another attempt is allowed, or None if allowed now."""
        now, ip = self._clock(), ip_bucket(ip)
        with self._lock:
            return self._seconds(self._wait(self._keys(email, ip, ip_trusted, now), now))

    def acquire(
        self, email: str, ip: str, *, ip_trusted: bool = True
    ) -> tuple[int | None, Reservation | None]:
        """Atomically check and reserve one attempt (counted as a failure until
        `succeeded` or `refund` gives it back). Returns (retry_after, None) when
        limited, else (None, reservation)."""
        now, ip = self._clock(), ip_bucket(ip)
        with self._lock:
            self._sweep(now)
            keys = self._keys(email, ip, ip_trusted, now)
            wait = self._wait(keys, now)
            if wait > 0:
                return self._seconds(wait), None
            for key, _ in keys:
                self._hit(key, now)
            return None, Reservation(email, ip, now, tuple(key for key, _ in keys))

    def _refund(self, reservation: Reservation) -> None:
        for key in reservation.keys:
            hits = self._failures.get(key)
            if hits is None:
                continue
            try:
                hits.remove(reservation.at)
            except ValueError:
                pass
            if not hits:
                del self._failures[key]

    def refund(self, reservation: Reservation) -> None:
        """Give back a reservation for an attempt that never checked a password."""
        with self._lock:
            self._refund(reservation)

    def succeeded(self, reservation: Reservation) -> None:
        """Refund a successful attempt, clear the (email, IP) failures and remember the
        pair as known."""
        email, ip = reservation.email, reservation.ip
        with self._lock:
            self._refund(reservation)
            self._failures.pop(("client", email, ip), None)
            self._known[(email, ip)] = self._clock() + self.known_ttl
            self._known.move_to_end((email, ip))
            while len(self._known) > self.max_keys:
                self._known.popitem(last=False)

    def record_failure(self, email: str, ip: str, *, ip_trusted: bool = True) -> None:
        now, ip = self._clock(), ip_bucket(ip)
        with self._lock:
            for key, _ in self._keys(email, ip, ip_trusted, now):
                self._hit(key, now)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._known.clear()


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
    global _limiter, _signup_limiter, _resend_limiter
    _limiter = None
    _signup_limiter = None
    _resend_limiter = None


# Sign-up and "send a new verification link" reuse the same keyed sliding window. Their
# reservations are never refunded on success: every request counts, since each one can
# create an account or send an email.
_signup_limiter: LoginRateLimiter | None = None
_resend_limiter: LoginRateLimiter | None = None


def signup_limiter() -> LoginRateLimiter:
    """The process-wide `POST /auth/signup` limiter."""
    global _signup_limiter
    if _signup_limiter is None:
        from app.auth.config import get_auth_settings

        cfg = get_auth_settings()
        _signup_limiter = LoginRateLimiter(
            per_client=cfg.signup_max_per_client,
            per_email=cfg.signup_max_per_email,
            per_ip=cfg.signup_max_per_ip,
            global_limit=cfg.signup_max_global,
            window_seconds=cfg.signup_window_seconds,
            max_keys=cfg.login_max_tracked_keys,
        )
    return _signup_limiter


def resend_limiter() -> LoginRateLimiter:
    """The process-wide `POST /auth/verify/resend` limiter."""
    global _resend_limiter
    if _resend_limiter is None:
        from app.auth.config import get_auth_settings

        cfg = get_auth_settings()
        _resend_limiter = LoginRateLimiter(
            per_client=cfg.resend_max_per_client,
            per_email=cfg.resend_max_per_email,
            per_ip=cfg.resend_max_per_ip,
            window_seconds=cfg.resend_window_seconds,
            max_keys=cfg.login_max_tracked_keys,
        )
    return _resend_limiter


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
