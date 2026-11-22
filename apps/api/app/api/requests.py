"""Act, part 1: the request list and drafted seller email (CP-23).

`POST /cases/{id}/requests` builds the request list from the case's latest assessment
version and drafts one consolidated seller email as revision 1 of the Act message
(`message_id` is the request list's id). Asking again for the same assessment version
returns the stored list. `GET` returns the latest list. Both need a signed-in user
whose workspace owns the case (404 otherwise); before the first assessment, `POST`
answers 409.

Message revisions, approval and send-once live in `app.act.router`, mounted by
`app.api.router` under `/cases/{case_id}/messages`. Fixture mode
(`DEALPROOF_FIXTURES=1`) serves the fixture list.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.schemas.requests import (
    AnalystRetryOut,
    DraftEmailOut,
    PriorityReason,
    RequestItemOut,
    RequestListOut,
)
from app.auth.deps import CurrentUser
from app.db import repo
from app.db.ledger import CostContext
from app.db.session import get_session, make_sessionmaker
from app.pipelines.act import llm as llm_module
from app.pipelines.act.request_list import (
    NoAssessment,
    StoredRequestList,
    build_request_list_for_case,
    latest_request_list,
    load_request_list,
)
from app.settings import get_settings

router = make_router(prefix="/cases/{case_id}/requests", tags=["act"])


async def requests_session() -> AsyncIterator[AsyncSession | None]:
    if fixtures_enabled():
        yield None
        return
    async for session in get_session():
        yield session


Session = Annotated[AsyncSession | None, Depends(requests_session)]


def _fixture(case_id: str) -> RequestListOut:
    if case_id != fixtures.CASE_ID:
        not_found("Request list")
    return fixtures.request_list()


def _case_uuid(case_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(case_id)
    except ValueError:
        not_found("Case")


def _humanise(value: str | None) -> str:
    text = (value or "not checked").replace("_", " ")
    return text[0].upper() + text[1:]


def present(stored: StoredRequestList) -> RequestListOut:
    rl = stored.request_list
    first = stored.first_revision
    return RequestListOut(
        id=str(rl.id),
        case_id=str(rl.case_id),
        assessment_version=stored.version.version,
        items=[
            RequestItemOut(
                id=str(row.id),
                document=view.document,
                reason=view.reason,
                categories=view.categories,
                claim_ids=view.claim_ids,
                questions=view.questions,
                priority=view.priority,
                priority_reason=PriorityReason(view.priority_reason.value),
                group="needed" if view.needed else "also_helpful",
                group_label=view.group,
            )
            for row, view in stored.items
        ],
        analyst_retries=[
            AnalystRetryOut(
                claim_id=claim_id,
                label=f"Check: {text}" if text else "Check this claim again",
                reason=_humanise(reason.value if reason else None),
            )
            for claim_id, reason, _detail, text in stored.retries
        ],
        draft=DraftEmailOut(
            subject=first.subject if first else "", body=first.body if first else ""
        ),
        message_id=str(rl.id) if first else None,
        email_send_enabled=get_settings().email_send_enabled,
        created_at=rl.created_at,
    )


@router.post("", response_model=RequestListOut, status_code=status.HTTP_201_CREATED)
async def create_request_list(case_id: str, user: CurrentUser, session: Session) -> RequestListOut:
    """Build the request list from the latest assessment and draft one consolidated email."""
    if fixtures_enabled() or session is None:
        return _fixture(case_id)
    cid = _case_uuid(case_id)
    try:
        await repo.get_case(session, user.workspace_id, cid)
    except repo.NotFound:
        not_found("Case")
    cost = CostContext(workspace_id=user.workspace_id, case_id=cid)
    try:
        # Cost and cache rows commit on their own sessions, on the request's engine.
        sessions = make_sessionmaker(session.bind)  # type: ignore[arg-type]
        async with llm_module.llm_factory(sessions, cost, None) as llm:
            built = await build_request_list_for_case(
                session, user.workspace_id, cid, llm=llm, sender_name=user.display_name
            )
    except NoAssessment as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return present(await load_request_list(session, built.request_list))


@router.get("", response_model=RequestListOut)
async def get_request_list(case_id: str, user: CurrentUser, session: Session) -> RequestListOut:
    """The latest request list for the case."""
    if fixtures_enabled() or session is None:
        return _fixture(case_id)
    try:
        request_list = await latest_request_list(session, user.workspace_id, _case_uuid(case_id))
    except repo.NotFound:
        not_found("Case")
    if request_list is None:
        not_found("Request list")
    return present(await load_request_list(session, request_list))
