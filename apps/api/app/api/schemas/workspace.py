"""`GET /workspace`: every case in the workspace with the slice of its record that the
screens spanning cases read (Overview, Pipeline, Signals, Approvals, Companies and the
app shell). Each field is the value `GET /cases/{id}` returns for the same case, cut
down to what those screens use; the full record stays at `GET /cases/{id}`."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.act.models import MessageStatus
from app.act.router import ApprovalOut, SendOut
from app.api.schemas.assessments import DiffLineOut, FitState
from app.api.schemas.cases import CaseSummary, EventOut
from app.api.schemas.common import (
    ApiModel,
    CriterionKind,
    CriterionResultState,
    Disposition,
    NamedUserOut,
    RunKind,
    RunState,
)


class ClaimCountsOut(ApiModel):
    """Claims by current status (`CaseDetail.claims[].status`, counted)."""

    supported: int = 0
    partially_corroborated: int = 0
    conflicting_evidence: int = 0
    contradicted: int = 0
    cannot_verify: int = 0
    not_checked: int = 0


class WorkspaceRunOut(ApiModel):
    """The case's latest run (`CaseDetail.case.run`), as a progress line needs it."""

    kind: RunKind
    state: RunState
    steps: int = Field(description="Steps in the run.")
    steps_finished: int = Field(description="Steps neither pending nor running.")


class WorkspaceCriterionOut(ApiModel):
    """One `CaseDetail.opportunity.criterion_results` row without its reason and evidence."""

    criterion_id: str
    label: str
    kind: CriterionKind
    weight: int
    state: CriterionResultState


class WorkspaceOpportunityOut(ApiModel):
    """`CaseDetail.opportunity` without the criteria definitions and relevance text."""

    thesis_id: str | None = None
    thesis_text: str | None = None
    fit_state: FitState
    fit: int | None = None
    assessable_pct: int = 0
    criterion_results: list[WorkspaceCriterionOut] = Field(default_factory=list)


class WorkspaceAssessmentOut(ApiModel):
    """The latest assessment version (`CaseDetail.assessment`): its disposition, its
    opportunity fit, and its diff from the previous version."""

    id: str
    version: int
    created_at: datetime
    disposition: Disposition = Field(description="judgments.screening_disposition.disposition")
    fit_state: FitState = Field(description="judgments.opportunity_fit.state")
    fit: int | None = Field(default=None, description="judgments.opportunity_fit.fit")
    assessable_pct: int = Field(default=0, description="judgments.opportunity_fit.assessable_pct")
    diff_from_previous: list[DiffLineOut] | None = None


class WorkspaceProfileOut(ApiModel):
    """The values of `CaseDetail.profile` a directory row shows (null without a profile)."""

    domain: str | None = None
    headquarters: str | None = None
    country: str | None = None
    headcount: int | None = None
    headcount_basis: str | None = None


class WorkspaceDocumentOut(ApiModel):
    """One `CaseDetail.documents` row, as a dated feed line needs it."""

    id: str
    filename: str
    uploaded_at: datetime
    uploaded_by_name: str | None = None
    purged: bool = False
    claims_extracted: int = 0


class WorkspaceRequestItemOut(ApiModel):
    document: str
    priority: int
    group: Literal["needed", "also_helpful"]


class WorkspaceRequestListOut(ApiModel):
    """`CaseDetail.request_list`: its items (priority order) and send mode."""

    items: list[WorkspaceRequestItemOut] = Field(default_factory=list)
    email_send_enabled: bool
    created_at: datetime


class WorkspaceRevisionOut(ApiModel):
    number: int
    recipient: str
    entered_by_user_id: str
    created_at: datetime


class WorkspaceMessageOut(ApiModel):
    """`CaseDetail.message` without its revision history and the text of the email."""

    status: MessageStatus
    current_revision: WorkspaceRevisionOut
    approval: ApprovalOut | None = None
    send: SendOut | None = None


class WorkspaceCaseOut(ApiModel):
    case_id: str
    owner: NamedUserOut = Field(description="CaseDetail.case.owner")
    run: WorkspaceRunOut | None = None
    identity_candidates: int = Field(default=0, description="len(CaseDetail.identity.candidates)")
    claim_counts: ClaimCountsOut = Field(default_factory=ClaimCountsOut)
    opportunity: WorkspaceOpportunityOut
    assessment: WorkspaceAssessmentOut | None = None
    profile: WorkspaceProfileOut | None = None
    events: list[EventOut] = Field(default_factory=list)
    documents: list[WorkspaceDocumentOut] = Field(default_factory=list)
    request_list: WorkspaceRequestListOut | None = None
    message: WorkspaceMessageOut | None = None


class WorkspaceOut(ApiModel):
    cases: list[CaseSummary] = Field(description="The rows of GET /cases, in the same order.")
    records: list[WorkspaceCaseOut] = Field(description="One per case, in the order of cases.")
