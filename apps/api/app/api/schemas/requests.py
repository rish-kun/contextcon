"""Act contract, part 1: the request list and the drafted seller email (CP-23 / drafting).

Part 2, the message itself (immutable revisions, approval of one revision, send once,
reconcile), is the real router in `app.act.router`, mounted under
`/cases/{case_id}/messages`. Its `MessageOut` is reused in `CaseDetail.message`.
The UI flow: `POST /cases/{id}/requests` builds the list and a draft, then
`POST /cases/{id}/messages` turns the (possibly edited) draft into revision 1.
"""

from datetime import datetime

from pydantic import Field

from app.api.schemas.common import ApiModel, ClaimCategory


class RequestItemOut(ApiModel):
    """One requested document, linked to every question it resolves (deduplicated)."""

    id: str
    document: str = Field(description='E.g. "Dated payroll summary".')
    reason: str
    categories: list[ClaimCategory] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


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
