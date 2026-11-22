"""Discover routes: thesis → criteria → search run → shortlist.

With `DEALPROOF_FIXTURES=1` every route serves the canned fixtures. Otherwise every
query is scoped to the signed-in user's workspace (`app/api/theses_deps.py`).
"""

import uuid

from fastapi import HTTPException, status

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.schemas.runs import RunOut
from app.api.schemas.theses import CriterionIn, ThesisCreate, ThesisOut, ThesisSummary
from app.api.theses_deps import ActorDep, LlmFactoryDep, SessionDep, SessionmakerDep
from app.api.theses_views import list_thesis_summaries, load_thesis_out
from app.clients.llm import LLMError
from app.db import repo
from app.extraction.llm import LlmOutputError
from app.jobs import events
from app.pipelines.discover import InvalidCriteria, SearchInProgress, replace_criteria
from app.pipelines.discover import create_thesis as create_thesis_row
from app.pipelines.discover import start_search as enqueue_search

router = make_router(prefix="/theses", tags=["discover"])


def _fixture_thesis(thesis_id: str) -> ThesisOut:
    if thesis_id != fixtures.THESIS_ID:
        not_found("Thesis")
    return fixtures.thesis()


def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        not_found("Thesis")


@router.post("", response_model=ThesisOut, status_code=status.HTTP_201_CREATED)
async def create_thesis(
    body: ThesisCreate,
    actor: ActorDep,
    session: SessionDep,
    sm: SessionmakerDep,
    make_llm: LlmFactoryDep,
) -> ThesisOut:
    """Create a thesis; criteria are extracted synchronously for review before searching."""
    if fixtures_enabled() or actor is None or session is None or sm is None:
        return fixtures.thesis_draft(body.text)
    try:
        thesis = await create_thesis_row(
            session,
            sm,
            actor.workspace_id,
            body.text,
            created_by=actor.user_id,
            llm_factory=make_llm,
        )
    except (LLMError, LlmOutputError) as exc:
        raise HTTPException(502, "Criteria extraction failed; try again.") from exc
    return await load_thesis_out(session, actor.workspace_id, thesis.id)


@router.get("", response_model=list[ThesisSummary])
async def list_theses(
    actor: ActorDep,
    session: SessionDep,
) -> list[ThesisSummary]:
    if fixtures_enabled() or actor is None or session is None:
        return fixtures.thesis_summaries()
    return await list_thesis_summaries(session, actor.workspace_id)


@router.get("/{thesis_id}", response_model=ThesisOut)
async def get_thesis(
    thesis_id: str,
    actor: ActorDep,
    session: SessionDep,
) -> ThesisOut:
    """The thesis with its criteria, latest run and shortlist (ranked, then excluded)."""
    if fixtures_enabled() or actor is None or session is None:
        return _fixture_thesis(thesis_id)
    try:
        return await load_thesis_out(session, actor.workspace_id, _uuid(thesis_id))
    except repo.NotFound:
        not_found("Thesis")


@router.put("/{thesis_id}/criteria", response_model=ThesisOut)
async def update_criteria(
    thesis_id: str,
    body: list[CriterionIn],
    actor: ActorDep,
    session: SessionDep,
) -> ThesisOut:
    """Replace the criteria. Edited criteria are marked `edited`."""
    if fixtures_enabled() or actor is None or session is None:
        return _fixture_thesis(thesis_id)
    tid = _uuid(thesis_id)
    try:
        await replace_criteria(session, actor.workspace_id, tid, body)
    except repo.NotFound:
        not_found("Thesis")
    except SearchInProgress as exc:
        raise HTTPException(409, str(exc)) from exc
    except InvalidCriteria as exc:
        raise HTTPException(422, str(exc)) from exc
    return await load_thesis_out(session, actor.workspace_id, tid)


@router.post("/{thesis_id}/search", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_search(
    thesis_id: str,
    actor: ActorDep,
    session: SessionDep,
) -> RunOut:
    """Start a discover run. Follow it with `GET /runs/{id}/events`."""
    if fixtures_enabled() or actor is None or session is None:
        run = _fixture_thesis(thesis_id).run
        assert run is not None
        return run
    try:
        run = await enqueue_search(
            session, actor.workspace_id, _uuid(thesis_id), created_by=actor.user_id
        )
    except repo.NotFound:
        not_found("Thesis")
    except SearchInProgress as exc:
        raise HTTPException(409, str(exc)) from exc
    except InvalidCriteria as exc:
        raise HTTPException(422, str(exc)) from exc
    return await events.load_run_out(session, actor.workspace_id, run.id)
