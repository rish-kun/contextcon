"""A throwaway Postgres for tests.

Order of preference:
1. `TEST_DATABASE_URL` (CI service, or a disposable Neon branch): a uniquely named
   database is created in it for the session and dropped afterwards. Nothing else on
   that server is touched.
2. A local `initdb` binary (e.g. Homebrew postgresql@17): a temporary cluster in a
   temp directory on a free port, removed afterwards.
3. Otherwise DB tests are skipped.
"""

import asyncio
import glob
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from alembic.config import Config

from alembic import command

API_DIR = Path(__file__).resolve().parents[2]


def _server_bin_dir() -> Path | None:
    """A directory holding initdb, pg_ctl *and* the postgres server.

    (Homebrew's libpq puts a client-only initdb on PATH, so PATH alone is not enough.)"""
    candidates: list[str] = []
    on_path = shutil.which("postgres")
    if on_path:
        candidates.append(str(Path(on_path).resolve().parent))
    for pattern in (
        "/opt/homebrew/opt/postgresql@*/bin",
        "/usr/local/opt/postgresql@*/bin",
        "/usr/lib/postgresql/*/bin",
        "/Applications/Postgres.app/Contents/Versions/*/bin",
    ):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    for candidate in candidates:
        d = Path(candidate)
        if all(os.access(d / b, os.X_OK) for b in ("initdb", "pg_ctl", "postgres")):
            return d
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _with_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + dbname, parts.query, parts.fragment))


def _asyncpg_dsn(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment))


async def _admin(url: str, sql: str) -> None:
    conn = await asyncpg.connect(_asyncpg_dsn(url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@contextmanager
def _local_cluster() -> Iterator[str]:
    bin_dir = _server_bin_dir()
    if bin_dir is None:
        raise LookupError("no local postgres binaries")
    initdb, pg_ctl = str(bin_dir / "initdb"), str(bin_dir / "pg_ctl")
    tmp = Path(tempfile.mkdtemp(prefix="dealproof-pg-"))
    data = tmp / "data"
    port = _free_port()
    opts = f"-c listen_addresses=127.0.0.1 -p {port} -k {tmp} -c fsync=off -c max_connections=200"
    try:
        subprocess.run(
            [initdb, "-D", str(data), "-U", "postgres", "--auth=trust", "-E", "UTF8"]
            + ["--no-locale"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [pg_ctl, "-D", str(data), "-o", opts, "-l", str(tmp / "log"), "-w", "start"],
            check=True,
            capture_output=True,
        )
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run([pg_ctl, "-D", str(data), "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def server_url() -> Iterator[str]:
    """Yield an admin URL for a server where test databases may be created."""
    env = os.environ.get("TEST_DATABASE_URL")
    if env:
        yield env
        return
    with _local_cluster() as url:
        yield url


@contextmanager
def fresh_database(admin_url: str) -> Iterator[str]:
    name = f"dealproof_test_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin(admin_url, f'CREATE DATABASE "{name}"'))
    try:
        yield _with_db(admin_url, name)
    finally:
        asyncio.run(_admin(admin_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url
    return cfg


def migrate(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)


_stack = None
_admin_url: str | None = None
_db_url: str | None = None


def shared_server() -> str:
    """Admin URL of one test server per process, torn down at interpreter exit.

    Both tests/db and tests/jobs import the same fixtures, which pytest would otherwise
    set up once per directory."""
    global _stack, _admin_url
    if _admin_url is None:
        import atexit
        from contextlib import ExitStack

        stack = ExitStack()
        _admin_url = stack.enter_context(server_url())
        atexit.register(stack.close)
        _stack = stack
    return _admin_url


def shared_migrated_database() -> str:
    """One database migrated to head, shared by the whole test process."""
    global _db_url
    if _db_url is None:
        assert _stack is not None or shared_server()
        url = _stack.enter_context(fresh_database(shared_server()))  # type: ignore[union-attr]
        migrate(url)
        _db_url = url
    return _db_url


# The grants production gives the API's runtime role (scripts/db/app-role-grants.sql).
APP_ROLE_GRANTS = API_DIR.parents[1] / "scripts" / "db" / "app-role-grants.sql"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def app_role_grants_sql(app: str, owner: str, database: str) -> str:
    return APP_ROLE_GRANTS.read_text().format(
        app=quote_ident(app), owner=quote_ident(owner), database=quote_ident(database)
    )


def _run_outside_loop(fn: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """asyncio.run(fn()), also from inside a running loop (async fixtures), where it
    runs on a worker thread. Cleanup at interpreter exit has no loop and no threads."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(fn())
        return
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: asyncio.run(fn())).result()


@contextmanager
def app_role(db_url: str) -> Iterator[str]:
    """A NOLOGIN role holding exactly the production runtime grants on `db_url`.

    Tests reach it with SET ROLE (asyncpg `server_settings={"role": ...}`), so it needs
    no password. Roles are cluster-wide, so the name is unique and the role is dropped
    afterwards."""
    name = f"dealproof_app_{uuid.uuid4().hex[:12]}"
    database = urlsplit(db_url).path.lstrip("/")

    async def create() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(db_url))
        try:
            await conn.execute(f"CREATE ROLE {quote_ident(name)} NOLOGIN")
            owner = await conn.fetchval(
                "SELECT tableowner FROM pg_tables WHERE tablename = 'alembic_version'"
            )
            await conn.execute(f"SET ROLE {quote_ident(owner)}")
            await conn.execute(app_role_grants_sql(name, owner, database))
        finally:
            await conn.close()

    async def drop() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(db_url))
        try:
            await conn.execute(f"DROP OWNED BY {quote_ident(name)}")
            await conn.execute(f"DROP ROLE IF EXISTS {quote_ident(name)}")
        finally:
            await conn.close()

    _run_outside_loop(create)
    try:
        yield name
    finally:
        _run_outside_loop(drop)


_app_role: str | None = None


def shared_app_role() -> str:
    """The runtime role on the shared migrated database (see `app_role`)."""
    global _app_role
    if _app_role is None:
        url = shared_migrated_database()
        # Entered after the database, so the role is dropped before the database is.
        _app_role = _stack.enter_context(app_role(url))  # type: ignore[union-attr]
    return _app_role
