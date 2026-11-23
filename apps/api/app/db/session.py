"""Async engine and sessions (SQLAlchemy 2 + asyncpg)."""

import ipaddress
import logging
import os
import ssl
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import event, exc
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import get_settings

log = logging.getLogger(__name__)

# libpq query parameters asyncpg does not understand. Neon's URLs carry
# `channel_binding=require`, which asyncpg rejects.
_DROP_PARAMS = {"channel_binding", "options", "target_session_attrs"}
# libpq names for the TLS mode.
_SSL_PARAMS = {"sslmode", "ssl"}
_SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
# Modes that ask for encryption. All of them get full verification (CA chain and
# hostname): libpq's `require` encrypts without authenticating the server, which
# lets anyone on the path impersonate the database, so it is upgraded here.
_VERIFIED_MODES = {"require", "verify-ca", "verify-full"}


def verified_ssl_context() -> ssl.SSLContext:
    """TLS that authenticates the server: the system CA store plus a hostname check.

    asyncpg passes the URL's host as `server_hostname`, so the certificate must name
    the host in the URL (Neon's certificates cover `*.<region>.aws.neon.tech`)."""
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    # create_default_context already sets these; pin them so a later edit can't relax them.
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _is_local(host: str | None) -> bool:
    """Loopback, a Unix socket directory, or no host (libpq's local default)."""
    if not host or host.startswith("/") or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalise_url(url: str) -> tuple[str, dict[str, Any]]:
    """Split a libpq-style URL (as Neon hands out) into an asyncpg URL and connect args.

    `postgres://` / `postgresql://` become `postgresql+asyncpg://`. `sslmode=…` is
    removed from the query and returned as asyncpg's `ssl` connect argument, and
    parameters asyncpg rejects (such as `channel_binding`) are dropped.

    TLS: `require`, `verify-ca` and `verify-full` all become a verifying
    `ssl.SSLContext` (see `verified_ssl_context`). A remote host with no `sslmode`
    gets the same, instead of asyncpg's unverified `prefer` default. `disable`,
    `allow` and `prefer` pass through unchanged for local development.
    """
    if not url:
        raise ValueError("DATABASE_URL is empty")
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        scheme = "postgresql+asyncpg"
    params = []
    connect_args: dict[str, Any] = {}
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key in _DROP_PARAMS:
            continue
        if key in _SSL_PARAMS:
            mode = value.lower()
            if mode in {"true", "1"}:
                mode = "require"
            elif mode in {"false", "0"}:
                mode = "disable"
            if mode not in _SSL_MODES:
                raise ValueError(f"unsupported {key} value in DATABASE_URL")
            connect_args["ssl"] = verified_ssl_context() if mode in _VERIFIED_MODES else mode
            continue
        params.append((key, value))
    if "ssl" not in connect_args and not _is_local(parts.hostname):
        connect_args["ssl"] = verified_ssl_context()
    async_url = urlunsplit((scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))
    connect_args.update(_connect_args(async_url))
    return async_url, connect_args


def to_async_url(url: str) -> str:
    """The asyncpg URL from `normalise_url`, without the connect args."""
    return normalise_url(url)[0]


def _connect_args(url: str) -> dict[str, Any]:
    # Neon's pooled endpoint (PgBouncer, transaction mode) cannot keep prepared
    # statements across transactions.
    if "-pooler." in (urlsplit(url).hostname or ""):
        return {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        }
    return {}


def tls_mode(connect_args: dict[str, Any]) -> str:
    """A loggable description of the TLS setting in `normalise_url`'s connect args."""
    value = connect_args.get("ssl")
    if isinstance(value, ssl.SSLContext):
        verified = value.verify_mode == ssl.CERT_REQUIRED and value.check_hostname
        return "verify-full" if verified else "unverified"
    return str(value) if value is not None else "default"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _install_idle_ping(engine: AsyncEngine, idle_seconds: float) -> None:
    """Ping a pooled connection on checkout only when it sat idle for `idle_seconds`.

    SQLAlchemy's `pool_pre_ping` pings on every checkout, and on asyncpg a ping is
    BEGIN, a query and ROLLBACK: about four round trips, which to Neon (Mumbai to
    Singapore) added ~150 ms to every session of every request. A connection used a
    few seconds ago is alive (Neon suspends a compute only after minutes without
    traffic), so only connections idle longer than the threshold are pinged; a fresh
    connection is never pinged. A failed ping raises `DisconnectionError`, which makes
    the pool drop that connection and check out another, as `pool_pre_ping` does.
    """
    pool = engine.sync_engine.pool
    dialect = engine.sync_engine.dialect

    @event.listens_for(pool, "checkin")
    def _checked_in(dbapi_connection: Any, record: Any) -> None:
        record.info["dp_idle_since"] = time.monotonic()

    @event.listens_for(pool, "checkout")
    def _checked_out(dbapi_connection: Any, record: Any, proxy: Any) -> None:
        since = record.info.get("dp_idle_since")
        if since is None or time.monotonic() - since < idle_seconds:
            return
        try:
            dialect.do_ping(dbapi_connection)
        except Exception as error:
            raise exc.DisconnectionError("pooled connection failed its ping") from error


def make_engine(url: str, **kwargs: Any) -> AsyncEngine:
    async_url, connect_args = normalise_url(url)
    connect_args.update(kwargs.pop("connect_args", {}))
    # An explicit `pool_pre_ping=True` keeps SQLAlchemy's ping-on-every-checkout.
    idle_ping = not kwargs.get("pool_pre_ping", False) and "poolclass" not in kwargs
    if "poolclass" not in kwargs:
        # QueuePool sizing; the 5 + 10 default ran out under streams plus in-process workers.
        kwargs.setdefault("pool_size", _env_int("DB_POOL_SIZE", 20))
        kwargs.setdefault("max_overflow", _env_int("DB_MAX_OVERFLOW", 20))
        kwargs.setdefault("pool_timeout", _env_int("DB_POOL_TIMEOUT", 10))
        kwargs.setdefault("pool_recycle", _env_int("DB_POOL_RECYCLE", 300))
        # Reuse the most recently returned connection: its prepared statements are
        # cached (asyncpg prepares each new statement in an extra round trip) and it
        # was used moments ago, so it needs no ping. FIFO rotated through all 20.
        kwargs.setdefault("pool_use_lifo", True)
    engine = create_async_engine(async_url, connect_args=connect_args, **kwargs)
    if idle_ping:
        _install_idle_ping(engine, _env_int("DB_PING_IDLE_SECONDS", 30))
    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None, **kwargs: Any) -> AsyncEngine:
    """Create the process-wide engine (from `DATABASE_URL` unless a URL is given)."""
    global _engine, _sessionmaker
    if url is None:
        url = get_settings().database_url.get_secret_value()
    log.info("database TLS: %s", tls_mode(normalise_url(url)[1]))
    _engine = make_engine(url, **kwargs)
    _sessionmaker = make_sessionmaker(_engine)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def database_configured() -> bool:
    return _engine is not None or bool(get_settings().database_url.get_secret_value())


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A session that commits on success and rolls back on error (worker use)."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
