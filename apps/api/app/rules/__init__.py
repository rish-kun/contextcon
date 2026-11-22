"""DealProof's deterministic rules engine.

Pure Python: no I/O, no LLM, no network, no clock. The same records under the
same policy give the same assessment every time (PRD principle 6). The policy
itself is data in ``app.rules.policy`` and is explained in ``POLICY.md``.
"""

from app.rules.claim_status import (
    combine_states,
    decide_all,
    decide_claim_status,
    effective_components,
)
from app.rules.company_type import classify_company, criteria_for, required_checks
from app.rules.decision_flip import (
    FLIP_VERSION,
    DecisionFlipAnalysis,
    FlipSearch,
    FlipState,
    ItemClass,
    ItemKind,
    ItemOutcome,
    MinimalSet,
    NextAction,
    NextBestAction,
    ReplayMismatch,
    SettleDocument,
    UnresolvedItem,
    analyse,
)
from app.rules.diff import diff
from app.rules.evaluate import (
    assess,
    business_assessment,
    decide_disposition,
    evidence_sufficiency,
    financial_assessment,
    inputs_hash,
)
from app.rules.fit import (
    assess_candidate,
    assess_case_candidate,
    evaluate_case_criteria,
    evaluate_criterion,
    fit_score,
    must_have_failures,
    opportunity_fit,
    screen_company_record,
    shortlist,
)
from app.rules.investors import funding_kind, rank_investors
from app.rules.policy import POLICY_VERSION
from app.rules.requests import build_request_list
from app.rules.validation import (
    entity_binding_corroborated,
    infer_kind,
    screen_evidence,
    screen_fact,
    validate_extraction,
    value_in_span,
)

__all__ = [
    "FLIP_VERSION",
    "POLICY_VERSION",
    "DecisionFlipAnalysis",
    "FlipSearch",
    "FlipState",
    "ItemClass",
    "ItemKind",
    "ItemOutcome",
    "MinimalSet",
    "NextAction",
    "NextBestAction",
    "ReplayMismatch",
    "SettleDocument",
    "UnresolvedItem",
    "analyse",
    "assess",
    "assess_candidate",
    "assess_case_candidate",
    "build_request_list",
    "business_assessment",
    "classify_company",
    "combine_states",
    "criteria_for",
    "decide_all",
    "decide_claim_status",
    "decide_disposition",
    "diff",
    "effective_components",
    "entity_binding_corroborated",
    "evaluate_case_criteria",
    "evaluate_criterion",
    "evidence_sufficiency",
    "financial_assessment",
    "fit_score",
    "funding_kind",
    "infer_kind",
    "inputs_hash",
    "must_have_failures",
    "opportunity_fit",
    "rank_investors",
    "required_checks",
    "screen_company_record",
    "screen_evidence",
    "screen_fact",
    "shortlist",
    "validate_extraction",
    "value_in_span",
]
