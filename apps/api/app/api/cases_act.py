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


class _RequestSession:
    """Stands in for a sessionmaker: `async with sm() as s` yields the request's own
    session and leaves it open. The repository's read methods then share the request's
    connection instead of checking out one connection (and transaction) each."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> _RequestSession:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


def _read_service(session: AsyncSession) -> ActService:
    """A read-only Act service on the request's session (no provider: nothing is sent).
    Only `get_state` is called on it, which reads; nothing here begins a transaction."""
    config = SendConfig(enabled=get_settings().email_send_enabled)
    return ActService(PostgresActRepository(_RequestSession(session)), config, None)  # type: ignore[arg-type]


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
