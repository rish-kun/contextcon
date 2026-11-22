"""Alembic environment (async, asyncpg).

Which database URL: `config.attributes["database_url"]` (tests), else
`DATABASE_MIGRATION_URL` (the schema owner, given only to the migration job), else
`DATABASE_URL` (the app's own DML-only role; enough for `alembic current`, not for
`upgrade`).

Concurrency: every run takes a Postgres advisory lock before Alembic reads the
current revision, so two containers starting at once cannot both apply the same
migration. The second waits, then finds the schema at head and does nothing.

Live traffic: once it holds that lock, the run sets `lock_timeout`
(MIGRATION_LOCK_TIMEOUT, default 5s), so a DDL statement that would queue behind the
running API's row locks (the job worker's FOR UPDATE on runs/steps) gives up instead
of stalling every query queued behind it. A lock timeout or deadlock rolls the whole
upgrade back (DDL is transactional), and the upgrade is retried with backoff, up to
MIGRATION_ATTEMPTS times (default 8).
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
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

# How long one DDL statement may wait for a table lock, and how often to retry.
LOCK_TIMEOUT = os.environ.get("MIGRATION_LOCK_TIMEOUT", "5s")
ATTEMPTS = max(1, int(os.environ.get("MIGRATION_ATTEMPTS", "8")))
MAX_BACKOFF_SECONDS = 30.0
# deadlock_detected, lock_not_available (lock_timeout)
_RETRYABLE_SQLSTATES = {"40P01", "55P03"}


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
    # Set only after the advisory lock, so waiting for another migrator is unbounded
    # but each statement of our own gives up on a table lock after LOCK_TIMEOUT.
    connection.execute(text("SELECT set_config('lock_timeout', :t, true)"), {"t": LOCK_TIMEOUT})


def _sqlstate(exc: BaseException) -> str | None:
    """The Postgres SQLSTATE behind a SQLAlchemy/asyncpg error, if any."""
    seen: BaseException | None = exc.orig if isinstance(exc, DBAPIError) else exc
    while seen is not None:
        code = getattr(seen, "sqlstate", None) or getattr(seen, "pgcode", None)
        if code:
            return str(code)
        seen = seen.__cause__
    return None


def _with_retries(run: Callable[[], None]) -> None:
    delay = 1.0
    for attempt in range(1, ATTEMPTS + 1):
        try:
            run()
            return
        except DBAPIError as exc:
            code = _sqlstate(exc)
            if code not in _RETRYABLE_SQLSTATES or attempt == ATTEMPTS:
                raise
            reason = "deadlock" if code == "40P01" else f"lock_timeout ({LOCK_TIMEOUT})"
            log.warning(
                "migration attempt %d/%d rolled back on %s; retrying in %.0fs",
                attempt,
                ATTEMPTS,
                reason,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, MAX_BACKOFF_SECONDS)


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
        _run(connection)  # the caller owns the connection and its transaction
        return
    _with_retries(lambda: asyncio.run(_run_async()))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
