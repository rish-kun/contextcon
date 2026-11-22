"""Discover: tri-state criteria, must-have gate, fit and assessable share, ranking.

- Each criterion is pass, fail or unknown. Missing data is unknown.
- Only a *verified* fail of a must-have excludes (a sourced value, not an estimate).
- fit = Σ weight(pass) / Σ weight(pass ∪ fail) × 100, None when nothing is assessable.
- assessable% = |pass ∪ fail| / |all| × 100. Unknowns lower this, never fit.
- Ranking: fit (None last), then assessable%, then name and id for stability.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import CriterionKind, CriterionOperator, CriterionResult
from app.domain.types import (
    CandidateAssessment,
    CompanyRecord,
    Criterion,
    CriterionEvaluation,
    FieldFact,
    OpportunityFit,
    Shortlist,
)
from app.rules import policy
from app.rules.compare import contains_phrase, normalize_text, to_number


def weight_of(criterion: Criterion) -> int:
    return (
        criterion.weight
        if criterion.weight is not None
        else policy.CRITERION_WEIGHTS[criterion.kind]
    )


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple | set | frozenset) else [value]


def _test(op: CriterionOperator, target: Any, actual: Any) -> bool | None:
    """True/False, or None when the value cannot be compared."""
    if op is CriterionOperator.IS_TRUE:
        return bool(actual) if isinstance(actual, bool) else None
    if op is CriterionOperator.CONTAINS_ANY:
        words = _as_list(target)
        haystack = " ".join(str(v) for v in _as_list(actual))
        return any(contains_phrase(haystack, w) for w in words)
    if op in (CriterionOperator.EQ, CriterionOperator.IN):
        options = {normalize_text(t) for t in _as_list(target)}
        values = {normalize_text(v) for v in _as_list(actual)}
        return bool(options & values)
    n = to_number(actual)
    if n is None:
        return None
    if op is CriterionOperator.GTE:
        t = to_number(target)
        return None if t is None else n >= t
    if op is CriterionOperator.LTE:
        t = to_number(target)
        return None if t is None else n <= t
    if op is CriterionOperator.BETWEEN:
        lo, hi = (to_number(x) for x in target)
        if lo is None or hi is None:
            return None
        return lo <= n <= hi
    return None


def evaluate_criterion(criterion: Criterion, company: CompanyRecord) -> CriterionEvaluation:
    fact: FieldFact | None = company.fields.get(criterion.field)
    base = {"criterion_id": criterion.id, "kind": criterion.kind}
    if fact is None or fact.value is None or fact.value == [] or fact.value == "":
        return CriterionEvaluation(
            **base,
            result=CriterionResult.UNKNOWN,
            verified=False,
            reason=f"No record states {criterion.field}",
        )
    outcome = _test(criterion.operator, criterion.value, fact.value)
    ev_ids = [fact.evidence_id] if fact.evidence_id else []
    if outcome is None:
        return CriterionEvaluation(
            **base,
            result=CriterionResult.UNKNOWN,
            verified=False,
            reason=f"{criterion.field} = {fact.value!r} cannot be compared",
            evidence_ids=ev_ids,
        )
    verified = fact.evidence_id is not None and not fact.is_estimate
    basis = "estimate" if fact.is_estimate else ("sourced" if fact.evidence_id else "unsourced")
    return CriterionEvaluation(
        **base,
        result=CriterionResult.PASS if outcome else CriterionResult.FAIL,
        verified=verified,
        reason=f"{criterion.field} = {fact.value!r} ({basis})",
        evidence_ids=ev_ids,
    )


def must_have_failures(evaluations: list[CriterionEvaluation]) -> list[CriterionEvaluation]:
    """Only verified fails of must-haves. Unknowns and estimate-based fails keep a company."""
    return [
        e
        for e in evaluations
        if e.kind is CriterionKind.MUST and e.result is CriterionResult.FAIL and e.verified
    ]


def _pct(num: int, den: int) -> int:
    return round(100 * num / den) if den else 0


def fit_score(
    criteria: list[Criterion],
    evaluations: list[CriterionEvaluation],
    *,
    verified_only: bool = False,
) -> tuple[int | None, int]:
    """(fit, assessable%). With verified_only, estimate-based results count as unknown."""
    by_id = {c.id: c for c in criteria}
    passed = assessable_weight = assessable = 0
    for e in evaluations:
        if e.result is CriterionResult.UNKNOWN or (verified_only and not e.verified):
            continue
        w = weight_of(by_id[e.criterion_id])
        assessable += 1
        assessable_weight += w
        if e.result is CriterionResult.PASS:
            passed += w
    fit = round(100 * passed / assessable_weight) if assessable_weight else None
    return fit, _pct(assessable, len(evaluations))


def opportunity_fit(criteria: list[Criterion], company: CompanyRecord) -> OpportunityFit:
    evaluations = [evaluate_criterion(c, company) for c in criteria]
    fit, pct = fit_score(criteria, evaluations)
    vfit, vpct = fit_score(criteria, evaluations, verified_only=True)
    label = (
        f"Fit {fit} out of 100, with {pct}% of the criteria assessable"
        if fit is not None
        else f"Fit unavailable: {pct}% of the criteria assessable"
    )
    return OpportunityFit(
        fit=fit,
        assessable_pct=pct,
        verified_fit=vfit,
        verified_assessable_pct=vpct,
        label=label,
        evaluations=evaluations,
    )


def assess_candidate(criteria: list[Criterion], company: CompanyRecord) -> CandidateAssessment:
    """Apply the gate and fit. Call again after enrichment: the gate re-applies."""
    of = opportunity_fit(criteria, company)
    labels = {c.id: c.label for c in criteria}
    failures = must_have_failures(of.evaluations)
    return CandidateAssessment(
        entity_id=company.entity_id,
        name=company.name,
        excluded=bool(failures),
        exclusion_reasons=[
            f"Must-have failed: {labels[e.criterion_id]} ({e.reason})" for e in failures
        ],
        fit=of,
        unknown_criteria=[
            labels[e.criterion_id] for e in of.evaluations if e.result is CriterionResult.UNKNOWN
        ],
    )


def _rank_key(a: CandidateAssessment) -> tuple:
    fit = a.fit.fit
    return (fit is None, -(fit or 0), -a.fit.assessable_pct, a.name.casefold(), a.entity_id)


def shortlist(criteria: list[Criterion], companies: list[CompanyRecord]) -> Shortlist:
    assessed = [assess_candidate(criteria, c) for c in companies]
    return Shortlist(
        ranked=sorted((a for a in assessed if not a.excluded), key=_rank_key),
        excluded=sorted((a for a in assessed if a.excluded), key=_rank_key),
    )
