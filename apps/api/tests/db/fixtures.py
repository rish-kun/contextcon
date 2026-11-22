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
    """Session factory on an emptied database, running as the app's runtime role.

    Production runs the API as a DML-only role (scripts/db/app-role-grants.sql), so
    app code under test gets the same privileges. Only the TRUNCATE below runs as the
    owner. (The role comes from `pg.shared_app_role()` rather than a fixture, so the
    conftests that import these fixtures by name need no change.)"""
    app_role = pg.shared_app_role()
    owner = make_engine(db_url)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    try:
        async with owner.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    finally:
        await owner.dispose()
    engine = make_engine(
        db_url,
        pool_size=20,
        max_overflow=20,
        connect_args={"server_settings": {"role": app_role}},
    )
    try:
        yield make_sessionmaker(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(sm: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sm() as s:
        yield s
