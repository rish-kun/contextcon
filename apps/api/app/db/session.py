"""Async engine and sessions (SQLAlchemy 2 + asyncpg)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import get_settings

# libpq query parameters asyncpg does not understand.
_DROP_PARAMS = {"channel_binding", "options", "target_session_attrs"}


def to_async_url(url: str) -> str:
    """Turn a libpq-style URL (as Neon hands out) into a SQLAlchemy asyncpg URL.

    `postgres://` / `postgresql://` become `postgresql+asyncpg://`, `sslmode=…` becomes
    asyncpg's `ssl=…`, and parameters asyncpg rejects are dropped.
    """
    if not url:
        raise ValueError("DATABASE_URL is empty")
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        scheme = "postgresql+asyncpg"
    params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key in _DROP_PARAMS:
            continue
        if key == "sslmode":
            key = "ssl"
        params.append((key, value))
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def _connect_args(url: str) -> dict[str, Any]:
    # Neon's pooled endpoint (PgBouncer, transaction mode) cannot keep prepared
    # statements across transactions.
    if "-pooler." in (urlsplit(url).hostname or ""):
        return {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        }
    return {}


def make_engine(url: str, **kwargs: Any) -> AsyncEngine:
    async_url = to_async_url(url)
    kwargs.setdefault("pool_pre_ping", True)
    return create_async_engine(async_url, connect_args=_connect_args(async_url), **kwargs)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None, **kwargs: Any) -> AsyncEngine:
    """Create the process-wide engine (from `DATABASE_URL` unless a URL is given)."""
    global _engine, _sessionmaker
    if url is None:
        url = get_settings().database_url.get_secret_value()
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
