import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.enums import SendStatus
from app.db.models import RequestList
from tests.db.factories import tenant

pytestmark = pytest.mark.asyncio


async def _approved(session: AsyncSession):
    t = await tenant(session)
    rl = RequestList(case_id=t.case.id)
    session.add(rl)
    await session.commit()
    rev = await repo.add_message_revision(
        session, t.workspace.id, rl.id, subject="s", body="b", recipient="cfo@seller.test"
    )
    approval = await repo.approve_revision(session, t.workspace.id, rev.id, user_id=t.user.id)
    await session.commit()
    return t, rl, approval


async def test_second_send_with_same_key_is_refused(session: AsyncSession) -> None:
    t, rl, approval = await _approved(session)
    key = f"request-list:{rl.id}"
    attempt = await repo.begin_send(session, t.workspace.id, approval_id=approval.id, send_key=key)
    await repo.finish_send(session, attempt.id, status=SendStatus.SUPPRESSED_TEST_MODE)
    await session.commit()
    with pytest.raises(repo.AlreadySent) as info:
        await repo.begin_send(session, t.workspace.id, approval_id=approval.id, send_key=key)
    assert info.value.attempt.status == "suppressed_test_mode"


async def test_send_key_unique_in_database(session: AsyncSession) -> None:
    t, rl, approval = await _approved(session)
    insert = text(
        "INSERT INTO send_attempts"
        " (id, message_revision_id, approval_id, send_key, status, provider) "
        "VALUES (:id, :rev, :ap, 'k1', 'pending', 'resend')"
    )
    params = {"rev": approval.message_revision_id, "ap": approval.id}
    await session.execute(insert, {**params, "id": uuid.uuid4()})
    with pytest.raises(IntegrityError):
        await session.execute(insert, {**params, "id": uuid.uuid4()})


async def test_finished_attempt_cannot_be_reused(session: AsyncSession) -> None:
    t, rl, approval = await _approved(session)
    attempt = await repo.begin_send(session, t.workspace.id, approval_id=approval.id, send_key="k")
    await repo.finish_send(session, attempt.id, status="sent", provider_message_id="msg_1")
    await session.commit()
    with pytest.raises(repo.AlreadySent):
        await repo.finish_send(session, attempt.id, status="sent")


async def test_send_needs_approval_in_same_workspace(session: AsyncSession) -> None:
    t, rl, approval = await _approved(session)
    other = await tenant(session, "other")
    with pytest.raises(repo.NotFound):
        await repo.begin_send(session, other.workspace.id, approval_id=approval.id, send_key="k")
