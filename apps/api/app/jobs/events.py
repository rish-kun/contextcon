"""Run status endpoints: `GET /runs/{id}`, `GET /runs/{id}/events` (SSE), `POST /runs/{id}/resume`.

SSE works by polling the steps table (default every second), which behaves the same
on every instance and through Neon's pooled endpoint, where LISTEN/NOTIFY is not
available. Events:

    event: run    data: RunOut   (first, on every run state change, and last)
    event: step   data: StepOut  (each step whose state, attempts or error changed)

The stream ends after the run reaches `done` or `failed`.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import repo
from app.db.enums import RunState
from app.db.models import Run, Step
from app.db.session import get_session, get_sessionmaker
from app.jobs.engine import BUDGET_REACHED, resume_run

router = APIRouter(prefix="/runs", tags=["runs"])

POLL_SECONDS = 1.0
KEEPALIVE_EVERY = 15  # polls


async def current_workspace_id(request: Request) -> uuid.UUID:
    """The caller's workspace.

    Placeholder until auth lands: auth middleware should set
    `request.state.workspace_id` from the signed-in session (or override this
    dependency). Until then a `X-Workspace-Id` header is accepted, which is NOT a
    security boundary.
    """
    value = getattr(request.state, "workspace_id", None) or request.headers.get("x-workspace-id")
    if not value:
        raise HTTPException(status_code=401, detail="no workspace")
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="bad workspace id") from exc


def sessionmaker_dep() -> async_sessionmaker[AsyncSession]:
    return get_sessionmaker()


WorkspaceId = Annotated[uuid.UUID, Depends(current_workspace_id)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
SessionMaker = Annotated[async_sessionmaker[AsyncSession], Depends(sessionmaker_dep)]


class StepOut(BaseModel):
    id: uuid.UUID
    key: str
    handler: str
    position: int
    state: str
    attempts: int
    max_attempts: int
    depends_on: list[str]
    error: str | None
    skip_reason: str | None
    # What the UI shows for a step that did not run: "Not checked: budget reached".
    not_checked_reason: str | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    @classmethod
    def of(cls, step: Step) -> "StepOut":
        not_checked = None
        if step.state == "skipped_budget":
            not_checked = f"Not checked: {step.skip_reason or BUDGET_REACHED}"
        elif step.state == "failed":
            not_checked = "Not checked: the check could not be run"
        return cls(
            id=step.id,
            key=step.key,
            handler=step.handler,
            position=step.position,
            state=step.state,
            attempts=step.attempts,
            max_attempts=step.max_attempts,
            depends_on=list(step.depends_on or []),
            error=step.error,
            skip_reason=step.skip_reason,
            not_checked_reason=not_checked,
            started_at=step.started_at,
            finished_at=step.finished_at,
            updated_at=step.updated_at,
        )


class RunOut(BaseModel):
    id: uuid.UUID
    kind: str
    state: str
    case_id: uuid.UUID | None
    discovery_run_id: uuid.UUID | None
    investor_run_id: uuid.UUID | None
    budget_credits: Decimal | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    steps: list[StepOut]

    @classmethod
    def of(cls, run: Run) -> "RunOut":
        return cls(
            id=run.id,
            kind=run.kind,
            state=run.state,
            case_id=run.case_id,
            discovery_run_id=run.discovery_run_id,
            investor_run_id=run.investor_run_id,
            budget_credits=run.budget_credits,
            error=run.error,
            created_at=run.created_at,
            finished_at=run.finished_at,
            steps=[StepOut.of(s) for s in run.steps],
        )


async def _load(session: AsyncSession, workspace_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    try:
        return await repo.get_run(session, workspace_id, run_id)
    except repo.NotFound as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@router.get("/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID,
    workspace_id: WorkspaceId,
    session: DbSession,
) -> RunOut:
    return RunOut.of(await _load(session, workspace_id, run_id))


@router.post("/{run_id}/resume", response_model=RunOut)
async def resume(
    run_id: uuid.UUID,
    workspace_id: WorkspaceId,
    session: DbSession,
) -> RunOut:
    run = await _load(session, workspace_id, run_id)
    await resume_run(session, run.id)
    await session.commit()
    session.expunge_all()
    return RunOut.of(await _load(session, workspace_id, run_id))


def _sse(event: str, data: BaseModel | dict[str, Any]) -> str:
    payload = data.model_dump_json() if isinstance(data, BaseModel) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_run_events(
    sessionmaker: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    poll_seconds: float | None = None,
    is_disconnected: Any = None,
) -> AsyncIterator[str]:
    poll = poll_seconds if poll_seconds is not None else POLL_SECONDS
    seen: dict[uuid.UUID, tuple] = {}
    last_run_state: str | None = None
    polls = 0
    while True:
        async with sessionmaker() as session:
            run = await repo.get_run(session, workspace_id, run_id)
            out = RunOut.of(run)
        for step in out.steps:
            signature = (step.state, step.attempts, step.error, step.skip_reason)
            if seen.get(step.id) != signature:
                seen[step.id] = signature
                if last_run_state is not None:
                    yield _sse("step", step)
        if out.state != last_run_state:
            last_run_state = out.state
            yield _sse("run", out)
        if out.state in (RunState.DONE, RunState.FAILED):
            return
        polls += 1
        if polls % KEEPALIVE_EVERY == 0:
            yield ": keepalive\n\n"
        if is_disconnected is not None and await is_disconnected():
            return
        await asyncio.sleep(poll)


@router.get("/{run_id}/events")
async def run_events(
    run_id: uuid.UUID,
    request: Request,
    workspace_id: WorkspaceId,
    sessionmaker: SessionMaker,
) -> StreamingResponse:
    async with sessionmaker() as session:
        await _load(session, workspace_id, run_id)  # 404 before the stream starts
    return StreamingResponse(
        stream_run_events(
            sessionmaker, workspace_id, run_id, is_disconnected=request.is_disconnected
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
