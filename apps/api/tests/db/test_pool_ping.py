"""The pool pings a connection only after it sat idle, and replaces one that died."""

import asyncpg
import pytest
from sqlalchemy import text

from app.db.session import make_engine
from tests.db.pg import _asyncpg_dsn

pytestmark = pytest.mark.asyncio


async def _backend_pid(engine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT pg_backend_pid()"))).scalar_one()


async def test_recently_used_connection_is_not_pinged(db_url, monkeypatch) -> None:
    monkeypatch.setenv("DB_PING_IDLE_SECONDS", "3600")
    engine = make_engine(db_url, pool_size=1, max_overflow=0)
    pings: list[object] = []
    monkeypatch.setattr(
        engine.sync_engine.dialect, "do_ping", lambda conn: pings.append(conn) or True
    )
    try:
        first = await _backend_pid(engine)
        assert await _backend_pid(engine) == first  # reused, and not pinged
        assert pings == []
    finally:
        await engine.dispose()


async def test_idle_connection_that_died_is_replaced(db_url, monkeypatch) -> None:
    monkeypatch.setenv("DB_PING_IDLE_SECONDS", "0")  # every reused connection counts as idle
    engine = make_engine(db_url, pool_size=1, max_overflow=0)
    try:
        dead = await _backend_pid(engine)
        admin = await asyncpg.connect(_asyncpg_dsn(db_url))
        try:
            await admin.execute("SELECT pg_terminate_backend($1)", dead)
        finally:
            await admin.close()
        # The ping on checkout finds the connection gone; the pool opens a new one and
        # the caller never sees the dead connection.
        assert await _backend_pid(engine) != dead
    finally:
        await engine.dispose()
