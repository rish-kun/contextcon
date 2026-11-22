"""Runs and steps (filled by CP-11). Streamed over SSE from `GET /runs/{id}/events`."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.api.schemas.common import ApiModel, CostTotalsOut, RunKind, RunState, StepState


class StepOut(ApiModel):
    id: str
    run_id: str
    key: str = Field(
        description='Stable step key, e.g. "verify.identity" or "evidence.claim:<id>".'
    )
    label: str = Field(description="Human label for the progress list.")
    position: int
    state: StepState
    attempts: int = 0
    detail: str | None = Field(default=None, description="Live sub-line while running.")
    result: str | None = Field(default=None, description="One-line result when done.")
    error: str | None = None
    from_cache: bool = Field(default=False, description="Replayed from the request cache.")
    cost: CostTotalsOut = Field(default_factory=CostTotalsOut)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunOut(ApiModel):
    id: str
    kind: RunKind
    state: RunState
    subject: str = Field(description="What the run is about: a company name or thesis text.")
    case_id: str | None = None
    thesis_id: str | None = None
    investor_search_id: str | None = None
    budget_credits: float
    cost: CostTotalsOut = Field(default_factory=CostTotalsOut)
    checks_not_run: int = Field(default=0, description="Checks skipped (become not_checked).")
    created_at: datetime
    finished_at: datetime | None = None
    resumed_at: datetime | None = Field(
        default=None, description="Set when the run picked up after an interruption."
    )
    error: str | None = None
    steps: list[StepOut] = Field(default_factory=list)


class RunSummaryOut(ApiModel):
    id: str
    kind: RunKind
    state: RunState
    created_at: datetime
    finished_at: datetime | None = None
    cost: CostTotalsOut = Field(default_factory=CostTotalsOut)


class StepEvent(ApiModel):
    """SSE `event: step`; data is the changed step."""

    event: Literal["step"] = "step"
    data: StepOut


class RunEvent(ApiModel):
    """SSE `event: run`; data is the run without steps. Sent on every run state change."""

    event: Literal["run"] = "run"
    data: RunOut


RunStreamEvent = StepEvent | RunEvent
