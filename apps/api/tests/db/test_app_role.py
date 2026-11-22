"""The API's runtime role (scripts/db/app-role-grants.sql) can read and write rows and
nothing else. The `session` fixture already runs as that role, as every DB test does."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.retention import allow_retention_delete
from tests.db import pg
from tests.db.factories import tenant

pytestmark = pytest.mark.asyncio


async def test_tests_run_as_the_runtime_role(session: AsyncSession) -> None:
    role = (await session.execute(text("SELECT current_user"))).scalar_one()
    assert role == pg.shared_app_role()
    flags = (
        await session.execute(
            text(
                "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls"
                " FROM pg_roles WHERE rolname = current_user"
            )
        )
    ).one()
    assert tuple(flags) == (False, False, False, False)
    member_of = (
        await session.execute(
            text(
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member"
                " WHERE r.rolname = current_user"
            )
        )
    ).scalar_one()
    assert member_of == 0


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE app_role_probe (id int)",
        "ALTER TABLE cases ADD COLUMN probe int",
        "DROP TABLE api_cache",
        "TRUNCATE api_cache",
        "ALTER TABLE assessment_versions DISABLE TRIGGER USER",
        "CREATE INDEX probe_idx ON cases (id)",
        "UPDATE alembic_version SET version_num = version_num",
        "DELETE FROM alembic_version",
        "CREATE FUNCTION probe() RETURNS int LANGUAGE sql AS 'SELECT 1'",
    ],
)
async def test_runtime_role_cannot_change_schema(session: AsyncSession, sql: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied|must be owner"):
        await session.execute(text(sql))


async def test_runtime_role_reads_the_schema_version(session: AsyncSession) -> None:
    assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()


async def test_immutability_triggers_still_fire_for_the_runtime_role(
    session: AsyncSession,
) -> None:
    t = await tenant(session)
    v = await repo.add_assessment_version(
        session,
        t.workspace.id,
        t.case.id,
        policy_version="policy-1",
        inputs_hash="h",
        judgments={"fit": 82},
        disposition="investigate_further",
        reasons=["fit 82"],
    )
    await session.commit()
    version_id = v.id  # rollback() expires `v`
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(
            text("UPDATE assessment_versions SET disposition = 'prioritise' WHERE id = :id"),
            {"id": version_id},
        )
    await session.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(
            text("DELETE FROM assessment_versions WHERE id = :id"), {"id": version_id}
        )
    await session.rollback()

    # The retention path still works: the opt-in setting needs no extra privilege.
    await allow_retention_delete(session)
    result = await session.execute(
        text("DELETE FROM assessment_versions WHERE id = :id"), {"id": version_id}
    )
    assert result.rowcount == 1  # type: ignore[attr-defined]
    await session.commit()
