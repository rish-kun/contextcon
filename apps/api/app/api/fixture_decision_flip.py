"""DecisionFlip fixtures, computed by the real rules (`rules.decision_flip.analyse`).

Each scenario builds an assessment version from claim outcomes and criterion
evaluations through `redecide` (the code `assess` uses), so the fixture panels show
exactly what the backend would return. Claim ids are the Harbourline fixture's where a
scenario stands for that case; labels and claim text are added as the API adds them.

Scenarios (keys of `scenarios()`, exported to apps/web/lib/api/fixtures.json):
    two_blockers       founder history cannot verify + funding partly corroborated
    no_blockers        Prioritise already; a non-material event claim stays open
    disqualifier_risk  an unknown must-have criterion (a verified fail would exclude)
    mapped_claim_risk  an unverified ownership claim behind the "Privately held"
                       must-have: contradicted, it is a verified failure (Deprioritise)
    threshold_unknown  an unknown revenue threshold: both branches stated
    identity           identity ambiguous: confirm the entity first
    not_evidence_limited  fit below 70 with every criterion known
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.api.schemas.decision_flip import DecisionFlipOut, FlipResolutionItemOut, FlipResolutionOut
from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    ComponentState,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    IdentityStatus,
    NotCheckedReason,
)
from app.domain.types import (
    AssessmentVersion,
    BusinessAssessment,
    CandidateAssessment,
    CheckOutcome,
    Claim,
    ClaimComponent,
    CompanyTypeDecision,
    ComponentFinding,
    Criterion,
    CriterionEvaluation,
    DecisionFlipAnalysis,
    FinancialAssessment,
    Judgments,
    RequestList,
)
from app.rules import POLICY_VERSION, policy
from app.rules.decision_flip import analyse
from app.rules.evaluate import must_have_failure_reasons, redecide

C, S = ClaimCategory, ClaimStatus
MUST, PREF = CriterionKind.MUST, CriterionKind.PREFERENCE
P, F, U = CriterionResult.PASS, CriterionResult.FAIL, CriterionResult.UNKNOWN

CREATED = datetime(2026, 11, 22, 10, 12, tzinfo=UTC)

_STATE = {
    S.SUPPORTED: ComponentState.MATCHED,
    S.CONTRADICTED: ComponentState.CONTRADICTED,
    S.CANNOT_VERIFY: ComponentState.UNSETTLED,
    S.CONFLICTING_EVIDENCE: ComponentState.CONFLICTING,
    S.NOT_CHECKED: ComponentState.NOT_CHECKED,
}

# Harbourline's claim ids (fixtures.claims): category, wording, label, components.
CLAIMS: dict[str, tuple[ClaimCategory, str, str, tuple[str, ...]]] = {
    "fx-claim-1": (
        C.IDENTITY_INCORPORATION,
        "Incorporated in 2016",
        "Incorporation",
        ("incorporation_year",),
    ),
    "fx-claim-2": (C.TEAM_SIZE, "We employ 300 people", "Team size", ("employee_count",)),
    "fx-claim-3": (
        C.LEADERSHIP_HISTORY,
        "Our founder ran operations at a national courier firm",
        "Founder history",
        ("role", "employer"),
    ),
    "fx-claim-4": (
        C.FUNDING,
        "We raised our Series A in 2024",
        "Series A funding",
        ("raised", "round_year"),
    ),
    "fx-claim-5": (
        C.DATED_EVENT,
        "We opened a cold-storage facility in Nashik in August 2026",
        "Nashik facility",
        ("event",),
    ),
    "fx-claim-6": (
        C.IDENTITY_INCORPORATION,
        "We are a privately held company",
        "Ownership",
        ("ownership",),
    ),
}
CLAIM_VALUES = {"ownership": "Private"}


@dataclass(frozen=True)
class _Crit:
    kind: CriterionKind
    label: str
    dimension: str
    operator: CriterionOperator = CriterionOperator.EQ
    value: object = None
    optional: bool = False  # only in scenarios that name it


CRITERIA: dict[str, _Crit] = {
    "fx-crit-1": _Crit(MUST, "Headquartered in India", "geography", value="India"),
    "fx-crit-2": _Crit(MUST, "Privately held", "ownership", value="private"),
    "fx-crit-3": _Crit(PREF, "Serves enterprise customers", "customer_type", value="enterprise"),
    "fx-crit-4": _Crit(PREF, "Recent expansion", "growth_signal", CriterionOperator.IS_TRUE),
    "fx-crit-5": _Crit(
        MUST,
        "Revenue at least INR 50 crore",
        "other",
        CriterionOperator.GTE,
        500_000_000,
        optional=True,
    ),
}


def _outcome(
    claim_id: str, status: ClaimStatus, reason: NotCheckedReason | None = None
) -> CheckOutcome:
    category, _, _, names = CLAIMS[claim_id]
    if status is S.PARTIALLY_CORROBORATED:
        states = [ComponentState.MATCHED] + [ComponentState.UNSETTLED] * (len(names) - 1)
    else:
        states = [_STATE[status]] * len(names)
    return CheckOutcome(
        claim_id=claim_id,
        category=category,
        status=status,
        reason="Fixture",
        settle_with=[] if status is S.SUPPORTED else [policy.CATEGORY_DOCUMENTS[category]],
        components=[
            ComponentFinding(component=n, check=category, state=s)
            for n, s in zip(names, states, strict=True)
        ],
        not_checked_reason=reason if status is S.NOT_CHECKED else None,
    )


def _claims(material: dict[str, bool] | None = None) -> dict[str, Claim]:
    return {
        cid: Claim(
            id=cid,
            text=text,
            category=cat,
            components=[ClaimComponent(name=n, value=CLAIM_VALUES.get(n, "x")) for n in names],
            material=(material or {}).get(cid, True),
        )
        for cid, (cat, text, _, names) in CLAIMS.items()
    }


def _criteria(results: dict[str, CriterionResult]) -> list[tuple[Criterion, CriterionEvaluation]]:
    return [
        (
            Criterion(
                id=cid,
                label=c.label,
                kind=c.kind,
                field=cid,
                operator=c.operator,
                value=c.value,
                dimension=c.dimension,
            ),
            CriterionEvaluation(
                criterion_id=cid,
                kind=c.kind,
                result=results.get(cid, P),
                verified=results.get(cid, P) is not U,
                reason="Fixture",
            ),
        )
        for cid, c in CRITERIA.items()
        if not c.optional or cid in results
    ]


def fixture_version(
    case_id: str,
    version: int,
    statuses: dict[str, ClaimStatus],
    results: dict[str, CriterionResult] | None = None,
    *,
    identity: IdentityStatus = IdentityStatus.CONFIRMED,
    material: dict[str, bool] | None = None,
) -> tuple[AssessmentVersion, dict[str, Claim], list[Criterion]]:
    """An assessment version whose disposition comes from `redecide`, with the claims
    and criteria behind it."""
    crits = _criteria(results or {})
    criteria = [c for c, _ in crits]
    evaluations = [e for _, e in crits]
    claims = _claims(material)
    reason = None if identity is IdentityStatus.CONFIRMED else NotCheckedReason.IDENTITY_UNRESOLVED
    outcomes = [_outcome(cid, st, reason) for cid, st in statuses.items()]
    fit, sufficiency, decision = redecide(
        identity_status=identity,
        company_type=CompanyType.STARTUP,
        outcomes=outcomes,
        evaluations=evaluations,
        criteria=criteria,
        claims=claims,
    )
    failures = must_have_failure_reasons(criteria, evaluations)
    labels = {c.id: c.label for c in criteria}
    v = AssessmentVersion(
        case_id=case_id,
        version=version,
        policy_version=POLICY_VERSION,
        inputs_hash=f"fixture-{case_id}-{version}",
        company_type=CompanyTypeDecision(company_type=CompanyType.STARTUP, reason="Fixture"),
        candidate=CandidateAssessment(
            entity_id="900001",
            name="Harbourline Warehousing (fixture)",
            excluded=bool(failures),
            exclusion_reasons=failures,
            fit=fit,
            unknown_criteria=[labels[e.criterion_id] for e in evaluations if e.result is U],
        ),
        outcomes=outcomes,
        judgments=Judgments(
            opportunity_fit=fit,
            evidence_sufficiency=sufficiency,
            business=BusinessAssessment(signals=[], note=""),
            financial=FinancialAssessment(assessed=False, reason="Fixture"),
            disposition=decision,
        ),
        disposition=decision.disposition,
        requests=RequestList(questions=[], documents=[], analyst_retries=[]),
    )
    return v, claims, criteria


def _analyse(
    case_id: str,
    version: int,
    statuses: dict[str, ClaimStatus],
    results: dict[str, CriterionResult] | None = None,
    *,
    identity: IdentityStatus = IdentityStatus.CONFIRMED,
    material: dict[str, bool] | None = None,
) -> DecisionFlipAnalysis:
    v, claims, criteria = fixture_version(
        case_id, version, statuses, results, identity=identity, material=material
    )
    return analyse(v, claims=claims, criteria=criteria, identity_status=identity)


SUPPORTED = {cid: S.SUPPORTED for cid in ("fx-claim-1", "fx-claim-3", "fx-claim-2", "fx-claim-4")}


def _label(item_id: str) -> tuple[str, str | None]:
    kind, _, ref = item_id.partition(":")
    if kind == "claim" and ref in CLAIMS:
        return CLAIMS[ref][2], CLAIMS[ref][1]
    if kind == "criterion" and ref in CRITERIA:
        return CRITERIA[ref].label, None
    if kind == "check":
        return f"{ref.replace('_', ' ').capitalize()} (not claimed yet)", None
    if item_id == "identity":
        return "Legal entity", None
    return "Financial inputs", None


def present(
    analysis: DecisionFlipAnalysis, *, analysis_id: str, resolution: FlipResolutionOut | None
) -> DecisionFlipOut:
    out = DecisionFlipOut.model_validate(
        {
            **analysis.model_dump(mode="json"),
            "analysis_id": analysis_id,
            "blocker_count": sum(1 for i in analysis.items if i.decision_blocker),
            "created_at": CREATED,
            "resolution": resolution,
        }
    )
    items = []
    for item in out.items:
        label, text = _label(item.id)
        items.append(item.model_copy(update={"label": label, "claim_text": text}))
    return out.model_copy(update={"items": items})


def _two_blockers(case_id: str) -> DecisionFlipOut:
    a = _analyse(
        case_id,
        2,
        {**SUPPORTED, "fx-claim-3": S.CANNOT_VERIFY, "fx-claim-4": S.PARTIALLY_CORROBORATED},
    )
    # Version 1 also had the team size open; the payroll summary settled it.
    resolution = FlipResolutionOut(
        previous_version=1,
        previous_blockers=3,
        resolved_blockers=1,
        items=[
            FlipResolutionItemOut(
                item_id="claim:fx-claim-2",
                label=CLAIMS["fx-claim-2"][2],
                outcome="resolved",
                was_blocker=True,
                current_state="supported",
                evidence_ids=["fx-ev-payroll"],
            ),
            FlipResolutionItemOut(
                item_id="claim:fx-claim-3",
                label=CLAIMS["fx-claim-3"][2],
                outcome="still_open",
                was_blocker=True,
                current_state="cannot_verify",
            ),
            FlipResolutionItemOut(
                item_id="claim:fx-claim-4",
                label=CLAIMS["fx-claim-4"][2],
                outcome="still_open",
                was_blocker=True,
                current_state="partially_corroborated",
            ),
        ],
    )
    return present(a, analysis_id=f"fx-flip-{case_id}", resolution=resolution)


def _no_blockers(case_id: str) -> DecisionFlipOut:
    a = _analyse(
        case_id,
        3,
        {**SUPPORTED, "fx-claim-5": S.CANNOT_VERIFY},
        material={"fx-claim-5": False},
    )
    return present(a, analysis_id=f"fx-flip-{case_id}-no-blockers", resolution=None)


def _disqualifier_risk(case_id: str) -> DecisionFlipOut:
    a = _analyse(case_id, 2, {**SUPPORTED, "fx-claim-2": S.CANNOT_VERIFY}, {"fx-crit-2": U})
    return present(a, analysis_id=f"fx-flip-{case_id}-risk", resolution=None)


def _mapped_claim_risk(case_id: str) -> DecisionFlipOut:
    a = _analyse(case_id, 2, {**SUPPORTED, "fx-claim-6": S.CANNOT_VERIFY})
    return present(a, analysis_id=f"fx-flip-{case_id}-mapped", resolution=None)


def _threshold_unknown(case_id: str) -> DecisionFlipOut:
    a = _analyse(case_id, 2, {**SUPPORTED, "fx-claim-2": S.CANNOT_VERIFY}, {"fx-crit-5": U})
    return present(a, analysis_id=f"fx-flip-{case_id}-threshold", resolution=None)


def _identity(case_id: str) -> DecisionFlipOut:
    a = _analyse(
        case_id,
        1,
        dict.fromkeys(SUPPORTED, S.NOT_CHECKED),
        identity=IdentityStatus.AMBIGUOUS,
    )
    return present(a, analysis_id=f"fx-flip-{case_id}-identity", resolution=None)


def _not_evidence_limited(case_id: str) -> DecisionFlipOut:
    a = _analyse(
        case_id,
        2,
        {**SUPPORTED, "fx-claim-2": S.CANNOT_VERIFY},
        {"fx-crit-3": F, "fx-crit-4": F},
    )
    return present(a, analysis_id=f"fx-flip-{case_id}-limited", resolution=None)


SCENARIOS: dict[str, Callable[[str], DecisionFlipOut]] = {
    "two_blockers": _two_blockers,
    "no_blockers": _no_blockers,
    "disqualifier_risk": _disqualifier_risk,
    "mapped_claim_risk": _mapped_claim_risk,
    "threshold_unknown": _threshold_unknown,
    "identity": _identity,
    "not_evidence_limited": _not_evidence_limited,
}


def scenarios(case_id: str = "fx-case-harbourline") -> dict[str, DecisionFlipOut]:
    return {name: build(case_id) for name, build in SCENARIOS.items()}
