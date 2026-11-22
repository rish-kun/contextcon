"""DealProof's deterministic rules engine.

Pure Python: no I/O, no LLM, no network, no clock. The same records under the
same policy give the same assessment every time (PRD principle 6). The policy
itself is data in ``app.rules.policy`` and is explained in ``POLICY.md``.
"""

from app.rules.claim_status import decide_all, decide_claim_status
from app.rules.company_type import classify_company, criteria_for, required_checks
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
    evaluate_criterion,
    fit_score,
    must_have_failures,
    opportunity_fit,
    shortlist,
)
from app.rules.investors import funding_kind, rank_investors
from app.rules.policy import POLICY_VERSION
from app.rules.requests import build_request_list
from app.rules.validation import validate_extraction

__all__ = [
    "POLICY_VERSION",
    "assess",
    "assess_candidate",
    "build_request_list",
    "business_assessment",
    "classify_company",
    "criteria_for",
    "decide_all",
    "decide_claim_status",
    "decide_disposition",
    "diff",
    "evaluate_criterion",
    "evidence_sufficiency",
    "financial_assessment",
    "fit_score",
    "funding_kind",
    "inputs_hash",
    "must_have_failures",
    "opportunity_fit",
    "rank_investors",
    "required_checks",
    "shortlist",
    "validate_extraction",
]
