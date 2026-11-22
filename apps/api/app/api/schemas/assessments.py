"""Assessment versions (CP-22): five separate judgments, never one combined score."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from app.api.schemas.common import (
    ApiModel,
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    Disposition,
    EvidenceOut,
    FactStr,
)
from app.api.schemas.theses import CriterionResultOut


class FitState(StrEnum):
    scored = "scored"
    unavailable = "unavailable"
    awaiting_strategy_criteria = "awaiting_strategy_criteria"
    identity_unresolved = "identity_unresolved"


class OpportunityFitOut(ApiModel):
    state: FitState
    fit: int | None = Field(default=None, description="Only set when state is scored.")
    assessable_pct: int = 0
    note: str | None = None
    criterion_results: list[CriterionResultOut] = Field(default_factory=list)


class SufficiencyItemOut(ApiModel):
    category: ClaimCategory
    status: ClaimStatus | None = Field(default=None, description="Null: not claimed.")
    claim_ids: list[str] = Field(default_factory=list)
    settle_with: str | None = None
    note: str | None = None


class EvidenceSufficiencyOut(ApiModel):
    pct: int = Field(description="Settled required checks / required checks.")
    required_categories: list[ClaimCategory]
    settled: list[SufficiencyItemOut] = Field(default_factory=list)
    gaps: list[SufficiencyItemOut] = Field(default_factory=list)


class BusinessSignalOut(ApiModel):
    label: str
    fact: FactStr = Field(description="Always labelled as a signal or estimate.")


class BusinessAssessmentOut(ApiModel):
    assessed: bool
    reason: str | None = None
    signals: list[BusinessSignalOut] = Field(default_factory=list)


class FinancialFigureOut(ApiModel):
    label: str
    fact: FactStr
    assumption: str | None = None


class FinancialAssessmentOut(ApiModel):
    assessed: bool
    reason: str | None = Field(default=None, description='"No reliable financial inputs".')
    would_need: list[str] = Field(default_factory=list)
    period: str | None = None
    figures: list[FinancialFigureOut] = Field(default_factory=list)
    conclusion: str | None = Field(default=None, description="Bounded; never a valuation.")


class DispositionReasonOut(ApiModel):
    text: str
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ScreeningDispositionOut(ApiModel):
    disposition: Disposition
    reasons: list[DispositionReasonOut]


class JudgmentsOut(ApiModel):
    opportunity_fit: OpportunityFitOut
    evidence_sufficiency: EvidenceSufficiencyOut
    business_assessment: BusinessAssessmentOut
    financial_assessment: FinancialAssessmentOut
    screening_disposition: ScreeningDispositionOut


class DiffLineOut(ApiModel):
    kind: Literal["claim", "judgment", "disposition"]
    subject: str = Field(description="Claim text or judgment name.")
    subject_id: str | None = None
    before: str | None = None
    after: str
    because: str = Field(description='E.g. "payroll_summary.pdf, p. 2". Never empty.')
    evidence: list[EvidenceOut] = Field(default_factory=list)


class AssessmentVersionOut(ApiModel):
    id: str
    version: int
    created_at: datetime
    policy_version: str
    inputs_hash: str
    trigger: str = Field(description='"initial verify", "seller documents <names>", ...')
    company_type: CompanyType | None = None
    judgments: JudgmentsOut
    diff_from_previous: list[DiffLineOut] | None = Field(
        default=None, description="Null for version 1."
    )
