"""Act contract (CP-23): request list, immutable message revisions, approval, send once."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.api.schemas.common import ApiModel, ClaimCategory, NamedUserOut


class RequestStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    sending = "sending"
    sent = "sent"
    suppressed_test_mode = "suppressed_test_mode"
    failed = "failed"
    unknown = "unknown"


class RequestItemOut(ApiModel):
    """One requested document, linked to every question it resolves."""

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


class MessageRevisionOut(ApiModel):
    """Immutable. Any edit creates a new revision that needs fresh approval."""

    id: str
    number: int
    recipient_email: str | None = None
    subject: str
    body: str
    content_hash: str
    created_at: datetime
    created_by: NamedUserOut | None = Field(default=None, description="Null for the LLM draft.")


class ApprovalOut(ApiModel):
    revision_id: str
    approved_by: NamedUserOut
    approved_at: datetime


class SendOut(ApiModel):
    send_key: str = Field(
        description="Request id + approved revision id; provider idempotency key."
    )
    status: RequestStatus
    attempted_at: datetime
    sent_at: datetime | None = None
    provider_message_id: str | None = None
    error: str | None = None


class SellerRequestOut(ApiModel):
    id: str
    case_id: str
    assessment_version: int
    status: RequestStatus
    items: list[RequestItemOut]
    analyst_retries: list[AnalystRetryOut] = Field(default_factory=list)
    current_revision: MessageRevisionOut
    revisions: list[MessageRevisionOut] = Field(description="Oldest first.")
    approval: ApprovalOut | None = Field(
        default=None, description="Approval of current_revision; null after any edit."
    )
    send: SendOut | None = None
    email_send_enabled: bool = Field(description="False means test mode: nothing leaves.")
    created_at: datetime


class RequestUpdateIn(ApiModel):
    """Creates a new revision. Allowed only before sending."""

    recipient_email: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)


class RequestApproveIn(ApiModel):
    revision_id: str = Field(description="The exact revision the approver read.")
