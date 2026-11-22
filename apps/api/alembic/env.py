"""Alembic environment (async, asyncpg)."""

import asyncio

from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from alembic import context
from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.session import make_engine
from app.settings import get_settings

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return url
    url = get_settings().database_url.get_secret_value()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url="postgresql://",  # offline SQL generation needs only the dialect
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = make_engine(_database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
