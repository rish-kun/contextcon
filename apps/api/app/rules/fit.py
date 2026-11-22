"""Discover: tri-state criteria, must-have gate, fit and assessable share, ranking.

- Each criterion is pass, fail or unknown. Missing data is unknown.
- Only a *verified* fail of a must-have excludes (a sourced value, not an estimate).
- fit = Σ weight(pass) / Σ weight(pass ∪ fail) × 100, None when nothing is assessable.
- assessable% = |pass ∪ fail| / |all| × 100. Unknowns lower this, never fit.
- Ranking: fit (None last), then assessable%, then name and id for stability.
- A disputed field (another source disagrees) is unknown, never fail.
- A fail on a stale field (older than FIELD_STALE_AFTER_DAYS) is not verified.
- Case evaluation (``assess_case_candidate``) recomputes every criterion from
  evidence bound to the confirmed company on a corroborating identifier and
  adequate for a criterion; anything else is unknown.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from app.domain.enums import CriterionKind, CriterionOperator, CriterionResult, SourceReliability
from app.domain.types import (
    CandidateAssessment,
    CompanyRecord,
    Criterion,
    CriterionEvaluation,
    Evidence,
    FieldFact,
    OpportunityFit,
    Shortlist,
)
from app.rules import policy
from app.rules.compare import contains_phrase, normalize_text, to_number
from app.rules.validation import screen_evidence

# A criterion is a question about the company: an announcement or the seller's
# own statement cannot answer it, and a profile-based figure is an estimate.
_CRITERION_INADEQUATE = frozenset(
    {SourceReliability.COMPANY_ANNOUNCEMENT, SourceReliability.SELLER_STATEMENT}
)
_CRITERION_ESTIMATE = frozenset({SourceReliability.PROFESSIONAL_PROFILE_SIGNAL})


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


def _empty(fact: FieldFact | None) -> bool:
    return fact is None or fact.value is None or fact.value == [] or fact.value == ""


def is_stale(fact: FieldFact, today: date | None) -> bool:
    return (
        today is not None
        and fact.as_of is not None
        and (today - fact.as_of).days > policy.FIELD_STALE_AFTER_DAYS
    )


def evaluate_criterion(
    criterion: Criterion,
    company: CompanyRecord,
    *,
    today: date | None = None,
) -> CriterionEvaluation:
    fact: FieldFact | None = company.fields.get(criterion.field)
    base = {"criterion_id": criterion.id, "kind": criterion.kind}
    if _empty(fact):
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
    # Disputed: another source gives a value with a different result. The
    # criterion is unknown, never fail (design §6.4).
    alternatives = [
        alt for alt in company.field_alternatives.get(criterion.field, []) if not _empty(alt)
    ]
    other = {_test(criterion.operator, criterion.value, alt.value) for alt in alternatives}
    if fact.disputed or (other - {None, outcome}):
        ev_ids += [a.evidence_id for a in alternatives if a.evidence_id]
        return CriterionEvaluation(
            **base,
            result=CriterionResult.UNKNOWN,
            verified=False,
            reason=f"{criterion.field}: sources disagree, so it is unknown",
            evidence_ids=list(dict.fromkeys(ev_ids)),
        )
    stale = is_stale(fact, today)
    verified = fact.evidence_id is not None and not fact.is_estimate and not stale
    basis = (
        "estimate"
        if fact.is_estimate
        else ("stale" if stale else ("sourced" if fact.evidence_id else "unsourced"))
    )
    return CriterionEvaluation(
        **base,
        result=CriterionResult.PASS if outcome else CriterionResult.FAIL,
        verified=verified,
        reason=f"{criterion.field} = {fact.value!r} ({basis})"
        + (f", as of {fact.as_of.isoformat()}" if stale and fact.as_of else ""),
        evidence_ids=ev_ids,
    )


# --- Case evaluation: criteria recomputed from screened evidence -----------------


def _bind_field(
    fact: FieldFact, company_id: str, evidence: dict[str, Evidence]
) -> tuple[FieldFact | None, str]:
    """Screen one field through the identity guard and criterion adequacy.

    Returns the field to use (possibly marked as an estimate) or None with the
    reason it cannot be used.
    """
    ev = evidence.get(fact.evidence_id) if fact.evidence_id else None
    if ev is not None:
        check = screen_evidence(ev, [company_id])
        if not check.valid:
            return None, check.reason
        cls = ev.source.reliability
        if cls in _CRITERION_INADEQUATE:
            return None, f"a {cls.value.replace('_', ' ')} cannot settle a criterion"
        if cls in _CRITERION_ESTIMATE and not fact.is_estimate:
            fact = fact.model_copy(update={"is_estimate": True})
        if fact.as_of is None and ev.as_of is not None:
            fact = fact.model_copy(update={"as_of": ev.as_of})
        return fact, ""
    if fact.entity_id is None:
        return None, "the source is not bound to the confirmed company"
    if fact.entity_id != company_id:
        return None, f"the source is about {fact.entity_id}, not the confirmed company"
    if not any(b in policy.CORROBORATING_IDENTIFIERS for b in fact.identity_basis):
        return None, "the source is attached on a name alone, not a corroborating identifier"
    return fact, ""


def screen_company_record(
    company: CompanyRecord,
    evidence: Iterable[Evidence] = (),
    disputed_evidence_ids: Iterable[str] = (),
) -> tuple[CompanyRecord, dict[str, str]]:
    """The company record restricted to entity-bound, adequate fields.

    Returns the screened record and, for each field that was dropped, why.
    Fields whose evidence is part of a conflicting claim component are marked
    disputed.
    """
    index = {e.id: e for e in evidence}
    disputed = set(disputed_evidence_ids)
    fields: dict[str, FieldFact] = {}
    dropped: dict[str, str] = {}
    for name in sorted(company.fields):
        bound, why = _bind_field(company.fields[name], company.entity_id, index)
        if bound is None:
            dropped[name] = why
            continue
        if bound.evidence_id in disputed and not bound.disputed:
            bound = bound.model_copy(update={"disputed": True})
        fields[name] = bound
    alternatives: dict[str, list[FieldFact]] = {}
    for name, alts in sorted(company.field_alternatives.items()):
        kept = [b for b, _ in (_bind_field(a, company.entity_id, index) for a in alts) if b]
        if kept:
            alternatives[name] = kept
    record = company.model_copy(update={"fields": fields, "field_alternatives": alternatives})
    return record, dropped


def evaluate_case_criteria(
    criteria: list[Criterion],
    company: CompanyRecord,
    *,
    today: date | None = None,
    evidence: Iterable[Evidence] = (),
    disputed_evidence_ids: Iterable[str] = (),
) -> list[CriterionEvaluation]:
    screened, dropped = screen_company_record(company, evidence, disputed_evidence_ids)
    out: list[CriterionEvaluation] = []
    for c in criteria:
        if c.field in dropped:
            out.append(
                CriterionEvaluation(
                    criterion_id=c.id,
                    kind=c.kind,
                    result=CriterionResult.UNKNOWN,
                    verified=False,
                    reason=f"{c.field}: {dropped[c.field]}",
                    evidence_ids=[
                        e for e in [company.fields[c.field].evidence_id] if e is not None
                    ],
                )
            )
        else:
            out.append(evaluate_criterion(c, screened, today=today))
    return out


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


def opportunity_fit(
    criteria: list[Criterion],
    company: CompanyRecord,
    *,
    today: date | None = None,
) -> OpportunityFit:
    evaluations = [evaluate_criterion(c, company, today=today) for c in criteria]
    return fit_from_evaluations(criteria, evaluations)


def fit_from_evaluations(
    criteria: list[Criterion], evaluations: list[CriterionEvaluation]
) -> OpportunityFit:
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


def assess_candidate(
    criteria: list[Criterion],
    company: CompanyRecord,
    *,
    today: date | None = None,
) -> CandidateAssessment:
    """Apply the gate and fit. Call again after enrichment: the gate re-applies."""
    return _candidate(criteria, company, opportunity_fit(criteria, company, today=today))


def assess_case_candidate(
    criteria: list[Criterion],
    company: CompanyRecord,
    *,
    today: date | None = None,
    evidence: Iterable[Evidence] = (),
    disputed_evidence_ids: Iterable[str] = (),
) -> CandidateAssessment:
    """Gate and fit for a case: every criterion recomputed from evidence bound
    to the confirmed company and adequate for a criterion. Disputed fields are
    unknown; stale fails are not verified."""
    evaluations = evaluate_case_criteria(
        criteria,
        company,
        today=today,
        evidence=evidence,
        disputed_evidence_ids=disputed_evidence_ids,
    )
    return _candidate(criteria, company, fit_from_evaluations(criteria, evaluations))


def _candidate(
    criteria: list[Criterion], company: CompanyRecord, of: OpportunityFit
) -> CandidateAssessment:
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
