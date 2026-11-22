"""Shared domain types: the inputs and outputs of the rules engine.

All models are frozen and JSON-serialisable (``model_dump(mode="json")``). They
carry no I/O and no timestamps of their own, so the same inputs always produce
the same outputs.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    Compatibility,
    ComponentState,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    Disposition,
    FundingKind,
    IdentityStatus,
    NotCheckedReason,
    SourceReliability,
)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Provenance --------------------------------------------------------------


class Source(Model):
    id: str
    provider: str  # e.g. "crustdata:company_enrich", "web", "upload", "user"
    label: str  # human label shown on the source chip
    url: str | None = None
    retrieved_at: dt.datetime
    reliability: SourceReliability
    # Syndicated copies of one announcement share an origin_key, so they count
    # as one origin. Defaults to the URL, then the source id.
    origin_key: str | None = None

    @property
    def origin(self) -> str:
        return self.origin_key or self.url or self.id


class Evidence(Model):
    """One quoted span or one structured field from a source, about one entity."""

    id: str
    source: Source
    entity_id: str | None = None
    quote: str | None = None
    field_path: str | None = None
    field_value: Any = None
    page: int | None = None
    as_of: dt.date | None = None  # when the underlying fact was true, not retrieval

    @model_validator(mode="after")
    def _has_span_or_field(self) -> Evidence:
        if not (self.quote and self.quote.strip()) and not self.field_path:
            raise ValueError("evidence needs a quote or a field path")
        return self


class ExtractedFact(Model):
    """A structured value read from one piece of evidence, for one claim component."""

    id: str
    evidence: Evidence
    component: str
    value: Any


# --- Claims ------------------------------------------------------------------


class ClaimComponent(Model):
    name: str  # a key of app.rules.policy.COMPONENT_RULES
    value: Any
    op: Literal["eq", "gte", "lte"] = "eq"


class Claim(Model):
    id: str
    text: str  # the original assertion, verbatim
    category: ClaimCategory
    components: list[ClaimComponent]
    # Facts must be attached to one of these entities (company id, person id).
    # Empty means the caller has already guarded identity.
    entity_ids: list[str] = Field(default_factory=list)
    origin: Literal["seller_document", "seller_typed", "profile"] = "seller_document"


class ClaimCheck(Model):
    """Everything the status rules need for one claim."""

    claim: Claim
    facts: list[ExtractedFact] = Field(default_factory=list)
    ran: bool = True
    not_run_reason: NotCheckedReason | None = None
    not_run_detail: str | None = None
    # Sources that were read for this claim, including ones that said nothing.
    sources_read: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reason_when_not_run(self) -> ClaimCheck:
        if not self.ran and self.not_run_reason is None:
            raise ValueError("a check that did not run needs a not_run_reason")
        return self


class ExtractionCheck(Model):
    valid: bool
    reason: str


class EvidenceRef(Model):
    """How one fact was used in a decision; enough for a source chip and the diff."""

    fact_id: str
    evidence_id: str
    component: str
    value: Any
    source_label: str
    reliability: SourceReliability
    origin: str
    as_of: dt.date | None = None
    role: Literal["decisive", "not_adequate", "undecided", "related", "rejected"]
    note: str = ""


class ComponentFinding(Model):
    component: str
    check: ClaimCategory
    state: ComponentState
    decisive_evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""


class CheckOutcome(Model):
    claim_id: str
    category: ClaimCategory
    status: ClaimStatus
    reason: str
    # What would settle it: document or record types. Empty only when supported.
    settle_with: list[str] = Field(default_factory=list)
    components: list[ComponentFinding] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    not_checked_reason: NotCheckedReason | None = None
    analyst_retry: bool = False


# --- Discover ----------------------------------------------------------------


class Criterion(Model):
    id: str
    label: str
    kind: CriterionKind
    field: str  # key into CompanyRecord.fields
    operator: CriterionOperator
    value: Any = None
    weight: int | None = None  # defaults by kind, see policy
    dimension: str | None = None


class FieldFact(Model):
    value: Any
    evidence_id: str | None = None
    as_of: dt.date | None = None
    is_estimate: bool = False


class CompanyRecord(Model):
    entity_id: str
    name: str
    fields: dict[str, FieldFact] = Field(default_factory=dict)


class CriterionEvaluation(Model):
    criterion_id: str
    kind: CriterionKind
    result: CriterionResult
    # A fail is verified only when it rests on a sourced value that is not an
    # estimate. Only a verified fail of a must-have excludes a company.
    verified: bool
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class OpportunityFit(Model):
    fit: int | None  # None = unavailable (nothing assessable)
    assessable_pct: int
    verified_fit: int | None
    verified_assessable_pct: int
    label: str
    evaluations: list[CriterionEvaluation] = Field(default_factory=list)


class CandidateAssessment(Model):
    entity_id: str
    name: str
    excluded: bool
    exclusion_reasons: list[str] = Field(default_factory=list)
    fit: OpportunityFit
    unknown_criteria: list[str] = Field(default_factory=list)


class Shortlist(Model):
    ranked: list[CandidateAssessment]
    excluded: list[CandidateAssessment]


# --- Evaluate ----------------------------------------------------------------


class CompanyTypeDecision(Model):
    company_type: CompanyType
    reason: str


class EvaluationCriterion(Model):
    name: str
    label: str
    checks: list[ClaimCategory]


class CheckSufficiency(Model):
    check: ClaimCategory
    adequate: bool  # adequate evidence settled it (supported or contradicted)
    result: ClaimStatus | None  # the substantive result, recorded separately
    claim_ids: list[str] = Field(default_factory=list)
    gap: str | None = None
    settle_with: list[str] = Field(default_factory=list)


class EvidenceSufficiency(Model):
    company_type: CompanyType
    pct: int
    checks: list[CheckSufficiency]
    gaps: list[str] = Field(default_factory=list)


class Signal(Model):
    label: str
    value: Any
    as_of: dt.date | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    is_signal: Literal[True] = True


class BusinessAssessment(Model):
    signals: list[Signal]
    note: str


class FinancialFigure(Model):
    component: str
    value: Any
    as_of: dt.date | None = None
    evidence_id: str
    source_label: str


class FinancialAssessment(Model):
    assessed: bool
    reason: str
    figures: list[FinancialFigure] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class DispositionDecision(Model):
    disposition: Disposition
    rule: str  # which predicate fired, see POLICY.md
    reasons: list[str]


class Judgments(Model):
    """Five judgments, deliberately never blended into one score."""

    opportunity_fit: OpportunityFit
    evidence_sufficiency: EvidenceSufficiency
    business: BusinessAssessment
    financial: FinancialAssessment
    disposition: DispositionDecision


class SeriesPoint(Model):
    date: dt.date
    value: float
    evidence_id: str


class DatedEvent(Model):
    label: str
    date: dt.date
    evidence_id: str


class BusinessInputs(Model):
    headcount_series: list[SeriesPoint] = Field(default_factory=list)  # profile estimates
    open_roles: FieldFact | None = None
    locations: list[FieldFact] = Field(default_factory=list)
    events: list[DatedEvent] = Field(default_factory=list)


class CompanyProfile(Model):
    founded_year: int | None = None
    headcount: int | str | None = None  # number or band such as "201-500"
    funding_stage: str | None = None


class AssessmentInputs(Model):
    case_id: str
    version: int = 1
    today: dt.date  # passed in, never read from the clock
    identity_status: IdentityStatus
    profile: CompanyProfile
    company: CompanyRecord
    criteria: list[Criterion]
    claim_checks: list[ClaimCheck]
    business: BusinessInputs = Field(default_factory=BusinessInputs)
    financial_facts: list[ExtractedFact] = Field(default_factory=list)


class RequestQuestion(Model):
    id: str
    text: str
    claim_id: str | None = None
    kind: Literal["claim", "identity", "financial_inputs", "unrun_check"]


class RequestItem(Model):
    document: str
    question_ids: list[str]
    claim_ids: list[str] = Field(default_factory=list)


class AnalystRetry(Model):
    claim_id: str
    reason: NotCheckedReason
    detail: str | None = None


class RequestList(Model):
    questions: list[RequestQuestion]
    documents: list[RequestItem]
    analyst_retries: list[AnalystRetry]


class AssessmentVersion(Model):
    case_id: str
    version: int
    policy_version: str
    inputs_hash: str
    company_type: CompanyTypeDecision
    candidate: CandidateAssessment
    outcomes: list[CheckOutcome]
    judgments: Judgments
    disposition: Disposition
    requests: RequestList


class ClaimChange(Model):
    claim_id: str
    before: ClaimStatus | None
    after: ClaimStatus | None
    evidence_added: list[str]
    evidence_removed: list[str]
    reason: str


class JudgmentChange(Model):
    judgment: Literal[
        "opportunity_fit", "evidence_sufficiency", "business", "financial", "disposition"
    ]
    field: str
    before: Any
    after: Any
    because: list[str]  # evidence ids, claim ids or criterion ids that caused it
    reason: str


class DispositionChange(Model):
    before: Disposition
    after: Disposition
    because: list[str]
    reason: str


class AssessmentDiff(Model):
    from_version: int
    to_version: int
    policy_changed: bool
    inputs_changed: bool
    claim_changes: list[ClaimChange]
    judgment_changes: list[JudgmentChange]
    disposition_change: DispositionChange | None


# --- Investors ---------------------------------------------------------------


class FundingRecord(Model):
    id: str
    company_id: str
    company_name: str
    company_sectors: list[str] = Field(default_factory=list)
    company_country: str | None = None
    round_type: str | None = None
    date: dt.date | None = None
    amount_usd: float | None = None
    investor_id: str | None = None
    investor_name: str | None = None
    investor_domain: str | None = None
    investor_country: str | None = None
    investor_type: str | None = None
    evidence_id: str


class SearchScope(Model):
    sectors: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    as_of: dt.date
    lookback_years: int = 6
    companies_examined: int = 0


class ComparableRound(Model):
    record_id: str
    company_id: str
    company_name: str
    round_type: str | None
    date: dt.date
    amount_usd: float | None
    evidence_id: str


class LatestInvestment(Model):
    date: dt.date
    company_name: str
    round_type: str | None
    evidence_id: str
    scope_note: str


class RankedInvestor(Model):
    key: str
    investor_id: str | None
    name: str
    aliases: list[str]
    comparable_rounds: list[ComparableRound]
    comparable_count: int
    score: float
    latest_sector_investment: LatestInvestment | None
    funding_kind: FundingKind | None
    compatibility: Compatibility
    compatibility_reason: str
    possible_duplicates: list[str] = Field(default_factory=list)
    why: str
    unknowns: list[str] = Field(default_factory=list)


class ExcludedRecord(Model):
    record_id: str
    reason: str


class InvestorRanking(Model):
    scope: SearchScope
    investors: list[RankedInvestor]
    excluded_records: list[ExcludedRecord]
