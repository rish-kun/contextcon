"""Runs and steps (filled by CP-11). Streamed over SSE from `GET /runs/{id}/events`."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

from app.api.schemas.common import (
    ApiModel,
    ClaimStatus,
    CostTotalsOut,
    Disposition,
    RunKind,
    RunState,
    SourceClass,
    StepState,
)


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


# --- Live activity (docs/design/iterations/D-live-run-experience.md §2) ----------------


Day = date  # a field named `date` shadows the type inside its class


class ActivityKind(StrEnum):
    status = "status"
    call = "call"
    source = "source"
    model = "model"
    finding = "finding"
    notice = "notice"


class ActivitySubject(StrEnum):
    company = "company"
    claim = "claim"
    investor = "investor"
    round = "round"
    identity = "identity"
    event = "event"
    peer = "peer"
    assessment = "assessment"
    request_list = "request_list"


class NoticeCode(StrEnum):
    search_widened = "search_widened"
    budget_low = "budget_low"
    budget_reached = "budget_reached"
    step_resumed = "step_resumed"
    served_from_cache = "served_from_cache"
    call_retried = "call_retried"
    source_limit = "source_limit"
    identity_blocked = "identity_blocked"
    nothing_to_check = "nothing_to_check"
    activity_limit = "activity_limit"


class ProgressOut(ApiModel):
    done: int
    total: int


class SourceRefOut(ApiModel):
    """A public page or a Crustdata record. Never an uploaded document's content: a
    `seller_document` carries only its kind in words as `title`."""

    type: Literal["web_page", "crustdata_record", "seller_document"]
    domain: str | None = Field(default=None, description="Lower-case host; null for non-web.")
    url: str | None = Field(
        default=None, description="Tracking parameters stripped; null if it carried a token."
    )
    title: str | None = Field(default=None, description="≤ 140 chars.")
    source_class: SourceClass | None = None
    as_of: date | None = Field(default=None, description="Date of the fact; null: no date.")
    state: Literal["read", "failed", "skipped"] = "read"
    reason: Literal["http_403", "timeout", "robots", "empty", "too_large", "budget"] | None = None


class CallInfoOut(ApiModel):
    """One external call, final state only (emitted when it returns)."""

    provider: Literal["crustdata", "anthropic"]
    endpoint: Literal[
        "company_identify",
        "company_search",
        "company_enrich",
        "person_search",
        "job_search",
        "web_search",
        "web_fetch",
        "messages",
    ]
    ok: bool
    error: str | None = Field(default=None, description="Allowlisted code when ok is false.")
    from_cache: bool = False
    attempts: int = Field(default=1, description="HTTP dispatches; > 1 means it was retried.")
    duration_ms: int | None = None
    credits: float | None = Field(
        default=None, description="This call. 0 on a cache hit; null when not reported."
    )
    usd: float | None = Field(default=None, description="Model calls only.")
    credits_total: float = Field(default=0, description="Run total after this call.")
    usd_total: float = Field(default=0, description="Run total after this call.")


class ActivityRefOut(ApiModel):
    type: Literal["claim", "company", "investor", "document"]
    id: str


CompanyMark = Literal["pending", "found", "none", "not_checked"]


class CompanyItemOut(ApiModel):
    """`subject: company` (and `peer`). Later stages send only the rows that changed."""

    id: str = Field(description="Crustdata company id: stable across every stage.")
    stage: Literal["found", "dropped", "enriching", "enriched", "scored", "explained"]
    name: str | None = None
    domain: str | None = None
    location: str | None = None
    headcount: int | None = None
    headcount_is_estimate: bool | None = None
    reason: str | None = None
    marks: dict[str, CompanyMark] | None = None
    highlight: str | None = None
    fit: float | None = None
    assessable: float | None = None
    rank: int | None = None


class ClaimItemOut(ApiModel):
    """`subject: claim`. No claim text: `category` is the only description."""

    id: str
    stage: Literal["queued", "checking", "settled", "not_checked"]
    category: str
    status: ClaimStatus | None = None
    previous_status: ClaimStatus | None = None
    evidence_count: int | None = None
    snippet: str | None = Field(
        default=None, description="≤ 200 chars, only from a web page or Crustdata record."
    )
    gap: str | None = Field(default=None, description="The rule's canned sentence.")


class IdentityItemOut(ApiModel):
    id: str
    stage: Literal["confirmed", "ambiguous", "unresolved"]
    name: str | None = None
    domain: str | None = None
    matched_keys: list[str] = Field(default_factory=list)


class RoundInvestorOut(ApiModel):
    key: str
    name: str


class RoundItemOut(ApiModel):
    id: str
    stage: Literal["found"] = "found"
    company: str | None = None
    company_id: str | None = None
    round: str | None = None
    date: Day | None = Field(default=None, description="Null: undated, cannot be ranked on.")
    amount_usd: float | None = None
    investors: list[RoundInvestorOut] = Field(default_factory=list)


class InvestorItemOut(ApiModel):
    id: str
    stage: Literal["found", "ranked"]
    name: str
    rank: int | None = None
    comparable_rounds: int = 0
    last_round_date: date | None = None


class EventItemOut(ApiModel):
    id: str
    stage: Literal["found"] = "found"
    date: Day | None = None
    event_kind: str
    title: str | None = Field(default=None, description="Event kind in words + the domain.")
    domain: str | None = None


class AssessmentItemOut(ApiModel):
    id: str
    stage: Literal["written"] = "written"
    version: int
    disposition: Disposition
    previous_disposition: Disposition | None = None
    fit: float | None = None
    assessable: float | None = None


class RequestListItemOut(ApiModel):
    id: str
    stage: Literal["drafted", "nothing_to_request"]


def _item_tag(value: Any) -> str:
    """Which item model a preview item is (items carry no type field; `subject` does)."""
    if isinstance(value, BaseModel):
        return _ITEM_TAGS[type(value)]
    keys = set(value) if isinstance(value, dict) else set()
    for key, tag in (
        ("category", "claim"),
        ("matched_keys", "identity"),
        ("round", "round"),
        ("comparable_rounds", "investor"),
        ("event_kind", "event"),
        ("disposition", "assessment"),
        ("name", "company"),
    ):
        if key in keys:
            return tag
    return "request_list"


ActivityItem = Annotated[
    Annotated[CompanyItemOut, Tag("company")]
    | Annotated[ClaimItemOut, Tag("claim")]
    | Annotated[IdentityItemOut, Tag("identity")]
    | Annotated[RoundItemOut, Tag("round")]
    | Annotated[InvestorItemOut, Tag("investor")]
    | Annotated[EventItemOut, Tag("event")]
    | Annotated[AssessmentItemOut, Tag("assessment")]
    | Annotated[RequestListItemOut, Tag("request_list")],
    Discriminator(_item_tag),
]
_ITEM_TAGS: dict[type, str] = {
    CompanyItemOut: "company",
    ClaimItemOut: "claim",
    IdentityItemOut: "identity",
    RoundItemOut: "round",
    InvestorItemOut: "investor",
    EventItemOut: "event",
    AssessmentItemOut: "assessment",
    RequestListItemOut: "request_list",
}


class ActivityOut(ApiModel):
    """One thing the run did. Append-only per run; `seq` is also the SSE `id:`.

    Public data and the user's own criteria only (never claim text, document text or
    filenames, prompts, model output, case-run search queries or contact details).
    Fields a kind does not use are null."""

    seq: int = Field(description="Per run, strictly increasing from 1.")
    run_id: str
    step_id: str | None = None
    step_key: str | None = None
    kind: ActivityKind
    at: datetime = Field(description="When it happened (UTC, ms), not when it was sent.")
    label: str = Field(description="≤ 120 chars, from a template.")
    detail: str | None = Field(default=None, description="≤ 200 chars.")
    progress: ProgressOut | None = Field(
        default=None, description="Only when both numbers are real."
    )
    source: SourceRefOut | None = None
    call: CallInfoOut | None = None
    counts: dict[str, int] | None = Field(
        default=None, description="Keys fixed per kind and endpoint."
    )
    highlights: list[str] | None = Field(default=None, description="≤ 2, each ≤ 100 chars.")
    items: list[ActivityItem] | None = Field(default=None, description="≤ 8, typed by subject.")
    subject: ActivitySubject | None = None
    code: NoticeCode | None = None
    ref: ActivityRefOut | None = Field(default=None, description="The row this is about.")


class ActivitySummaryOut(ApiModel):
    """Run totals over every activity so far (credits and USD are the cost ledger's)."""

    by_kind: dict[str, int] = Field(default_factory=dict)
    crustdata_calls: int = 0
    records_returned: int = 0
    sources_read: int = 0
    sources_failed: int = 0
    domains: int = 0
    companies_found: int = 0
    investors_found: int = 0
    claims_settled: int = 0
    credits: float = 0
    llm_usd: float = 0
    elapsed_seconds: float = 0
    last_seq: int = 0


class ActivityPage(ApiModel):
    items: list[ActivityOut]
    next_after: int | None = Field(
        default=None, description="Pass as `after` for the next page; null at the end."
    )
    summary: ActivitySummaryOut = Field(default_factory=ActivitySummaryOut)


class ActivityEvent(ApiModel):
    """SSE `event: activity`, with `id: {seq}`."""

    event: Literal["activity"] = "activity"
    data: ActivityOut


RunStreamEvent = StepEvent | RunEvent | ActivityEvent
