"""Case contract (CP-19 create/identity/verify, CP-25 memo aggregate)."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.act.router import MessageOut
from app.api.schemas.assessments import AssessmentVersionOut, FitState
from app.api.schemas.claims import ClaimOut
from app.api.schemas.common import (
    ApiModel,
    CostTotalsOut,
    Disposition,
    EvidenceOut,
    FactStr,
    IdentityState,
    NamedUserOut,
    SourceRecordOut,
)
from app.api.schemas.company import CompanyProfileOut
from app.api.schemas.decision_flip import DecisionFlipOut, DecisionFlipSummaryOut
from app.api.schemas.documents import DeletionRecordOut, DocumentOut
from app.api.schemas.requests import RequestListOut
from app.api.schemas.runs import RunKind, RunOut, RunSummaryOut
from app.api.schemas.theses import CriterionIn, CriterionOut, CriterionResultOut


class CaseStatus(StrEnum):
    verifying = "verifying"
    awaiting_identity = "awaiting_identity"
    assessed = "assessed"
    failed = "failed"


class CaseCreate(ApiModel):
    """Open a case from a shortlist item, or directly from a name and website."""

    shortlist_item_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    website: str | None = Field(default=None, min_length=3, max_length=500)
    thesis_id: str | None = None
    # A company picked from `GET /companies/lookup`: identity starts from this id.
    crustdata_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one_entry_point(self) -> "CaseCreate":
        if self.shortlist_item_id is not None:
            return self
        if self.crustdata_id is not None and self.name:
            return self
        if not (self.name and self.website):
            raise ValueError("give shortlist_item_id, name with crustdata_id, or name and website")
        return self


class IdentityPickIn(ApiModel):
    crustdata_company_id: int


class CaseCriteriaIn(ApiModel):
    """Strategy criteria for a direct-verify case (no thesis). Needed before any fit score."""

    criteria: list[CriterionIn] = Field(min_length=1)


class CaseOut(ApiModel):
    id: str
    name: str
    website: str | None = None
    status: CaseStatus
    identity_state: IdentityState
    crustdata_company_id: int | None = None
    thesis_id: str | None = None
    shortlist_item_id: str | None = None
    credit_budget: float
    created_at: datetime
    owner: NamedUserOut
    run: RunOut | None = Field(default=None, description="Latest run for this case.")


class CaseSummary(ApiModel):
    id: str
    name: str
    website: str | None = None
    status: CaseStatus
    identity_state: IdentityState
    disposition: Disposition | None = None
    fit_state: FitState | None = None
    fit: int | None = None
    assessable_pct: int | None = None
    claim_count: int = 0
    cost: CostTotalsOut = Field(default_factory=CostTotalsOut)
    latest_run_state: str | None = None
    decision_flip: DecisionFlipSummaryOut | None = Field(
        default=None, description="Blockers to the next disposition (latest version)."
    )
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- memo sections


class IdentityKeyOut(ApiModel):
    key: str = Field(description='"domain", "profile_url", "hq_city", "founded_year", "cin", ...')
    label: str
    value: str
    evidence: list[EvidenceOut] = Field(default_factory=list)


class IdentityCandidateOut(ApiModel):
    crustdata_company_id: int
    name: str
    confidence_score: float | None = None
    matching: list[IdentityKeyOut] = Field(default_factory=list)
    differing: list[IdentityKeyOut] = Field(default_factory=list)


class IdentityPickOut(ApiModel):
    crustdata_company_id: int
    picked_by: NamedUserOut
    picked_at: datetime
    matched_keys: list[str]


class IdentityOut(ApiModel):
    state: IdentityState
    entity_name: str | None = None
    crustdata_company_id: int | None = None
    keys: list[IdentityKeyOut] = Field(default_factory=list, description="Matching keys.")
    candidates: list[IdentityCandidateOut] = Field(
        default_factory=list, description="Shown when ambiguous or unresolved."
    )
    pick: IdentityPickOut | None = None
    note: str | None = None


class OpportunityOut(ApiModel):
    thesis_id: str | None = None
    thesis_text: str | None = None
    criteria: list[CriterionOut] = Field(default_factory=list)
    fit_state: FitState
    fit: int | None = None
    assessable_pct: int = 0
    criterion_results: list[CriterionResultOut] = Field(default_factory=list)
    relevance: list[str] = Field(default_factory=list, description="Why it is relevant.")


class EventOut(ApiModel):
    id: str
    event_date: date
    title: str
    kind: str = Field(description='"launch", "expansion", "facility", "funding", ...')
    evidence: EvidenceOut


class ComparisonBasisOut(ApiModel):
    industry: str | None = None
    country: str | None = None
    headcount_band: str | None = None


class ComparableCompanyOut(ApiModel):
    crustdata_company_id: int
    name: str
    observation: FactStr


class ComparablesOut(ApiModel):
    basis: ComparisonBasisOut
    companies: list[ComparableCompanyOut] = Field(default_factory=list)
    no_fair_comparison_reason: str | None = Field(
        default=None, description='"No fair comparison found" plus the basis tried.'
    )


class RiskItemOut(ApiModel):
    kind: str = Field(description='"gap", "estimate_used", "not_checked", "assumption"')
    text: str
    claim_ids: list[str] = Field(default_factory=list)


class CostLineOut(ApiModel):
    run_id: str
    run_kind: RunKind
    step_key: str
    step_label: str
    cost: CostTotalsOut
    cached: bool = False
    at: datetime


class SharedCostOut(ApiModel):
    """Discovery cost shared by every case opened from one shortlist. Not in the case total."""

    run_id: str
    thesis_id: str
    cost: CostTotalsOut


class CaseCostOut(ApiModel):
    crustdata_credits: float
    llm_usd: float
    unknown_cost_calls: int = 0
    credit_budget: float
    checks_not_run: int = 0
    by_step: list[CostLineOut] = Field(default_factory=list)
    shared_discovery: SharedCostOut | None = None


class MemoCitationOut(ApiModel):
    """One numbered citation. A purged excerpt shows its deletion record, not a broken link."""

    id: str = Field(description='Marker used in drafted text, e.g. "F1".')
    number: int
    evidence: EvidenceOut | None = None
    deletion: DeletionRecordOut | None = None


class MemoLineOut(ApiModel):
    """One deterministic memo line (built by rules from the assessment, never drafted)."""

    text: str
    citation_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    kind: str | None = Field(
        default=None, description='"estimate", "signal", "not_checked", "gap", "assumption"...'
    )


class MemoSectionOut(ApiModel):
    key: str
    number: int | None = Field(default=None, description="Template section number, 1-10.")
    heading: str
    drafted_text: str | None = Field(
        default=None,
        description="Prose that only restates cited accepted facts; every sentence ends with "
        "[F<n>] markers. Null for purely structured sections.",
    )
    used_fallback: bool = Field(
        default=False, description="True when the drafted prose failed validation twice."
    )
    lines: list[MemoLineOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list, description="Template boilerplate.")


class CaseMemoOut(ApiModel):
    """The screening memo for one assessment version, in the PRD's finished-case order."""

    assessment_version: int
    assessment_version_id: str
    policy_version: str
    generated_at: datetime
    title: str
    sections: list[MemoSectionOut]
    citations: list[MemoCitationOut] = Field(default_factory=list)
    retention_notice: str | None = Field(
        default=None, description="Deletion dates for uploaded documents, when there are any."
    )


class CaseDetail(ApiModel):
    """The memo aggregate, sections in the PRD's finished-case order."""

    case: CaseOut
    opportunity: OpportunityOut
    identity: IdentityOut
    profile: CompanyProfileOut | None = None
    claims: list[ClaimOut] = Field(default_factory=list)
    events: list[EventOut] = Field(default_factory=list)
    comparables: ComparablesOut
    assessment: AssessmentVersionOut | None = Field(
        default=None, description="Latest version; history via GET /cases/{id}/assessments."
    )
    memo: CaseMemoOut | None = Field(
        default=None, description="Screening memo of the latest assessment version."
    )
    decision_flip: DecisionFlipOut | None = Field(
        default=None,
        description="Hypothetical: what would change the latest version's disposition. "
        "Null until analysed; GET /cases/{id}/decision-flip for other versions.",
    )
    risks: list[RiskItemOut] = Field(default_factory=list)
    request_list: RequestListOut | None = None
    message: MessageOut | None = Field(
        default=None, description="The seller email (revisions, approval, send) from app.act."
    )
    documents: list[DocumentOut] = Field(default_factory=list)
    deletions: list[DeletionRecordOut] = Field(default_factory=list)
    sources: list[SourceRecordOut] = Field(default_factory=list)
    cost: CaseCostOut
    runs: list[RunSummaryOut] = Field(default_factory=list)
