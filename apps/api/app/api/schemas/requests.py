"""Act contract, part 1: the request list and the drafted seller email (CP-23 / drafting).

Part 2, the message itself (immutable revisions, approval of one revision, send once,
reconcile), is the real router in `app.act.router`, mounted under
`/cases/{case_id}/messages`. Its `MessageOut` is reused in `CaseDetail.message`.
The UI flow: `POST /cases/{id}/requests` builds the list and a draft, then
`POST /cases/{id}/messages` turns the (possibly edited) draft into revision 1.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from app.api.schemas.common import ApiModel, ClaimCategory


class PriorityReason(StrEnum):
    """Why a requested document sits where it does (DecisionFlip, blocker-first)."""

    decision_blocker = "decision_blocker"
    disqualifier_risk = "disqualifier_risk"
    non_blocking = "non_blocking"
    analyst_retry = "analyst_retry"


class RequestItemOut(ApiModel):
    """One requested document, linked to every question it resolves (deduplicated).
    Items come blocker-first: the version's DecisionFlip minimum evidence, other
    decision blockers, disqualifier risks, then the rest; ties by estimated effort."""

    id: str
    document: str = Field(description='E.g. "Dated payroll summary".')
    reason: str
    categories: list[ClaimCategory] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    priority: int = Field(
        default=3,
        description="0 minimum evidence set, 1 other decision blocker, 2 disqualifier risk, "
        "3 non-blocking, 4 analyst re-run only. Lower comes first.",
    )
    priority_reason: PriorityReason = PriorityReason.non_blocking
    group: Literal["needed", "also_helpful"] = Field(
        default="also_helpful",
        description="Decision blockers are needed; everything else is also helpful.",
    )
    group_label: str = Field(
        default="Also helpful",
        description='"Needed to complete our screening" or "Also helpful", as in the email.',
    )


class AnalystRetryOut(ApiModel):
    """A check to re-run on our side (budget, provider error). Never sent to the seller."""

    claim_id: str | None = None
    label: str
    reason: str
    estimated_credits: float | None = None


class DraftEmailOut(ApiModel):
    """LLM draft built from the items. Contains no unverified facts. Editable."""

    subject: str
    body: str


class RequestListOut(ApiModel):
    id: str
    case_id: str
    assessment_version: int = Field(description="The assessment version the list was built on.")
    items: list[RequestItemOut]
    analyst_retries: list[AnalystRetryOut] = Field(default_factory=list)
    draft: DraftEmailOut
    message_id: str | None = Field(
        default=None, description="The Act message created from this draft, once there is one."
    )
    email_send_enabled: bool = Field(description="False means test mode: nothing leaves.")
    created_at: datetime
