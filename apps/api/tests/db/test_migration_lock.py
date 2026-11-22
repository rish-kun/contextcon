"""`alembic upgrade head` from two containers at once applies each migration once.

Alembic's `context` is process-global, so each run is a real `alembic` subprocess,
the way two Cloud Run instances would run it."""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import asyncpg

from tests.db import pg

API_DIR = Path(__file__).resolve().parents[2]
LOCK_KEY = int.from_bytes(b"DPmigrat", "big", signed=True)


def _start_upgrade(url: str, **extra_env: str) -> subprocess.Popen[str]:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["DATABASE_MIGRATION_URL"] = url
    env.update(extra_env)
    return subprocess.Popen(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _finish(proc: subprocess.Popen[str], ok: bool = True) -> str:
    _, err = proc.communicate(timeout=120)
    assert (proc.returncode == 0) == ok, err
    return err


async def _revision(url: str) -> str:
    conn = await asyncpg.connect(pg._asyncpg_dsn(url))
    try:
        return await conn.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await conn.close()


async def _hold_worker_locks(url: str, seconds: float, proc_env: dict[str, str]) -> str:
    """Hold FOR UPDATE on steps (as the API's job worker does) while an upgrade that
    alters steps starts, for `seconds`. Returns the upgrade's stderr."""
    worker = await asyncpg.connect(pg._asyncpg_dsn(url))
    try:
        tx = worker.transaction()
        await tx.start()
        await worker.execute("SELECT * FROM steps FOR UPDATE")
        proc = _start_upgrade(url, **proc_env)
        await asyncio.sleep(seconds)
        await tx.rollback()
    finally:
        await worker.close()
    return _finish(proc, ok=proc_env.get("EXPECT_OK", "1") == "1")


async def _version_table_exists(url: str) -> bool:
    conn = await asyncpg.connect(pg._asyncpg_dsn(url))
    try:
        return bool(await conn.fetchval("SELECT to_regclass('public.alembic_version') IS NOT NULL"))
    finally:
        await conn.close()


def test_upgrade_waits_for_the_lock_then_is_a_no_op(pg_server: str) -> None:
    with pg.fresh_database(pg_server) as url:

        async def hold_lock_while_upgrade_starts() -> subprocess.Popen[str]:
            holder = await asyncpg.connect(pg._asyncpg_dsn(url))
            try:
                await holder.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)
                proc = _start_upgrade(url)
                await asyncio.sleep(3)
                assert proc.poll() is None, "upgrade did not wait for the lock"
                assert not await _version_table_exists(url)
                await holder.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
                return proc
            finally:
                await holder.close()

        first = asyncio.run(hold_lock_while_upgrade_starts())
        err = _finish(first)
        assert "waiting for the migration lock" in err
        assert "Running upgrade" in err

        again = _finish(_start_upgrade(url))
        assert "migration lock acquired" in again
        assert "Running upgrade" not in again


def test_concurrent_upgrades_both_succeed(pg_server: str) -> None:
    with pg.fresh_database(pg_server) as url:
        procs = [_start_upgrade(url) for _ in range(3)]
        started = time.monotonic()
        errs = [_finish(p) for p in procs]
        assert time.monotonic() - started < 120
        # Exactly one run applied the migrations; the others found head.
        assert sum("Running upgrade  -> 0001" in e for e in errs) == 1


def test_upgrade_retries_when_live_row_locks_block_ddl(pg_server: str) -> None:
    """The deadlock that broke deploys: 0004 alters `steps` while the running API's
    worker holds row locks on it. The upgrade times out on the lock, rolls back,
    backs off and succeeds once the worker's transaction ends."""
    with pg.fresh_database(pg_server) as url:
        pg.migrate(url, "0003")
        env = {"MIGRATION_LOCK_TIMEOUT": "300ms", "MIGRATION_ATTEMPTS": "10"}
        err = asyncio.run(_hold_worker_locks(url, 2.5, env))
        assert "rolled back on lock_timeout" in err
        assert asyncio.run(_revision(url)) == "0004"


def test_upgrade_gives_up_after_its_attempts_and_leaves_the_schema_unchanged(
    pg_server: str,
) -> None:
    with pg.fresh_database(pg_server) as url:
        pg.migrate(url, "0003")
        env = {"MIGRATION_LOCK_TIMEOUT": "200ms", "MIGRATION_ATTEMPTS": "2", "EXPECT_OK": "0"}
        err = asyncio.run(_hold_worker_locks(url, 6, env))
        assert "attempt 1/2 rolled back" in err
        assert asyncio.run(_revision(url)) == "0003"
