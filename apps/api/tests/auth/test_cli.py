"""`python -m app.auth.cli`: workspaces, users, passwords."""

import asyncio
import io
import subprocess
import sys

import pytest
from sqlalchemy import select

from app.auth.cli import main
from app.auth.passwords import verify_password
from app.db.models import AuthSession, User, Workspace
from tests.auth.conftest import client_for
from tests.auth.helpers import PASSWORD, login
from tests.db.pg import API_DIR


def _cli(db_url: str, *argv: str, stdin: str = "") -> tuple[int, str]:
    out = io.StringIO()
    code = main(list(argv), database_url=db_url, stdin=io.StringIO(stdin), out=out)
    return code, out.getvalue()


@pytest.fixture
def cli(sm, db_url):  # sm empties the database first
    return lambda *argv, stdin="": _cli(db_url, *argv, stdin=stdin)


@pytest.mark.asyncio
async def test_create_workspace_and_user_then_sign_in(cli, app, session) -> None:
    code, out = await asyncio.to_thread(cli, "create-workspace", "--name", "Demo fund")
    assert code == 0 and out.startswith("workspace ")
    code, out = await asyncio.to_thread(
        cli,
        "create-user",
        "--email",
        "Asha@Fund.example",
        "--name",
        "Asha Rao",
        "--workspace",
        "Demo fund",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert code == 0, out
    user = (await session.execute(select(User))).scalar_one()
    ws = (await session.execute(select(Workspace))).scalar_one()
    assert user.email == "asha@fund.example" and user.display_name == "Asha Rao"
    assert user.workspace_id == ws.id
    assert user.password_hash and PASSWORD not in user.password_hash
    assert verify_password(user.password_hash, PASSWORD)

    async with client_for(app) as client:
        response = await login(client, "asha@fund.example")
    assert response.status_code == 200 and response.json()["display_name"] == "Asha Rao"

    code, out = await asyncio.to_thread(cli, "list-users", "--workspace", str(ws.id))
    assert code == 0 and "asha@fund.example\tAsha Rao\tDemo fund" in out


def test_create_user_rejects_bad_input(cli, capsys) -> None:
    cli("create-workspace", "--name", "Demo fund")
    base = ["create-user", "--email", "a@fund.example", "--workspace", "Demo fund"]
    assert cli(*base, "--name", "A", "--password-stdin", stdin="short")[0] == 1
    assert "at least" in capsys.readouterr().err
    assert cli(*base, "--name", "  ", "--password-stdin", stdin=PASSWORD)[0] == 1
    assert "named person" in capsys.readouterr().err
    assert cli(*base[:-1], "Nope", "--name", "A", "--password-stdin", stdin=PASSWORD)[0] == 1
    assert "no workspace" in capsys.readouterr().err
    assert cli(*base, "--name", "A", "--password-stdin", stdin=PASSWORD)[0] == 0
    assert cli(*base, "--name", "B", "--password-stdin", stdin=PASSWORD)[0] == 1
    assert "exists" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_set_password_ends_sessions(cli, app, session) -> None:
    await asyncio.to_thread(cli, "create-workspace", "--name", "Demo fund")
    await asyncio.to_thread(
        cli,
        "create-user",
        "--email",
        "a@fund.example",
        "--name",
        "A Person",
        "--workspace",
        "Demo fund",
        "--password-stdin",
        stdin=PASSWORD,
    )
    async with client_for(app) as client:
        await login(client, "a@fund.example")
        assert (await client.get("/auth/me")).status_code == 200
        code, _ = await asyncio.to_thread(
            cli,
            "set-password",
            "--email",
            "a@fund.example",
            "--password-stdin",
            stdin="a new passphrase",
        )
        assert code == 0
        assert (await client.get("/auth/me")).status_code == 401
        assert (await login(client, "a@fund.example")).status_code == 401
        assert (await login(client, "a@fund.example", "a new passphrase")).status_code == 200
    assert len(list((await session.execute(select(AuthSession))).scalars())) == 1


def test_module_entry_point_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.auth.cli", "create-user", "--help"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--password-stdin" in result.stdout and "--workspace" in result.stdout
