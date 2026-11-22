"""Act sections of `GET /cases/{id}`: the request list and the seller message.

Both read persisted state only (nothing is drafted or sent while a case is read):

* `request_list`: the latest request list built on an assessment version, with its
  items in priority order (`position`), the claims and questions each item resolves,
  the retries kept on our side, the first draft and whether sending is live or test.
* `message`: the Act message for that list (or, before there is one, the latest
  message of the case): the current revision, the approval of that revision with the
  approver's name and time, the latest send with its status and receipt (provider
  message id, test mode), and every revision.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.act.models import ActError
from app.act.pg_repository import PostgresActRepository
from app.act.router import MessageOut, _message_out
from app.act.service import ActService, SendConfig
from app.api.cases_sections import CaseContext, register_section
from app.api.requests import present
from app.api.schemas.requests import RequestListOut
from app.db.models import MessageRevision, RequestList
from app.db.session import make_sessionmaker
from app.pipelines.act.request_list import NoAssessment, load_request_list
from app.settings import get_settings


async def _latest_list(ctx: CaseContext) -> RequestList | None:
    return (
        await ctx.session.execute(
            select(RequestList)
            .where(
                RequestList.case_id == ctx.case.id,
                RequestList.assessment_version_id.is_not(None),
            )
            .order_by(RequestList.created_at.desc(), RequestList.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def request_list_section(ctx: CaseContext) -> RequestListOut | None:
    request_list = await _latest_list(ctx)
    if request_list is None:
        return None
    try:
        return present(await load_request_list(ctx.session, request_list))
    except NoAssessment:
        return None


async def _message_list(ctx: CaseContext) -> RequestList | None:
    """The message behind the latest request list, else the latest drafted message."""
    has_revision = exists().where(MessageRevision.request_list_id == RequestList.id)
    latest = await _latest_list(ctx)
    if latest is not None:
        found = await ctx.session.execute(
            select(RequestList.id).where(RequestList.id == latest.id, has_revision)
        )
        if found.first() is not None:
            return latest
    return (
        await ctx.session.execute(
            select(RequestList)
            .where(RequestList.case_id == ctx.case.id, has_revision)
            .order_by(RequestList.created_at.desc(), RequestList.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _read_service(session: AsyncSession) -> ActService:
    """A read-only Act service on the request's engine (no provider: nothing is sent)."""
    sessions = make_sessionmaker(session.bind)  # type: ignore[arg-type]
    config = SendConfig(enabled=get_settings().email_send_enabled)
    return ActService(PostgresActRepository(sessions), config, None)


async def message_section(ctx: CaseContext) -> MessageOut | None:
    request_list = await _message_list(ctx)
    if request_list is None:
        return None
    try:
        state = await _read_service(ctx.session).get_state(str(ctx.case.id), str(request_list.id))
    except ActError:
        return None
    return _message_out(state)


register_section("request_list", request_list_section)
register_section("message", message_section)
