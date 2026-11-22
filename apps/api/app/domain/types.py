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
    DocumentType,
    EffortLevel,
    FlipSearch,
    FlipState,
    FundingKind,
    IdentityStatus,
    ItemClass,
    ItemKind,
    NextAction,
    NotCheckedReason,
    SelectionBasis,
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
    # For seller-provided documents: what kind of document it is. Some
    # questions need a specific record (a dated payroll record, a share
    # allotment) and a generic deck never settles them.
    document_type: DocumentType | None = None

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
    # How the record was tied to ``entity_id`` (design §5.4): the corroborating
    # identifiers that matched, for example ["crustdata_id"], ["domain"],
    # ["cin"] or ["case_upload"]. A name match alone ("name") is not enough,
    # and evidence without a corroborating identifier never decides anything.
    identity_basis: list[str] = Field(default_factory=list)

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
    # Rules-only: a certificate's validity is about one standard. Set on the
    # `certificate_valid_until` components the rules add, so only facts from an
    # origin that also names this standard can settle it.
    scope: str | None = Field(default=None, exclude=True)


class Claim(Model):
    id: str
    text: str  # the original assertion, verbatim
    category: ClaimCategory
    components: list[ClaimComponent]
    # Facts must be attached to one of these entities (company id, person id).
    # Empty means the caller has already guarded identity.
    entity_ids: list[str] = Field(default_factory=list)
    origin: Literal["seller_document", "seller_typed", "profile"] = "seller_document"
    # A material claim that is contradicted or conflicting blocks "prioritise".
    material: bool = True


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
    # Source classes of the decisive origins, so an announcement-only match
    # stays visibly an announcement downstream (memo, UI).
    provenance: list[SourceReliability] = Field(default_factory=list)
    announcement_only: bool = False


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
    # Entity binding for case evaluation (design §5.4). When ``evidence_id``
    # names an Evidence passed to the assessment, that evidence's binding is
    # used instead.
    entity_id: str | None = None
    identity_basis: list[str] = Field(default_factory=list)
    # Another adequate source disagrees: the criterion is unknown, never fail.
    disputed: bool = False


class CompanyRecord(Model):
    entity_id: str
    name: str
    fields: dict[str, FieldFact] = Field(default_factory=dict)
    # Other sourced values for the same field (from other origins). When they
    # lead to a different criterion result, the criterion is disputed.
    field_alternatives: dict[str, list[FieldFact]] = Field(default_factory=dict)


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
    # Whether v1 has a check for this question. Prioritise needs every covered
    # required check complete; uncovered ones stay listed as gaps.
    covered_in_v1: bool = True


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


FinancialBasis = Literal["audited", "filing", "registry", "company_results", "estimate"]
ListingStatus = Literal["listed", "unlisted", "unknown"]


class FinancialFigure(Model):
    component: str
    value: Any
    as_of: dt.date | None = None
    evidence_id: str
    source_label: str
    # What the figure is: a period ("Q2 FY27"), its unit as written, and the kind of
    # record it came from. `display` is the figure as shown ("₹2,095 cr").
    period: str | None = None
    period_end: dt.date | None = None
    period_months: int | None = None
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None
    display: str | None = None
    basis: FinancialBasis | None = None
    quote: str | None = None


class FinancialAssessment(Model):
    assessed: bool
    reason: str
    figures: list[FinancialFigure] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    # assessed: reliable reported figures; indicative: provider estimates only;
    # not_found: the public search ran and found nothing; not_assessed: no search yet.
    state: Literal["assessed", "indicative", "not_found", "not_assessed"] = "not_assessed"
    period: str | None = None
    conclusion: str | None = None
    searched: list[str] = Field(default_factory=list)
    would_need: list[str] = Field(default_factory=list)


class ReportedFigure(Model):
    """A figure `verify.financials` read from a public filing, registry page or a
    listed company's results page, with the period and unit it was stated in."""

    fact: ExtractedFact
    period: str | None = None
    period_end: dt.date | None = None
    period_months: int | None = None
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None


class FinancialEstimate(Model):
    """A data provider's revenue estimate: a range, never a reported figure."""

    lower_usd: float | None = None
    upper_usd: float | None = None
    as_of: dt.date | None = None
    evidence_id: str
    source_label: str


class FinancialInputs(Model):
    figures: list[ReportedFigure] = Field(default_factory=list)
    estimates: list[FinancialEstimate] = Field(default_factory=list)
    listing: ListingStatus = "unknown"
    listing_basis: str | None = None
    # What `verify.financials` searched; None while it has not run.
    searched: list[str] | None = None


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
    financials: FinancialInputs = Field(default_factory=FinancialInputs)
    # Evidence behind CompanyRecord fields, so criteria are recomputed from
    # entity-bound evidence through the same screen as claims.
    evidence: list[Evidence] = Field(default_factory=list)


class RequestQuestion(Model):
    id: str
    text: str
    claim_id: str | None = None
    kind: Literal["claim", "identity", "financial_inputs", "unrun_check"]
    # The precise unresolved component of the claim this question is about.
    component: str | None = None
    # Whether a document from the seller can resolve it, tracked apart from
    # the claim status. Questions only the analyst can resolve never go to
    # the seller.
    seller_resolvable: bool = True


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
    # Open questions the seller cannot resolve (for example a registry charge
    # record): the analyst follows them up; they are not in the seller list.
    analyst_questions: list[RequestQuestion] = Field(default_factory=list)


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


# --- DecisionFlip --------------------------------------------------------------
# Output of ``app.rules.decision_flip.analyse``: which open items stand between
# the case and the next disposition, found by re-running the rules with items
# forced to a hypothetical state. Ids, enums, policy document names and rule
# reasons only: no claim text and no evidence values.


class ItemOutcome(Model):
    """The disposition the rules give with one or more items forced. Never verified."""

    hypothetical: Literal[True] = True
    disposition: Disposition
    rule: str  # decide_disposition's rule id
    reasons: list[str]
    changes_disposition: bool  # differs from the real disposition


class UnresolvedItem(Model):
    # "claim:<id>", "check:<category>", "criterion:<id>", "identity" or "financial_inputs"
    id: str
    kind: ItemKind
    claim_id: str | None = None
    criterion_id: str | None = None
    check: ClaimCategory | None = None
    # e.g. a claim status ("cannot_verify"), "unknown" for a criterion, "absent"
    # for a required check never claimed, the identity status, "not_assessed".
    current_state: str
    classification: ItemClass
    decision_blocker: bool  # in at least one minimal set (or the greedy set)
    disqualifier_risk: bool  # if contradicted, the case would be Deprioritise
    required_in_every_path: bool
    flips_alone: bool  # forcing only this item supported reaches the target
    locks_target: bool  # contradicted, the target is out of reach even if all else is supported
    seller_resolvable: bool
    analyst_retry: bool
    depends_on: list[str] = Field(default_factory=list)
    settle_with: list[str] = Field(default_factory=list)  # policy document names
    if_supported: ItemOutcome | None = None
    if_contradicted: ItemOutcome | None = None  # None when not simulated
    # Coarse effort to obtain its documents (policy.DOCUMENT_EFFORT); a tie-break only.
    est_effort: EffortLevel = EffortLevel.MEDIUM
    # For criteria and financial items: what to obtain, with both branches stated
    # ("If the verified figure is at least 100, Headcount passes; otherwise it fails").
    conditional_action: str | None = None


class SettleDocument(Model):
    document: str
    item_ids: list[str]
    seller_resolvable: bool


class MinimalSet(Model):
    """A set of items that, all forced supported, reaches the target and has no
    reaching proper subset (greedy: no single item can be dropped)."""

    hypothetical: Literal[True] = True
    item_ids: list[str]
    documents: list[SettleDocument]
    outcome: ItemOutcome


class NextBestAction(Model):
    action: NextAction
    text: str  # from the fixed templates, never a model
    item_ids: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    # The conditional sentences (both branches) for criteria and financial items in
    # the set; also appended to ``text``.
    conditions: list[str] = Field(default_factory=list)


MINIMUM_SET_LABEL = "Minimum set of checks required to change the screening outcome"


class DecisionFlipAnalysis(Model):
    hypothetical: Literal[True] = True
    case_id: str
    assessment_version: int
    policy_version: str
    inputs_hash: str
    flip_version: str
    # sha256 of {inputs_hash, policy_version, flip_version, materiality}
    analysis_key: str
    state: FlipState
    current: Disposition
    current_rule: str
    current_reasons: list[str]
    target: Disposition | None
    ceiling: ItemOutcome  # every item forced supported
    items: list[UnresolvedItem]
    minimal_sets: list[MinimalSet]  # exhaustive: all; greedy: the one found
    minimum_evidence: MinimalSet | None
    worst_if_contradicted: ItemOutcome | None
    next_best_action: NextBestAction
    search: FlipSearch
    greedy: bool
    evaluations: int  # number of rule runs
    # The minimum set is the fewest checks, never "the cheapest"; effort is a tie-break.
    selection_basis: SelectionBasis = SelectionBasis.FEWEST_CHECKS
    selection_label: str = MINIMUM_SET_LABEL


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
