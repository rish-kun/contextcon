"""Shared fixtures for tests/db and tests/jobs (imported by both conftests)."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import Base
from app.db.session import make_engine, make_sessionmaker
from tests.db import pg


@pytest.fixture(scope="session")
def pg_server() -> str:
    """Admin URL of the test Postgres server (see tests/db/pg.py)."""
    try:
        return pg.shared_server()
    except LookupError:
        pytest.skip("no Postgres: set TEST_DATABASE_URL or install postgres binaries")


@pytest.fixture(scope="session")
def db_url(pg_server: str) -> str:
    """A database migrated to head with Alembic (the migration is under test too)."""
    return pg.shared_migrated_database()


@pytest_asyncio.fixture
async def sm(db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory on an emptied database."""
    engine = make_engine(db_url, pool_size=20, max_overflow=20)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    try:
        yield make_sessionmaker(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(sm: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sm() as s:
        yield s
