"""Scoring policy (served by CP-25, rendered by the policy page)."""

from pydantic import Field

from app.api.schemas.common import ApiModel, ClaimCategory, Disposition, SourceClass


class PolicyWeightsOut(ApiModel):
    must: int
    preference: int


class PolicyThresholdsOut(ApiModel):
    prioritise_fit_min: int
    prioritise_sufficiency_min: int
    deprioritise_fit_below: int
    deprioritise_assessable_min: int
    cannot_assess_assessable_below: int


class DispositionRuleOut(ApiModel):
    order: int
    disposition: Disposition
    rule: str


class RequiredChecksOut(ApiModel):
    startup: list[ClaimCategory]
    established: list[ClaimCategory]


class AdequateSourcesOut(ApiModel):
    category: ClaimCategory
    component: str = Field(description='"*" means every component of the category.')
    source_classes: list[SourceClass]


class SettleWithOut(ApiModel):
    category: ClaimCategory
    document: str


class BudgetsOut(ApiModel):
    case_credits: float
    discover_credits: float
    investor_credits: float


class PolicyOut(ApiModel):
    policy_version: str
    weights: PolicyWeightsOut
    fit_formula: str
    assessable_formula: str
    thresholds: PolicyThresholdsOut
    disposition_rules: list[DispositionRuleOut]
    required_checks: RequiredChecksOut
    adequate_sources: list[AdequateSourcesOut]
    settle_with: list[SettleWithOut]
    company_type_rule: str
    investor_ranking_rule: str
    comparables_rule: str
    budgets: BudgetsOut
    markdown: str = Field(default="", description="POLICY.md: the policy explained in words.")
