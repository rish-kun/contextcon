"""Run routes: status, SSE progress, the activity log and resume, scoped to the signed-in
user's workspace.

SSE wire format (`GET /runs/{id}/events`):

    event: run
    data: <RunOut JSON, steps omitted>

    event: step
    data: <StepOut JSON>

    id: <seq>
    event: activity
    data: <ActivityOut JSON>

The stream starts with a `run` event and a `step` event per step, then the activity
backlog (after `Last-Event-ID` or `?after=`, else from the start), then a `: live`
comment; after that a `step` event per change, each new `activity`, a `run` event on
every state or cost change, `: keepalive` comments, and it ends after a `run` event whose
state is `done` or `failed`. Clients fall back to polling `GET /runs/{id}` and
`GET /runs/{id}/activity?after=<last seq>` every 2 s if the stream fails. Errors (401,
404) are returned as JSON before the stream starts.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Header, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api import fixture_activity, fixtures
from app.api._base import (
    COMMON_RESPONSES,
    FIXTURE_HEADER,
    fixtures_enabled,
    make_router,
    not_found,
)
from app.api.schemas.common import RunState, StepState
from app.api.schemas.runs import (
    ActivityOut,
    ActivityPage,
    RunEvent,
    RunOut,
    RunQueueOut,
    RunQueueStatus,
    StepEvent,
)
from app.auth.deps import WorkspaceId
from app.db import repo
from app.db.session import get_sessionmaker
from app.jobs import events, queue

router = make_router(prefix="/runs", tags=["runs"])

# Pause between fixture events; tests set it to 0.
FIXTURE_EVENT_DELAY_SECONDS = 0.25

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


def sse(event: StepEvent | RunEvent) -> str:
    return f"event: {event.event}\ndata: {event.data.model_dump_json()}\n\n"


def _run_id(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except ValueError:
        not_found("Run")


def _fixture_run(run_id: str) -> RunOut:
    run = fixtures.runs().get(run_id)
    if run is None:
        not_found("Run")
    return run


async def _fixture_events(run: RunOut, after: int = 0) -> AsyncIterator[str]:
    """Replay a fixture run as if it were happening now: each step goes running → done
    with its recorded activities in between, spaced like the real run but never more
    than `FIXTURE_EVENT_DELAY_SECONDS` apart."""
    activities = [a for a in fixture_activity.activities(run.id) if a.seq > after]
    by_step: dict[str | None, list[ActivityOut]] = {}
    for activity in activities:
        by_step.setdefault(activity.step_id, []).append(activity)
    yield sse(RunEvent(data=run.model_copy(update={"state": RunState.running, "steps": []})))
    yield events.LIVE_MARKER
    for activity in by_step.pop(None, []):
        yield events.activity_frame(activity)
    for step in run.steps:
        await asyncio.sleep(FIXTURE_EVENT_DELAY_SECONDS)
        running = step.model_copy(update={"state": StepState.running, "result": None})
        yield sse(StepEvent(data=running))
        for activity in by_step.pop(step.id, []):
            await asyncio.sleep(FIXTURE_EVENT_DELAY_SECONDS / 2)
            yield events.activity_frame(activity)
        await asyncio.sleep(FIXTURE_EVENT_DELAY_SECONDS)
        yield sse(StepEvent(data=step))
    for rest in by_step.values():
        for activity in rest:
            yield events.activity_frame(activity)
    yield sse(RunEvent(data=run.model_copy(update={"steps": []})))
    yield events.END_FRAME


async def _load(workspace_id: uuid.UUID, run_id: str) -> RunOut:
    async with get_sessionmaker()() as db:
        try:
            return await events.load_run_out(db, workspace_id, _run_id(run_id))
        except repo.NotFound:
            not_found("Run")


@router.get("", response_model=RunQueueOut)
async def list_runs(
    workspace_id: WorkspaceId,
    status: Annotated[
        RunQueueStatus,
        Query(description="`active`: pending or running, oldest first. `recent`: latest runs."),
    ] = RunQueueStatus.active,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RunQueueOut:
    """The workspace's jobs: what is queued or working now, or the latest runs. Each row
    says which thesis, case or investor search it belongs to, how far it has got and what
    it has spent so far (the same totals the run's own page shows)."""
    if fixtures_enabled():
        return fixtures.run_queue(status, limit)
    async with get_sessionmaker()() as db:
        return await queue.list_run_queue(db, workspace_id, status=status, limit=limit)


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, workspace_id: WorkspaceId) -> RunOut:
    """The run with every step. Polling fallback for the event stream."""
    if fixtures_enabled():
        return _fixture_run(run_id)
    return await _load(workspace_id, run_id)


def _json_error(code: int) -> dict:
    """An error response documented as JSON (the route's own media type is SSE)."""
    return {
        "description": COMMON_RESPONSES[code]["description"],
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorOut"}}},
    }


_SSE_DESCRIPTION = (
    "Server-sent events. `event: run` carries a RunOut without steps (first, on every "
    "run state or cost change, and last once the run is `done` or `failed`); `event: step` "
    "carries a StepOut (every step once, then each change); `event: activity` carries an "
    "ActivityOut with `id: <seq>` (the backlog after `Last-Event-ID` or `?after=`, then a "
    "`: live` comment, then each new one). Once the run is finished and every activity has "
    "been sent, `event: end` (data `{}`) is the last frame: clients close on it, not on a "
    "finished `run`, which a reconnect sends before the backlog. Other lines starting "
    "with `:` are keepalives."
)


@router.get(
    "/{run_id}/events",
    response_class=EventStreamResponse,
    response_model=None,
    responses={
        200: {
            "description": _SSE_DESCRIPTION,
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "x-sse-events": {
                        "run": {"$ref": "#/components/schemas/RunOut"},
                        "step": {"$ref": "#/components/schemas/StepOut"},
                        "activity": {"$ref": "#/components/schemas/ActivityOut"},
                    },
                }
            },
        },
        401: _json_error(401),
        404: _json_error(404),
        501: _json_error(501),
    },
)
async def stream_run_events(
    run_id: str,
    request: Request,
    workspace_id: WorkspaceId,
    after: int | None = Query(
        default=None, ge=0, description="Resume after this activity seq (or `Last-Event-ID`)."
    ),
    last_event_id: str | None = Header(default=None, include_in_schema=False),
) -> EventStreamResponse:
    """Stream step, run and activity changes as server-sent events until the run finishes."""
    if after is None and last_event_id and last_event_id.strip().isdigit():
        after = int(last_event_id.strip())
    if fixtures_enabled():
        run = _fixture_run(run_id)
        return EventStreamResponse(
            _fixture_events(run, after or 0), headers={**SSE_HEADERS, FIXTURE_HEADER: "1"}
        )
    await _load(workspace_id, run_id)  # 404 before the stream starts
    stream = events.run_event_stream(
        get_sessionmaker(),
        workspace_id,
        _run_id(run_id),
        after=after,
        is_disconnected=request.is_disconnected,
    )
    return EventStreamResponse(stream, headers=SSE_HEADERS)


@router.get("/{run_id}/activity", response_model=ActivityPage)
async def list_run_activity(
    run_id: str,
    workspace_id: WorkspaceId,
    after: int = Query(default=0, ge=0, description="Return activities with seq > after."),
    limit: int = Query(default=500, ge=1, le=2000),
) -> ActivityPage:
    """The run's activity log, in seq order, with run totals. For the run log, a reload
    mid-run, and the polling fallback (every 2 s with the last seq)."""
    if fixtures_enabled():
        _fixture_run(run_id)
        return fixture_activity.page(run_id, after=after, limit=limit)
    async with get_sessionmaker()() as db:
        try:
            return await events.load_activity_page(
                db, workspace_id, _run_id(run_id), after=after, limit=limit
            )
        except repo.NotFound:
            not_found("Run")


@router.post("/{run_id}/resume", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def resume_run(run_id: str, workspace_id: WorkspaceId) -> RunOut:
    """Re-queue failed or budget-skipped steps. Cached calls replay at no new cost."""
    if fixtures_enabled():
        return _fixture_run(run_id)
    async with get_sessionmaker()() as db:
        try:
            return await events.resume_run_out(db, workspace_id, _run_id(run_id))
        except repo.NotFound:
            not_found("Run")
