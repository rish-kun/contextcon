import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import ImmutableRowError, RequestList
from tests.db.factories import tenant

pytestmark = pytest.mark.asyncio


async def _version(session: AsyncSession, t, disposition: str = "investigate_further"):
    v = await repo.add_assessment_version(
        session,
        t.workspace.id,
        t.case.id,
        policy_version="policy-1",
        inputs_hash="h",
        judgments={"fit": 82},
        disposition=disposition,
        reasons=["fit 82"],
    )
    await session.commit()
    return v


async def test_assessment_versions_increment_and_keep_history(session: AsyncSession) -> None:
    t = await tenant(session)
    v1 = await _version(session, t)
    v2 = await _version(session, t, "prioritise")
    assert (v1.version, v2.version) == (1, 2)
    assert v2.previous_version_id == v1.id
    assert (await repo.latest_assessment(session, t.workspace.id, t.case.id)).id == v2.id


async def test_assessment_version_update_rejected_by_orm(session: AsyncSession) -> None:
    t = await tenant(session)
    v = await _version(session, t)
    v.disposition = "prioritise"
    with pytest.raises(ImmutableRowError):
        await session.flush()


async def test_assessment_version_update_rejected_by_database(session: AsyncSession) -> None:
    t = await tenant(session)
    v = await _version(session, t)
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(
            text("UPDATE assessment_versions SET disposition = 'prioritise' WHERE id = :id"),
            {"id": v.id},
        )


async def test_message_revision_update_rejected(session: AsyncSession) -> None:
    t = await tenant(session)
    rl = RequestList(case_id=t.case.id)
    session.add(rl)
    await session.commit()
    r1 = await repo.add_message_revision(
        session, t.workspace.id, rl.id, subject="s", body="b1", recipient="x@y.test"
    )
    r2 = await repo.add_message_revision(
        session, t.workspace.id, rl.id, subject="s", body="b2", recipient="x@y.test"
    )
    await session.commit()
    assert (r1.revision, r2.revision) == (1, 2)
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(
            text("UPDATE message_revisions SET body = 'edited' WHERE id = :id"), {"id": r1.id}
        )
    await session.rollback()
    r2.recipient = "other@y.test"
    with pytest.raises(ImmutableRowError):
        await session.flush()


async def _approved_revision(session: AsyncSession):
    t = await tenant(session)
    rl = RequestList(case_id=t.case.id)
    session.add(rl)
    await session.commit()
    rev = await repo.add_message_revision(
        session, t.workspace.id, rl.id, subject="s", body="b", recipient="x@y.test"
    )
    approval = await repo.approve_revision(session, t.workspace.id, rev.id, user_id=t.user.id)
    await session.commit()
    return t, rl, rev, approval


@pytest.mark.parametrize("table", ["approvals", "message_revisions", "assessment_versions"])
async def test_immutable_rows_cannot_be_deleted(session: AsyncSession, table: str) -> None:
    t, _, _, _ = await _approved_revision(session)
    await _version(session, t)
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(text(f"DELETE FROM {table}"))


async def test_deleting_a_case_does_not_cascade_into_immutable_rows(session: AsyncSession) -> None:
    t, _, _, _ = await _approved_revision(session)
    with pytest.raises(DBAPIError):
        await session.execute(text("DELETE FROM cases WHERE id = :id"), {"id": t.case.id})
    await session.rollback()
    assert (await session.execute(text("SELECT count(*) FROM approvals"))).scalar_one() == 1


async def test_retention_path_may_delete_immutable_rows(session: AsyncSession) -> None:
    from app.db.retention import allow_retention_delete

    _, _, rev, approval = await _approved_revision(session)
    await allow_retention_delete(session)
    await session.execute(text("DELETE FROM approvals WHERE id = :id"), {"id": approval.id})
    await session.execute(text("DELETE FROM message_revisions WHERE id = :id"), {"id": rev.id})
    await session.commit()
    # The opt-in ends with the transaction.
    t, _, _, _ = await _approved_revision(session)
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(text("DELETE FROM approvals"))
