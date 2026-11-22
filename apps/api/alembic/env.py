"""Alembic environment (async, asyncpg).

Which database URL: `config.attributes["database_url"]` (tests), else
`DATABASE_MIGRATION_URL` (the schema owner, given only to the migration job), else
`DATABASE_URL` (the app's own DML-only role; enough for `alembic current`, not for
`upgrade`).

Concurrency: every run takes a Postgres advisory lock before Alembic reads the
current revision, so two containers starting at once cannot both apply the same
migration. The second waits, then finds the schema at head and does nothing.
"""

import asyncio
import logging
import os
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from alembic import context
from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.session import make_engine, normalise_url, tls_mode
from app.settings import get_settings

config = context.config
target_metadata = Base.metadata
log = logging.getLogger("alembic.env")

# The `alembic` CLI (the container entrypoint) logs to stderr per alembic.ini. Callers
# that pass a URL in (tests) keep their own logging setup.
if config.config_file_name is not None and "database_url" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Advisory lock key for migrations: the bytes "DPmigrat" as a signed 64-bit integer.
# Any process that holds this lock is migrating the schema.
MIGRATION_LOCK_KEY = int.from_bytes(b"DPmigrat", "big", signed=True)


def _database_url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return url
    url = os.environ.get("DATABASE_MIGRATION_URL", "")
    if url:
        return url
    url = get_settings().database_url.get_secret_value()
    if not url:
        raise RuntimeError("neither DATABASE_MIGRATION_URL nor DATABASE_URL is set")
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


def _lock(connection: Connection) -> None:
    """Hold the migration lock until this transaction ends.

    This is the transaction-scoped form of `pg_advisory_lock`. Postgres releases it
    on commit, on rollback and if the connection drops, so a crashed migration never
    leaves it held. It also works through Neon's PgBouncer pooler (transaction mode),
    where a session-level lock could stay behind on a pooled server connection.
    Alembic runs the whole upgrade in one transaction (`transaction_per_migration` is
    off), so the lock covers every migration in the run."""
    got = connection.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
    ).scalar_one()
    if not got:
        log.info("waiting for the migration lock (another instance is migrating)")
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
    log.info("migration lock acquired")


def _run(connection: Connection) -> None:
    caller_txn = connection.in_transaction()
    role = connection.execute(text("SELECT current_user")).scalar_one()
    log.info("connected as database role %s", role)
    if not caller_txn:
        # The SELECT above autobegan a transaction; end it so Alembic opens its own.
        connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        _lock(connection)
        context.run_migrations()


async def _run_async() -> None:
    url = _database_url()
    log.info("database TLS: %s", tls_mode(normalise_url(url)[1]))
    engine = make_engine(url, poolclass=NullPool)
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
