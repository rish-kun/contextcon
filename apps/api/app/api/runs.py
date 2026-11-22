"""Run routes: status, SSE progress and resume, scoped to the signed-in user's workspace.

SSE wire format (`GET /runs/{id}/events`):

    event: run
    data: <RunOut JSON, steps omitted>

    event: step
    data: <StepOut JSON>

The stream starts with a `run` event, sends a `step` event per step and per change, may
send `: keepalive` comments, and ends after a `run` event whose state is `done` or
`failed`. Clients fall back to polling `GET /runs/{id}` every 2 s if the stream fails.
Errors (401, 404) are returned as JSON before the stream starts.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import Request, status
from fastapi.responses import StreamingResponse

from app.api import fixtures
from app.api._base import (
    COMMON_RESPONSES,
    FIXTURE_HEADER,
    fixtures_enabled,
    make_router,
    not_found,
)
from app.api.schemas.common import RunState, StepState
from app.api.schemas.runs import RunEvent, RunOut, StepEvent
from app.auth.deps import WorkspaceId
from app.db import repo
from app.db.session import get_sessionmaker
from app.jobs import events

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


async def _fixture_events(run: RunOut) -> AsyncIterator[str]:
    """Replay a fixture run as if it were happening now."""
    yield sse(RunEvent(data=run.model_copy(update={"state": RunState.running, "steps": []})))
    for step in run.steps:
        await asyncio.sleep(FIXTURE_EVENT_DELAY_SECONDS)
        running = step.model_copy(update={"state": StepState.running, "result": None})
        yield sse(StepEvent(data=running))
        await asyncio.sleep(FIXTURE_EVENT_DELAY_SECONDS)
        yield sse(StepEvent(data=step))
    yield sse(RunEvent(data=run.model_copy(update={"steps": []})))


async def _load(workspace_id: uuid.UUID, run_id: str) -> RunOut:
    async with get_sessionmaker()() as db:
        try:
            return await events.load_run_out(db, workspace_id, _run_id(run_id))
        except repo.NotFound:
            not_found("Run")


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
    "run state change, and last once the run is `done` or `failed`); `event: step` carries "
    "a StepOut (every step once, then each change). Lines starting with `:` are keepalives."
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
    run_id: str, request: Request, workspace_id: WorkspaceId
) -> EventStreamResponse:
    """Stream step and run changes as server-sent events until the run finishes."""
    if fixtures_enabled():
        run = _fixture_run(run_id)
        return EventStreamResponse(
            _fixture_events(run), headers={**SSE_HEADERS, FIXTURE_HEADER: "1"}
        )
    await _load(workspace_id, run_id)  # 404 before the stream starts
    stream = events.run_event_stream(
        get_sessionmaker(),
        workspace_id,
        _run_id(run_id),
        is_disconnected=request.is_disconnected,
    )
    return EventStreamResponse(stream, headers=SSE_HEADERS)


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
