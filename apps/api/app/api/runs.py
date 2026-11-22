"""Run routes: status, SSE progress and resume. Stubs until CP-11.

SSE wire format (`GET /runs/{id}/events`):

    event: step
    data: <StepOut JSON>

    event: run
    data: <RunOut JSON, steps omitted>

The stream ends after a `run` event whose state is `done` or `failed`. Clients fall back
to polling `GET /runs/{id}` every 2 s if the stream fails.
"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import status
from fastapi.responses import StreamingResponse

from app.api import fixtures
from app.api._base import (
    FIXTURE_HEADER,
    fixture_or_501,
    fixtures_enabled,
    make_router,
    not_found,
    not_implemented,
)
from app.api.schemas.common import RunState, StepState
from app.api.schemas.runs import RunEvent, RunOut, RunStreamEvent, StepEvent

OWNER = "CP-11"

router = make_router(prefix="/runs", tags=["runs"])

# Pause between fixture events; tests set it to 0.
FIXTURE_EVENT_DELAY_SECONDS = 0.25


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


def sse(event: StepEvent | RunEvent) -> str:
    return f"event: {event.event}\ndata: {event.data.model_dump_json()}\n\n"


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


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str) -> RunOut:
    """The run with every step. Polling fallback for the event stream."""
    return fixture_or_501(OWNER, lambda: _fixture_run(run_id))


@router.get(
    "/{run_id}/events",
    response_class=EventStreamResponse,
    response_model=None,
    responses={
        200: {
            "model": RunStreamEvent,
            "description": "Server-sent events: `event: step` (StepOut) and `event: run` "
            "(RunOut without steps). The JSON schema describes one event's name and data.",
        }
    },
)
def stream_run_events(run_id: str) -> EventStreamResponse:
    """Stream step and run changes as server-sent events until the run finishes."""
    if not fixtures_enabled():
        not_implemented(OWNER)
    run = _fixture_run(run_id)
    return EventStreamResponse(
        _fixture_events(run),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", FIXTURE_HEADER: "1"},
    )


@router.post("/{run_id}/resume", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def resume_run(run_id: str) -> RunOut:
    """Re-queue failed or interrupted steps. Cached calls replay at no new cost."""
    return fixture_or_501(OWNER, lambda: _fixture_run(run_id))
