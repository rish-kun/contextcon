"""Evaluate: five separate judgments and the screening disposition.

The judgments are never blended into one score. ``assess`` is the single entry
point that turns case inputs into an immutable ``AssessmentVersion``.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import timedelta

from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    ComponentState,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    Disposition,
    IdentityStatus,
)
from app.domain.types import (
    AssessmentInputs,
    AssessmentVersion,
    BusinessAssessment,
    BusinessInputs,
    CheckOutcome,
    CheckSufficiency,
    Claim,
    Criterion,
    CriterionEvaluation,
    DispositionDecision,
    Evidence,
    EvidenceSufficiency,
    ExtractedFact,
    FinancialAssessment,
    FinancialFigure,
    Judgments,
    OpportunityFit,
    Signal,
)
from app.rules import policy
from app.rules.claim_status import combine_states, decide_claim_status, document_for, status_label
from app.rules.company_type import classify_company, required_checks
from app.rules.compare import normalize_text
from app.rules.fit import assess_case_candidate, fit_from_evaluations, must_have_failures
from app.rules.requests import build_request_list
from app.rules.validation import screen_fact

_BLOCKING_REQUIRED = frozenset(
    {ClaimStatus.CONTRADICTED, ClaimStatus.CONFLICTING_EVIDENCE, ClaimStatus.NOT_CHECKED}
)


# --- Evidence sufficiency ------------------------------------------------------


def _check_result(states: list[ComponentState]) -> ClaimStatus:
    """Same precedence as a compound claim: conflicting before contradicted."""
    if states and all(s is ComponentState.NOT_CHECKED for s in states):
        return ClaimStatus.NOT_CHECKED
    return combine_states(states)


def evidence_sufficiency(
    company_type: CompanyType,
    outcomes: list[CheckOutcome],
    claims: dict[str, Claim] | None = None,
) -> EvidenceSufficiency:
    """Share of required checks that adequate evidence settled (supported or
    contradicted). Adequacy and the substantive result are recorded separately."""
    claims = claims or {}
    by_check: dict[ClaimCategory, list[tuple[CheckOutcome, str, ComponentState]]] = defaultdict(
        list
    )
    for o in outcomes:
        for f in o.components:
            by_check[f.check].append((o, f.component, f.state))

    checks: list[CheckSufficiency] = []
    gaps: list[str] = []
    for check in required_checks(company_type):
        entries = by_check.get(check, [])
        label = check.value.replace("_", " ")
        if not entries:
            doc = policy.CATEGORY_DOCUMENTS[check]
            gap = f"{label}: not claimed and not checked"
            checks.append(
                CheckSufficiency(
                    check=check,
                    adequate=False,
                    result=None,
                    gap=gap,
                    settle_with=[doc],
                    covered_in_v1=check in policy.V1_COVERED_CHECKS,
                )
            )
            gaps.append(gap)
            continue
        states = [s for _, _, s in entries]
        adequate = all(s in (ComponentState.MATCHED, ComponentState.CONTRADICTED) for s in states)
        result = _check_result(states)
        claim_ids = list(dict.fromkeys(o.claim_id for o, _, _ in entries))
        settle: list[str] = []
        if not adequate:
            for o, comp, s in entries:
                if s in (ComponentState.MATCHED, ComponentState.CONTRADICTED):
                    continue
                claim = claims.get(o.claim_id)
                doc = (
                    document_for(comp, claim)
                    if claim
                    else (
                        policy.COMPONENT_RULES[comp].document
                        if comp in policy.COMPONENT_RULES
                        else policy.CATEGORY_DOCUMENTS[check]
                    )
                )
                if doc not in settle:
                    settle.append(doc)
        gap = None if adequate else f"{label}: {status_label(result)}"
        if gap:
            gaps.append(gap)
        checks.append(
            CheckSufficiency(
                check=check,
                adequate=adequate,
                result=result,
                claim_ids=claim_ids,
                gap=gap,
                settle_with=settle,
                covered_in_v1=check in policy.V1_COVERED_CHECKS,
            )
        )
    settled = sum(1 for c in checks if c.adequate)
    pct = round(100 * settled / len(checks)) if checks else 0
    return EvidenceSufficiency(company_type=company_type, pct=pct, checks=checks, gaps=gaps)


# --- Business assessment (signals) --------------------------------------------

BUSINESS_NOTE = (
    "Observed operating signals, not confirmed results. Headcount and hiring come from "
    "professional profiles and job listings; they are never treated as revenue."
)


def business_assessment(inputs: BusinessInputs) -> BusinessAssessment:
    signals: list[Signal] = []
    series = sorted(inputs.headcount_series, key=lambda p: (p.date, p.evidence_id))
    if series:
        latest = series[-1]
        signals.append(
            Signal(
                label="Headcount estimate (professional profiles)",
                value=int(latest.value),
                as_of=latest.date,
                evidence_ids=[latest.evidence_id],
            )
        )
        earlier = [p for p in series if p.date <= latest.date - timedelta(days=330)]
        if earlier and earlier[-1].value > 0:
            base = earlier[-1]
            change = round(100 * (latest.value - base.value) / base.value, 1)
            signals.append(
                Signal(
                    label=f"Headcount change since {base.date.isoformat()} (estimate)",
                    value=f"{change:+.1f}%",
                    as_of=latest.date,
                    evidence_ids=[base.evidence_id, latest.evidence_id],
                )
            )
    if inputs.open_roles is not None and inputs.open_roles.value is not None:
        signals.append(
            Signal(
                label="Open roles (hiring activity)",
                value=inputs.open_roles.value,
                as_of=inputs.open_roles.as_of,
                evidence_ids=[e for e in [inputs.open_roles.evidence_id] if e],
            )
        )
    if inputs.locations:
        signals.append(
            Signal(
                label="Locations on record",
                value=sorted({str(loc.value) for loc in inputs.locations}),
                evidence_ids=sorted({x.evidence_id for x in inputs.locations if x.evidence_id}),
            )
        )
    for e in sorted(inputs.events, key=lambda e: (e.date, e.label, e.evidence_id)):
        signals.append(
            Signal(
                label=f"Dated event: {e.label}",
                value=e.date.isoformat(),
                as_of=e.date,
                evidence_ids=[e.evidence_id],
            )
        )
    return BusinessAssessment(signals=signals, note=BUSINESS_NOTE)


# --- Financial assessment ------------------------------------------------------

NOT_ASSESSED = "Not assessed: no reliable financial inputs (audited statements or registry filings)"


def financial_assessment(
    facts: list[ExtractedFact], entity_ids: list[str] | None = None
) -> FinancialAssessment:
    """Only figures from audited statements or registry filings, bound to the
    company (``entity_ids``) on a corroborating identifier and with their
    quotes verified: the same screen claims use. Without entity ids nothing
    can be attached, so nothing is assessed. Headcount and hiring never enter here."""
    figures: dict[str, FinancialFigure] = {}
    for f in sorted(facts, key=lambda f: f.id):
        rule = policy.COMPONENT_RULES.get(f.component)
        if rule is None or rule.check is not ClaimCategory.FINANCIALS:
            continue
        src = f.evidence.source
        if src.reliability not in policy.RELIABLE_FINANCIAL_SOURCES:
            continue
        if not screen_fact(f, list(entity_ids or [])).valid:
            continue
        figures.setdefault(
            f.id,
            FinancialFigure(
                component=f.component,
                value=f.value,
                as_of=f.evidence.as_of,
                evidence_id=f.evidence.id,
                source_label=src.label,
            ),
        )
    if not figures:
        return FinancialAssessment(assessed=False, reason=NOT_ASSESSED)
    return FinancialAssessment(
        assessed=True,
        reason=f"Based on {len(figures)} figure(s) from audited statements or registry filings",
        figures=list(figures.values()),
        assumptions=[
            "Figures are taken as reported in the cited documents, without adjustment",
            "No valuation, forecast or fair value is implied",
        ],
    )


# --- Disposition -----------------------------------------------------------------


_CONTRADICTED_STATUSES = frozenset({ClaimStatus.CONTRADICTED, ClaimStatus.CONFLICTING_EVIDENCE})
_UNVERIFIED_STATUSES = frozenset(
    {ClaimStatus.CANNOT_VERIFY, ClaimStatus.PARTIALLY_CORROBORATED, ClaimStatus.NOT_CHECKED}
)


def _blocks_prioritise(key: str) -> bool:
    return policy.DISPOSITION_RULES[key].outcome is Disposition.INVESTIGATE_FURTHER


def _material_blocking(covered_required: set[ClaimCategory]) -> dict[ClaimStatus, bool]:
    """Which material claim statuses block Prioritise, from the disposition table.
    A contradicted or conflicting material claim blocks wherever it sits; an
    unverified one blocks outside the v1-covered required checks (inside them the
    required-check rule already applies)."""
    out: dict[ClaimStatus, bool] = {}
    if _blocks_prioritise("contradicted_optional_claim"):
        out.update(dict.fromkeys(_CONTRADICTED_STATUSES, True))
    if _blocks_prioritise("unverified_optional_claim"):
        out.update(dict.fromkeys(_UNVERIFIED_STATUSES, False))
    return out


def _complete(c: CheckSufficiency) -> bool:
    return c.adequate and c.result is ClaimStatus.SUPPORTED


def decide_disposition(
    identity_status: IdentityStatus,
    fit: OpportunityFit,
    sufficiency: EvidenceSufficiency,
    must_failures: list[str],
    *,
    outcomes: list[CheckOutcome] | None = None,
    claims: dict[str, Claim] | None = None,
) -> DispositionDecision:
    """Predicates in fixed precedence; the first that holds decides.

    1. cannot_assess        identity not confirmed, or too little of the thesis assessable
    2. deprioritise         a must-have verifiably failed, or poor fit on verified evidence
    3. prioritise           strong fit, every v1-covered required check complete, and no
                            material claim contradicted or conflicting anywhere
    4. investigate_further  everything else (attractive, evidence incomplete)

    Missing evidence never reaches rule 2: unknowns never fail a criterion,
    disputed criteria are unknown, estimate-based and stale results are
    excluded from the poor-fit test, and claim statuses do not feed it at all.
    Pass ``outcomes`` (and ``claims`` for materiality) so the whole ledger is
    considered, not only the required checks.
    """
    if identity_status is not IdentityStatus.CONFIRMED:
        return DispositionDecision(
            disposition=Disposition.CANNOT_ASSESS,
            rule="identity_uncertain",
            reasons=[
                f"Identity is {identity_status.value}: records cannot be attached to the "
                "company safely"
            ],
        )
    if fit.fit is None or fit.assessable_pct < policy.CANNOT_ASSESS_MAX_ASSESSABLE:
        return DispositionDecision(
            disposition=Disposition.CANNOT_ASSESS,
            rule="essential_information_missing",
            reasons=[
                f"Only {fit.assessable_pct}% of the criteria can be assessed "
                f"(minimum {policy.CANNOT_ASSESS_MAX_ASSESSABLE}%)"
            ],
        )
    if must_failures:
        return DispositionDecision(
            disposition=Disposition.DEPRIORITISE,
            rule="requirement_failed",
            reasons=list(must_failures),
        )
    if (
        fit.verified_fit is not None
        and fit.verified_fit < policy.DEPRIORITISE_MAX_FIT
        and fit.verified_assessable_pct >= policy.DEPRIORITISE_MIN_ASSESSABLE
    ):
        return DispositionDecision(
            disposition=Disposition.DEPRIORITISE,
            rule="poor_fit_on_good_evidence",
            reasons=[
                f"Verified fit {fit.verified_fit} is below {policy.DEPRIORITISE_MAX_FIT} with "
                f"{fit.verified_assessable_pct}% of the criteria verified"
            ],
        )

    claims = claims or {}
    blocking = [
        c for c in sufficiency.checks if c.result is not None and c.result in _BLOCKING_REQUIRED
    ]
    # Every required check v1 covers must be complete. An absent check
    # (result None) or a skipped one is a gap, never a pass.
    incomplete = [
        c
        for c in sufficiency.checks
        if c.check in policy.V1_COVERED_CHECKS and not _complete(c) and c not in blocking
    ]
    covered_required = {c.check for c in sufficiency.checks if c.check in policy.V1_COVERED_CHECKS}
    statuses = _material_blocking(covered_required)
    material = [
        o
        for o in outcomes or []
        if o.status in statuses
        and (statuses[o.status] or o.category not in covered_required)
        and (claims.get(o.claim_id) is None or claims[o.claim_id].material)
    ]
    unverified_musts = (
        [
            e
            for e in fit.evaluations
            if e.kind is CriterionKind.MUST and e.result is CriterionResult.UNKNOWN
        ]
        if _blocks_prioritise("unverified_mandatory_criterion")
        else []
    )
    strong = fit.fit >= policy.PRIORITISE_MIN_FIT
    if strong and not incomplete and not blocking and not material and not unverified_musts:
        return DispositionDecision(
            disposition=Disposition.PRIORITISE,
            rule="strong_fit_checks_satisfied",
            reasons=[
                fit.label,
                "Every required check within what v1 covers is settled by adequate evidence "
                f"({sufficiency.pct}% of all required checks)",
            ],
        )

    reasons = [fit.label]
    if not strong:
        reasons.append(f"Fit is below {policy.PRIORITISE_MIN_FIT}")
    for c in incomplete:
        label = c.check.value.replace("_", " ")
        state = "not claimed and not checked" if c.result is None else status_label(c.result)
        reasons.append(f"Required check {label}: {state}")
    for c in blocking:
        label = c.check.value.replace("_", " ")
        reasons.append(f"Required check {label}: {status_label(c.result)}")
    for o in material:
        reasons.append(f"Material claim {o.claim_id}: {status_label(o.status)}")
    for e in unverified_musts:
        reasons.append(f"Must-have criterion {e.criterion_id}: not verified")
    return DispositionDecision(
        disposition=Disposition.INVESTIGATE_FURTHER,
        rule="evidence_incomplete",
        reasons=reasons,
    )


def must_have_failure_reasons(
    criteria: list[Criterion], evaluations: list[CriterionEvaluation]
) -> list[str]:
    """The exclusion reasons ``assess_case_candidate`` gives, in the same words."""
    labels = {c.id: c.label for c in criteria}
    return [
        f"Must-have failed: {labels[e.criterion_id]} ({e.reason})"
        for e in must_have_failures(evaluations)
    ]


def _single_required_value(c: Criterion) -> object | None:
    """The one value a criterion requires, when it requires exactly one."""
    if c.operator is CriterionOperator.IS_TRUE:
        return True
    if c.operator is CriterionOperator.EQ:
        return c.value
    if c.operator in (CriterionOperator.IN, CriterionOperator.CONTAINS_ANY):
        values = c.value if isinstance(c.value, list | tuple) else [c.value]
        return values[0] if len(values) == 1 else None
    return None


def _same_value(claimed: object, required: object) -> bool:
    if isinstance(required, bool) or isinstance(claimed, bool):
        return str(claimed).strip().lower() == str(required).strip().lower()
    return normalize_text(str(claimed)) == normalize_text(str(required))


def contradicted_must_haves(
    criteria: list[Criterion],
    evaluations: list[CriterionEvaluation],
    outcomes: list[CheckOutcome],
    claims: dict[str, Claim],
) -> list[str]:
    """Verified must-have failures that come from claim checks (POLICY.md §5).

    A Contradicted claim whose component maps to a must-have's dimension
    (``policy.COMPONENT_CRITERION_DIMENSIONS``) is a verified failure of that
    must-have when the claimed value is exactly the one the criterion requires.
    Needs the claims (for their component values); a must-have that already
    failed is not counted twice."""
    if policy.DISPOSITION_RULES["verified_mandatory_failure"].outcome is not (
        Disposition.DEPRIORITISE
    ):
        return []
    failed = {e.criterion_id for e in must_have_failures(evaluations)}
    musts = [
        c for c in criteria if c.kind is CriterionKind.MUST and c.dimension and c.id not in failed
    ]
    reasons: list[str] = []
    seen: set[str] = set()
    for o in outcomes:
        claim = claims.get(o.claim_id)
        if o.status is not ClaimStatus.CONTRADICTED or claim is None:
            continue
        claimed = {c.name: c for c in claim.components}
        for f in o.components:
            dimension = policy.COMPONENT_CRITERION_DIMENSIONS.get(f.component)
            component = claimed.get(f.component)
            if f.state is not ComponentState.CONTRADICTED or not dimension or component is None:
                continue
            if component.op != "eq":
                continue
            for c in musts:
                required = _single_required_value(c)
                if (
                    c.dimension == dimension
                    and c.id not in seen
                    and required is not None
                    and _same_value(component.value, required)
                ):
                    seen.add(c.id)
                    reasons.append(
                        f"Must-have failed: {c.label} (claim {o.claim_id} contradicted "
                        f"on {f.component.replace('_', ' ')})"
                    )
    return reasons


def redecide(
    *,
    identity_status: IdentityStatus,
    company_type: CompanyType,
    outcomes: list[CheckOutcome],
    evaluations: list[CriterionEvaluation],
    criteria: list[Criterion],
    claims: dict[str, Claim],
) -> tuple[OpportunityFit, EvidenceSufficiency, DispositionDecision]:
    """Fit, evidence sufficiency and the disposition from already-decided claim
    outcomes and criterion evaluations. ``assess`` calls it with the real values
    and DecisionFlip with some of them forced, so a hypothetical and a real
    disposition always come from the same rules. ``criteria`` supplies weights
    and labels."""
    fit = fit_from_evaluations(criteria, evaluations)
    sufficiency = evidence_sufficiency(company_type, outcomes, claims)
    decision = decide_disposition(
        identity_status,
        fit,
        sufficiency,
        must_have_failure_reasons(criteria, evaluations)
        + contradicted_must_haves(criteria, evaluations, outcomes, claims),
        outcomes=outcomes,
        claims=claims,
    )
    return fit, sufficiency, decision


# --- Versioned assessment -------------------------------------------------------


def inputs_hash(inputs: AssessmentInputs) -> str:
    """sha256 of the canonical inputs and policy version. The version number is
    left out, so re-running unchanged inputs gives the same hash."""
    data = inputs.model_dump(mode="json", exclude={"version"})
    payload = {"policy_version": policy.POLICY_VERSION, "inputs": data}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _evidence_index(inputs: AssessmentInputs) -> list[Evidence]:
    seen: dict[str, Evidence] = {}
    for e in inputs.evidence:
        seen.setdefault(e.id, e)
    for c in inputs.claim_checks:
        for f in c.facts:
            seen.setdefault(f.evidence.id, f.evidence)
    for f in inputs.financial_facts:
        seen.setdefault(f.evidence.id, f.evidence)
    return [seen[k] for k in sorted(seen)]


def assess(inputs: AssessmentInputs) -> AssessmentVersion:
    """Case inputs → one immutable assessment version. Same inputs, same output.

    Claims, fit and the financial assessment all use the same screened
    evidence: every fact and field passes the identity guard for the
    confirmed company before it can count.
    """
    outcomes = [decide_claim_status(c) for c in inputs.claim_checks]
    claims = {c.claim.id: c.claim for c in inputs.claim_checks}
    evidence = _evidence_index(inputs)
    disputed = sorted(
        {
            eid
            for o in outcomes
            for f in o.components
            if f.state is ComponentState.CONFLICTING
            for eid in f.decisive_evidence_ids
        }
    )
    candidate = assess_case_candidate(
        inputs.criteria,
        inputs.company,
        today=inputs.today,
        evidence=evidence,
        disputed_evidence_ids=disputed,
    )
    ctype = classify_company(
        inputs.profile.founded_year,
        inputs.profile.headcount,
        inputs.profile.funding_stage,
        inputs.today,
    )
    _, sufficiency, decision = redecide(
        identity_status=inputs.identity_status,
        company_type=ctype.company_type,
        outcomes=outcomes,
        evaluations=candidate.fit.evaluations,
        criteria=inputs.criteria,
        claims=claims,
    )
    business = business_assessment(inputs.business)
    financial = financial_assessment(
        [f for c in inputs.claim_checks for f in c.facts] + list(inputs.financial_facts),
        [inputs.company.entity_id],
    )
    requests = build_request_list(
        outcomes,
        claims,
        inputs.identity_status,
        financial,
        financials_required=ClaimCategory.FINANCIALS in required_checks(ctype.company_type),
    )
    return AssessmentVersion(
        case_id=inputs.case_id,
        version=inputs.version,
        policy_version=policy.POLICY_VERSION,
        inputs_hash=inputs_hash(inputs),
        company_type=ctype,
        candidate=candidate,
        outcomes=outcomes,
        judgments=Judgments(
            opportunity_fit=candidate.fit,
            evidence_sufficiency=sufficiency,
            business=business,
            financial=financial,
            disposition=decision,
        ),
        disposition=decision.disposition,
        requests=requests,
    )
