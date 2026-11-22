"""Create (or re-key) the API's DML-only database role and print its connection URL.

    gcloud secrets versions access latest --secret DATABASE_MIGRATION_URL \\
      --project cc-g527-showproduct \\
    | uv run --project apps/api python scripts/db/provision-app-role.py \\
    | gcloud secrets versions add DATABASE_URL --project cc-g527-showproduct --data-file=-

Reads the schema owner's URL (DATABASE_MIGRATION_URL, a direct, non-pooled Neon URL)
on stdin and writes the runtime role's URL on stdout. Secrets travel only through
the pipe: the script refuses to write to a terminal and never logs a URL or password.

What it does, as the owner:
1. Creates the role (LOGIN, no other attributes) or, if it exists, sets a new random
   password. Created with SQL, not through the Neon API, so it is not made a member
   of `neon_superuser`.
2. Applies scripts/db/app-role-grants.sql (DML on tables, USAGE on sequences, default
   privileges for future tables, read-only alembic_version).
3. Checks the role has no superuser-like attributes or role memberships.
4. Connects as the new role through the pooled host with full TLS verification and
   checks that DDL is refused.

The output URL uses the pooled (`-pooler`) host and `sslmode=verify-full`.
Run it after the schema exists (the first migration), because it revokes writes on
alembic_version.
"""

import asyncio
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
from app.db.session import normalise_url  # noqa: E402  (needs apps/api on the path)

GRANTS = Path(__file__).resolve().parent / "app-role-grants.sql"
APP_ROLE = os.environ.get("APP_ROLE", "dealproof_app")


def log(msg: str) -> None:
    print(f"provision-app-role: {msg}", file=sys.stderr)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def pooled_host(host: str) -> str:
    """Neon's pooled hostname: `-pooler` after the endpoint id (first label)."""
    first, _, rest = host.partition(".")
    return host if first.endswith("-pooler") else f"{first}-pooler.{rest}"


def asyncpg_args(url: str) -> tuple[str, dict]:
    """A plain asyncpg DSN plus connect kwargs, with the app's TLS handling."""
    async_url, args = normalise_url(url)
    parts = urlsplit(async_url)
    dsn = urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, ""))
    args.pop("prepared_statement_name_func", None)
    return dsn, args


async def main() -> None:
    owner_url = sys.stdin.read().strip()
    if not owner_url:
        sys.exit("provision-app-role: no owner URL on stdin")
    parts = urlsplit(owner_url)
    if parts.hostname and "-pooler." in parts.hostname:
        sys.exit("provision-app-role: use the direct (non-pooled) owner URL")
    database = parts.path.lstrip("/")
    password = secrets.token_urlsafe(32)  # [A-Za-z0-9_-] only: safe inside '...'

    dsn, kwargs = asyncpg_args(owner_url)
    conn = await asyncpg.connect(dsn, **kwargs)
    try:
        owner = await conn.fetchval("SELECT current_user")
        if not await conn.fetchval("SELECT to_regclass('public.alembic_version') IS NOT NULL"):
            sys.exit("provision-app-role: no alembic_version table; migrate first")
        table_owner = await conn.fetchval(
            "SELECT tableowner FROM pg_tables WHERE tablename = 'alembic_version'"
        )
        if table_owner != owner:
            sys.exit("provision-app-role: connect as the role that owns the schema")
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", APP_ROLE)
        attrs = (
            "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            " INHERIT CONNECTION LIMIT 60"
        )
        verb = "ALTER" if exists else "CREATE"
        async with conn.transaction():
            # Statement text holds the password; asyncpg does not log it, and Neon
            # stores it as a SCRAM verifier.
            await conn.execute(f"{verb} ROLE {quote_ident(APP_ROLE)} {attrs} PASSWORD '{password}'")
            await conn.execute(
                GRANTS.read_text().format(
                    app=quote_ident(APP_ROLE),
                    owner=quote_ident(owner),
                    database=quote_ident(database),
                )
            )
        log(f"{'re-keyed' if exists else 'created'} role {APP_ROLE}; grants applied as {owner}")

        row = await conn.fetchrow(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls,"
            " (SELECT count(*) FROM pg_auth_members m WHERE m.member = r.oid) AS memberships"
            " FROM pg_roles r WHERE rolname = $1",
            APP_ROLE,
        )
        flags = ("rolsuper", "rolcreaterole", "rolcreatedb", "rolreplication", "rolbypassrls")
        if any(row[k] for k in flags) or row["memberships"]:
            sys.exit(f"provision-app-role: {APP_ROLE} has extra attributes or role memberships")
    finally:
        await conn.close()

    host = pooled_host(parts.hostname or "")
    netloc = f"{quote(APP_ROLE, safe='')}:{password}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    app_url = urlunsplit(("postgresql", netloc, parts.path, "sslmode=verify-full", ""))

    dsn, kwargs = asyncpg_args(app_url)
    # Neon's proxy may take a moment to learn a new password.
    for attempt in range(6):
        try:
            app = await asyncpg.connect(dsn, **kwargs)
            break
        except asyncpg.InvalidPasswordError:
            if attempt == 5:
                raise
            await asyncio.sleep(5)
    try:
        if await app.fetchval("SELECT current_user") != APP_ROLE:
            sys.exit("provision-app-role: connected as the wrong role")
        try:
            await app.execute("CREATE TABLE provision_probe (id int)")
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            await app.execute("DROP TABLE provision_probe")
            sys.exit(f"provision-app-role: {APP_ROLE} can create tables")
    finally:
        await app.close()
    log(f"checked: {APP_ROLE} connects over the pooler with verify-full TLS and cannot run DDL")
    sys.stdout.write(app_url)


if __name__ == "__main__":
    if sys.stdout.isatty():
        sys.exit("provision-app-role: refusing to print a connection URL to a terminal; pipe it")
    asyncio.run(main())
