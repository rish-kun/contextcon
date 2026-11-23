"""Account administration. People can also sign up on `/signup`; accounts made here
count as email-verified (use it for teammates and demo accounts).

    uv run python -m app.auth.cli create-workspace --name "Demo fund"
    uv run python -m app.auth.cli create-user --email a@fund.example --name "Asha Rao" \\
        --workspace "Demo fund"                       # prompts for the password twice
    printf '%s' "$PW" | uv run python -m app.auth.cli create-user ... --password-stdin
    uv run python -m app.auth.cli set-password --email a@fund.example   # ends their sessions
    uv run python -m app.auth.cli list-users [--workspace "Demo fund"]

`--workspace` takes a workspace id or its exact name. The database is `DATABASE_URL`.
Passwords are never accepted as arguments, so they stay out of shell history.
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import sessions
from app.auth.config import get_auth_settings
from app.db.models import User, Workspace
from app.db.session import make_engine, make_sessionmaker
from app.settings import get_settings


class CliError(Exception):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.auth.cli", description=__doc__.split("\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ws = sub.add_parser("create-workspace", help="create a workspace and print its id")
    ws.add_argument("--name", required=True)

    user = sub.add_parser("create-user", help="create a named user with a password")
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True, help="display name shown on approvals")
    user.add_argument("--workspace", required=True, help="workspace id or exact name")
    user.add_argument("--password-stdin", action="store_true", help="read the password from stdin")

    pw = sub.add_parser("set-password", help="replace a user's password; ends their sessions")
    pw.add_argument("--email", required=True)
    pw.add_argument("--password-stdin", action="store_true", help="read the password from stdin")

    ls = sub.add_parser("list-users", help="list users (email, name, workspace)")
    ls.add_argument("--workspace", help="workspace id or exact name")
    return parser


def read_password(from_stdin: bool, stdin: TextIO) -> str:
    if from_stdin:
        password = stdin.read().rstrip("\r\n")
    else:
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise CliError("passwords do not match")
    minimum = get_auth_settings().min_password_length
    if len(password) < minimum:
        raise CliError(f"password must be at least {minimum} characters")
    if len(password) > 1024:
        raise CliError("password must be at most 1024 characters")
    return password


async def _run(args: argparse.Namespace, database_url: str, stdin: TextIO, out: TextIO) -> None:
    engine = make_engine(database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            if args.command == "create-workspace":
                if not args.name.strip():
                    raise CliError("workspace name is empty")
                ws = await sessions.create_workspace(db, args.name)
                await db.commit()
                print(f"workspace {ws.id} {ws.name!r}", file=out)
            elif args.command == "create-user":
                if not args.name.strip():
                    raise CliError("display name is empty: approvals need a named person")
                if "@" not in args.email:
                    raise CliError("email looks invalid")
                try:
                    ws = await sessions.find_workspace(db, args.workspace)
                except LookupError as exc:
                    raise CliError(str(exc)) from None
                if await sessions.find_user_by_email(db, args.email) is not None:
                    raise CliError(f"a user with email {args.email.strip().lower()!r} exists")
                password = read_password(args.password_stdin, stdin)
                try:
                    user = await sessions.create_user(
                        db, ws.id, email=args.email, display_name=args.name, password=password
                    )
                    await db.commit()
                except IntegrityError:
                    raise CliError("could not create the user (duplicate email?)") from None
                print(f"user {user.id} {user.email} {user.display_name!r} in {ws.name!r}", file=out)
            elif args.command == "set-password":
                if await sessions.find_user_by_email(db, args.email) is None:
                    raise CliError(f"no user with email {args.email.strip().lower()!r}")
                password = read_password(args.password_stdin, stdin)
                user = await sessions.set_password(db, args.email, password)
                await db.commit()
                print(f"password updated for {user.email}; their sessions were ended", file=out)
            elif args.command == "list-users":
                stmt = (
                    select(User, Workspace)
                    .join(Workspace, Workspace.id == User.workspace_id)
                    .order_by(Workspace.name, User.email)
                )
                if args.workspace:
                    try:
                        ws = await sessions.find_workspace(db, args.workspace)
                    except LookupError as exc:
                        raise CliError(str(exc)) from None
                    stmt = stmt.where(User.workspace_id == ws.id)
                for user, ws in (await db.execute(stmt)).all():
                    print(f"{user.email}\t{user.display_name}\t{ws.name}\t{ws.id}", file=out)
    finally:
        await engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    database_url: str | None = None,
    stdin: TextIO | None = None,
    out: TextIO | None = None,
) -> int:
    args = _parser().parse_args(argv)
    url = database_url or get_settings().database_url.get_secret_value()
    err = sys.stderr
    if not url:
        print("error: DATABASE_URL is not set", file=err)
        return 2
    try:
        asyncio.run(_run(args, url, stdin or sys.stdin, out or sys.stdout))
    except CliError as exc:
        print(f"error: {exc}", file=err)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
