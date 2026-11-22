"""DecisionFlip: the deterministic counterfactual evaluator (design F, POLICY.md §9).

Pure tests. Most cases build an ``AssessmentVersion`` from claim outcomes and
criterion evaluations through ``redecide`` (the same code ``assess`` uses), so
each scenario states exactly the statuses it needs; the PRD fixture runs end to
end from ``AssessmentInputs``.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.domain import (
    AssessmentVersion,
    BusinessAssessment,
    CandidateAssessment,
    CheckOutcome,
    Claim,
    ClaimCategory,
    ClaimComponent,
    ClaimStatus,
    CompanyType,
    CompanyTypeDecision,
    ComponentFinding,
    ComponentState,
    Criterion,
    CriterionEvaluation,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    Disposition,
    FinancialAssessment,
    IdentityStatus,
    Judgments,
    NotCheckedReason,
    RequestList,
)
from app.rules import (
    FLIP_VERSION,
    POLICY_VERSION,
    DecisionFlipAnalysis,
    FlipSearch,
    FlipState,
    ItemClass,
    ItemKind,
    ItemOutcome,
    NextAction,
    ReplayMismatch,
    analyse,
    assess,
    policy,
    redecide,
)
from app.rules.decision_flip import _enumerate, _normalise, _Runner, rank
from app.rules.evaluate import must_have_failure_reasons
from tests.rules.test_evaluate import PRD_INPUTS

C = ClaimCategory
S = ClaimStatus
MUST, PREF = CriterionKind.MUST, CriterionKind.PREFERENCE

COMPONENTS = {
    C.IDENTITY_INCORPORATION: ["incorporation_year"],
    C.LOCATION: ["hq_city"],
    C.TEAM_SIZE: ["employee_count"],
    C.LEADERSHIP_HISTORY: ["role", "employer"],
    C.FUNDING: ["raised", "round_year"],
    C.DATED_EVENT: ["event"],
    C.CUSTOMER_PARTNERSHIP: ["counterparty"],
    C.FINANCIALS: ["revenue"],
    C.DEBT_SECURITY: ["has_debt"],
}

_STATE = {
    S.SUPPORTED: ComponentState.MATCHED,
    S.CONTRADICTED: ComponentState.CONTRADICTED,
    S.CANNOT_VERIFY: ComponentState.UNSETTLED,
    S.CONFLICTING_EVIDENCE: ComponentState.CONFLICTING,
    S.NOT_CHECKED: ComponentState.NOT_CHECKED,
}


def oc(
    claim_id: str,
    category: ClaimCategory,
    status: ClaimStatus = S.SUPPORTED,
    *,
    reason: NotCheckedReason | None = None,
) -> CheckOutcome:
    names = COMPONENTS[category]
    if status is S.PARTIALLY_CORROBORATED:
        names = names if len(names) > 1 else [*names, names[0]]
        states = [ComponentState.MATCHED] + [ComponentState.UNSETTLED] * (len(names) - 1)
    else:
        states = [_STATE[status]] * len(names)
    return CheckOutcome(
        claim_id=claim_id,
        category=category,
        status=status,
        reason=f"Claim text of {claim_id} would be here",
        settle_with=[] if status is S.SUPPORTED else [policy.CATEGORY_DOCUMENTS[category]],
        components=[
            ComponentFinding(component=n, check=category, state=s)
            for n, s in zip(names, states, strict=True)
        ],
        not_checked_reason=reason,
        analyst_retry=reason in (NotCheckedReason.BUDGET_EXHAUSTED, NotCheckedReason.SOURCE_ERROR),
    )


def crit(
    cid: str, kind: CriterionKind, result: CriterionResult, *, verified: bool = True
) -> tuple[Criterion, CriterionEvaluation]:
    return (
        Criterion(
            id=cid, label=f"Label {cid}", kind=kind, field=cid, operator=CriterionOperator.IS_TRUE
        ),
        CriterionEvaluation(
            criterion_id=cid,
            kind=kind,
            result=result,
            verified=verified and result is not CriterionResult.UNKNOWN,
            reason=f"{cid} is {result.value}",
        ),
    )


P, F, U = CriterionResult.PASS, CriterionResult.FAIL, CriterionResult.UNKNOWN
GOOD = [crit("geo", MUST, P), crit("ind", MUST, P), crit("ent", PREF, P)]  # fit 100


def startup_supported(**override: ClaimStatus) -> list[CheckOutcome]:
    cats = {
        "c-inc": C.IDENTITY_INCORPORATION,
        "c-founder": C.LEADERSHIP_HISTORY,
        "c-team": C.TEAM_SIZE,
        "c-fund": C.FUNDING,
    }
    return [
        oc(cid, cat, override.get(cid.replace("-", "_"), S.SUPPORTED)) for cid, cat in cats.items()
    ]


def build(
    outcomes: list[CheckOutcome],
    crits: list[tuple[Criterion, CriterionEvaluation]] = GOOD,
    *,
    ctype: CompanyType = CompanyType.STARTUP,
    identity: IdentityStatus = IdentityStatus.CONFIRMED,
    claims: dict[str, Claim] | None = None,
    financial_assessed: bool = False,
    case_id: str = "case-t",
) -> AssessmentVersion:
    criteria = [c for c, _ in crits]
    evaluations = [e for _, e in crits]
    fit, sufficiency, decision = redecide(
        identity_status=identity,
        company_type=ctype,
        outcomes=outcomes,
        evaluations=evaluations,
        criteria=criteria,
        claims=claims or {},
    )
    failures = must_have_failure_reasons(criteria, evaluations)
    labels = {c.id: c.label for c in criteria}
    return AssessmentVersion(
        case_id=case_id,
        version=1,
        policy_version=POLICY_VERSION,
        inputs_hash=f"hash-{case_id}",
        company_type=CompanyTypeDecision(company_type=ctype, reason="test"),
        candidate=CandidateAssessment(
            entity_id="co",
            name="Co",
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
            financial=FinancialAssessment(assessed=financial_assessed, reason="test"),
            disposition=decision,
        ),
        disposition=decision.disposition,
        requests=RequestList(questions=[], documents=[], analyst_retries=[]),
    )


def run(version: AssessmentVersion, crits=GOOD, **kw) -> DecisionFlipAnalysis:
    return analyse(version, criteria=[c for c, _ in crits], **kw)


def item(a: DecisionFlipAnalysis, item_id: str):
    return next(i for i in a.items if i.id == item_id)


def blockers(a: DecisionFlipAnalysis) -> list[str]:
    return [i.id for i in a.items if i.decision_blocker]


def all_outcomes(a: DecisionFlipAnalysis) -> list[ItemOutcome]:
    out = [a.ceiling]
    out += [o for i in a.items for o in (i.if_supported, i.if_contradicted) if o is not None]
    out += [s.outcome for s in a.minimal_sets]
    if a.worst_if_contradicted is not None:
        out.append(a.worst_if_contradicted)
    return out


# --- 1. No blockers ---


def test_no_blockers_when_already_prioritise():
    claims = {
        "c-other": Claim(
            id="c-other",
            text="We are well liked",
            category=C.DATED_EVENT,
            components=[ClaimComponent(name="event", value="x")],
            material=False,
        )
    }
    v = build([*startup_supported(), oc("c-other", C.DATED_EVENT, S.CANNOT_VERIFY)], claims=claims)
    a = run(v, claims=claims)
    assert v.disposition is Disposition.PRIORITISE
    assert a.state is FlipState.NO_BLOCKERS and a.target is None
    assert blockers(a) == [] and a.minimal_sets == [] and a.minimum_evidence is None
    assert a.next_best_action.action is NextAction.NONE
    assert a.next_best_action.text == "No open item stands in the way of Prioritise."
    other = item(a, "claim:c-other")
    assert other.classification is ItemClass.NON_BLOCKING
    assert other.if_supported.disposition is Disposition.PRIORITISE
    assert not other.if_supported.changes_disposition


# --- 2. Multiple blockers ---


def test_two_blockers_neither_flips_alone():
    v = build(startup_supported(c_team=S.CANNOT_VERIFY, c_fund=S.PARTIALLY_CORROBORATED))
    a = run(v)
    assert a.current is Disposition.INVESTIGATE_FURTHER
    assert a.state is FlipState.HAS_BLOCKERS and a.target is Disposition.PRIORITISE
    assert blockers(a) == ["claim:c-fund", "claim:c-team"]
    for i in ("claim:c-fund", "claim:c-team"):
        assert not item(a, i).flips_alone
        assert item(a, i).required_in_every_path
        assert item(a, i).classification is ItemClass.DECISION_BLOCKER
    assert [s.item_ids for s in a.minimal_sets] == [["claim:c-fund", "claim:c-team"]]
    chosen = a.minimum_evidence
    assert [d.document for d in chosen.documents] == [policy.DOC_FUNDING, policy.DOC_PAYROLL]
    assert chosen.outcome.disposition is Disposition.PRIORITISE
    assert chosen.hypothetical is True and chosen.outcome.hypothetical is True
    assert a.next_best_action.action is NextAction.REQUEST_DOCUMENTS
    assert a.next_best_action.text == (
        "Request 2 documents that settle the 2 decision blockers, rather than everything open."
    )
    assert a.search is FlipSearch.EXHAUSTIVE and a.greedy is False


def test_two_claims_settled_by_one_document():
    outcomes = [
        *startup_supported(c_fund=S.CANNOT_VERIFY),
        oc("c-fund-2", C.FUNDING, S.PARTIALLY_CORROBORATED),
    ]
    a = run(build(outcomes))
    assert [s.item_ids for s in a.minimal_sets] == [["claim:c-fund", "claim:c-fund-2"]]
    docs = a.minimum_evidence.documents
    assert [(d.document, d.item_ids) for d in docs] == [
        (policy.DOC_FUNDING, ["claim:c-fund", "claim:c-fund-2"])
    ]
    assert a.next_best_action.text.startswith("Request 1 document that settles the 2 decision")


def test_alternative_paths_give_two_minimal_sets():
    # fit 67 (2 of 3 weight); either unknown preference passing lifts it to 75.
    crits = [crit("geo", MUST, P), crit("p1", PREF, F), crit("u1", PREF, U), crit("u2", PREF, U)]
    a = run(build(startup_supported(), crits), crits)
    assert a.current is Disposition.INVESTIGATE_FURTHER and a.target is Disposition.PRIORITISE
    assert [s.item_ids for s in a.minimal_sets] == [["criterion:u1"], ["criterion:u2"]]
    for i in ("criterion:u1", "criterion:u2"):
        assert item(a, i).decision_blocker and item(a, i).flips_alone
        assert not item(a, i).required_in_every_path
    assert a.minimum_evidence.item_ids == ["criterion:u1"]
    # Criteria are settled by sourced records, not by the seller.
    assert a.next_best_action.action is NextAction.ANALYST_FOLLOW_UP


# --- 3. Unsupported claims ---


def test_contradicted_and_conflicting_material_claims():
    outcomes = [
        *startup_supported(),
        oc("c-event", C.DATED_EVENT, S.CONTRADICTED),
        oc("c-cust", C.CUSTOMER_PARTNERSHIP, S.CONFLICTING_EVIDENCE),
    ]
    a = run(build(outcomes))
    assert a.current is Disposition.INVESTIGATE_FURTHER and a.target is Disposition.PRIORITISE
    event, cust = item(a, "claim:c-event"), item(a, "claim:c-cust")
    assert event.current_state == "contradicted" and event.if_contradicted is None
    assert event.if_supported.disposition is Disposition.INVESTIGATE_FURTHER
    assert [s.item_ids for s in a.minimal_sets] == [["claim:c-cust", "claim:c-event"]]
    # Policy §5: a claim never leads to Deprioritise.
    assert not event.disqualifier_risk and not cust.disqualifier_risk
    assert cust.if_contradicted.disposition is Disposition.INVESTIGATE_FURTHER
    assert cust.locks_target and not event.locks_target
    assert a.worst_if_contradicted.disposition is Disposition.INVESTIGATE_FURTHER


# --- 4. Missing evidence ---


def test_required_check_never_claimed_and_checks_that_did_not_run():
    outcomes = [
        oc("c-inc", C.IDENTITY_INCORPORATION),
        oc("c-team", C.TEAM_SIZE, S.NOT_CHECKED, reason=NotCheckedReason.SOURCE_UNAVAILABLE),
        oc(
            "c-founder",
            C.LEADERSHIP_HISTORY,
            S.NOT_CHECKED,
            reason=NotCheckedReason.BUDGET_EXHAUSTED,
        ),
    ]  # no funding claim at all
    a = run(build(outcomes))
    gap = item(a, "check:funding")
    assert gap.kind is ItemKind.CHECK_GAP and gap.current_state == "absent"
    assert gap.settle_with == [policy.CATEGORY_DOCUMENTS[C.FUNDING]]
    assert gap.decision_blocker and gap.required_in_every_path
    retry = item(a, "claim:c-founder")
    assert retry.analyst_retry and not retry.seller_resolvable and retry.settle_with == []
    assert item(a, "claim:c-team").settle_with == [policy.DOC_PAYROLL]
    assert set(a.minimum_evidence.item_ids) == {
        "check:funding",
        "claim:c-founder",
        "claim:c-team",
    }
    assert a.next_best_action.action is NextAction.RERUN_CHECKS
    assert a.next_best_action.text.startswith("Re-run 1 check that did not run.")


def test_missing_financial_inputs_are_non_blocking():
    outcomes = [
        oc("c-inc", C.IDENTITY_INCORPORATION),
        oc("c-loc", C.LOCATION),
        oc("c-team", C.TEAM_SIZE),
        oc("c-founder", C.LEADERSHIP_HISTORY),
    ]  # financials and customers are required but not covered by v1
    a = run(build(outcomes, ctype=CompanyType.ESTABLISHED))
    assert a.current is Disposition.PRIORITISE and a.state is FlipState.NO_BLOCKERS
    fin = item(a, "financial_inputs")
    assert fin.classification is ItemClass.NON_BLOCKING and fin.if_contradicted is None
    assert fin.settle_with == [policy.DOC_FINANCIAL_INPUTS]
    assert item(a, "check:financials").classification is ItemClass.NON_BLOCKING
    assert item(a, "check:customer_partnership").classification is ItemClass.NON_BLOCKING


# --- 5. Disqualifying criteria ---


def test_unknown_must_have_is_a_disqualifier_risk():
    crits = [*GOOD, crit("hq", MUST, U)]
    a = run(build(startup_supported(c_team=S.CANNOT_VERIFY), crits), crits)
    hq = item(a, "criterion:hq")
    assert hq.disqualifier_risk and not hq.decision_blocker
    assert hq.classification is ItemClass.DISQUALIFIER_RISK
    assert hq.if_contradicted.disposition is Disposition.DEPRIORITISE
    assert hq.if_contradicted.rule == "requirement_failed"
    assert a.worst_if_contradicted.disposition is Disposition.DEPRIORITISE
    assert blockers(a) == ["claim:c-team"]


def test_unknown_preference_is_never_a_disqualifier_risk():
    crits = [crit("geo", MUST, P), *(crit(f"p{i}", PREF, F) for i in range(3)), crit("u", PREF, U)]
    a = run(build(startup_supported(), crits), crits)
    u = item(a, "criterion:u")
    # Its fail would bring poor fit on verified evidence; the outcome says so, the
    # class does not (only an unknown must-have is a disqualifier risk).
    assert u.if_contradicted.disposition is Disposition.DEPRIORITISE
    assert not u.disqualifier_risk and u.classification is ItemClass.NON_BLOCKING


def test_verified_must_have_failure_is_disqualified_and_not_simulated():
    crits = [crit("geo", MUST, F), crit("ind", MUST, P), crit("x", PREF, U)]
    a = run(build(startup_supported(c_team=S.CANNOT_VERIFY), crits), crits)
    assert a.current is Disposition.DEPRIORITISE and a.state is FlipState.DISQUALIFIED
    assert a.target is None and a.minimal_sets == []
    assert all(i.if_supported is None and i.if_contradicted is None for i in a.items)
    assert all(i.classification is ItemClass.NON_BLOCKING for i in a.items)
    assert a.next_best_action.action is NextAction.REVIEW_DISQUALIFIER
    assert "Must-have failed: Label geo" in a.next_best_action.text


# --- 7. Identity unresolved ---


def test_identity_unresolved():
    reason = NotCheckedReason.IDENTITY_UNRESOLVED
    outcomes = [
        oc("c-inc", C.IDENTITY_INCORPORATION, S.NOT_CHECKED, reason=reason),
        oc("c-founder", C.LEADERSHIP_HISTORY, S.NOT_CHECKED, reason=reason),
        oc("c-team", C.TEAM_SIZE, S.NOT_CHECKED, reason=reason),
        oc("c-fund", C.FUNDING, S.NOT_CHECKED, reason=reason),
    ]
    v = build(outcomes, identity=IdentityStatus.AMBIGUOUS)
    a = run(v, identity_status=IdentityStatus.AMBIGUOUS)
    assert a.current is Disposition.CANNOT_ASSESS
    assert a.target is Disposition.INVESTIGATE_FURTHER
    assert a.ceiling.disposition is Disposition.PRIORITISE
    assert a.items[0].id == "identity" and a.items[0].current_state == "ambiguous"
    assert [s.item_ids for s in a.minimal_sets] == [["identity"]]
    assert a.minimum_evidence.documents[0].document == policy.DOC_IDENTITY
    assert item(a, "identity").flips_alone and item(a, "identity").if_contradicted is None
    for cid in ("c-inc", "c-founder", "c-team", "c-fund"):
        assert item(a, f"claim:{cid}").depends_on == ["identity"]
    assert a.next_best_action.action is NextAction.RESOLVE_IDENTITY
    assert a.next_best_action.text == (
        "Confirm the legal entity first; 4 checks cannot run until then."
    )
    # The identity status is read from the version when not passed.
    assert run(v) == a


# --- 8. Not evidence-limited ---


def test_poor_fit_on_known_criteria_is_not_evidence_limited():
    # fit 4 of 7 = 57, every criterion known; verified fit is not poor enough to deprioritise.
    crits = [crit("a", MUST, P), crit("b", MUST, P), *(crit(f"p{i}", PREF, F) for i in range(3))]
    a = run(build(startup_supported(c_team=S.CANNOT_VERIFY), crits), crits)
    assert a.current is Disposition.INVESTIGATE_FURTHER
    assert a.state is FlipState.NOT_EVIDENCE_LIMITED and a.target is None
    assert blockers(a) == [] and a.minimum_evidence is None
    assert a.ceiling.disposition is Disposition.INVESTIGATE_FURTHER
    assert a.next_best_action.action is NextAction.NONE
    assert "Fit is below 70" in a.next_best_action.text


# --- 9. Greedy path ---


def _greedy_outcomes() -> list[CheckOutcome]:
    return [
        *startup_supported(
            c_inc=S.CANNOT_VERIFY,
            c_founder=S.CANNOT_VERIFY,
            c_team=S.CANNOT_VERIFY,
            c_fund=S.PARTIALLY_CORROBORATED,
        ),
        oc("c-e1", C.DATED_EVENT, S.CONFLICTING_EVIDENCE),
        oc("c-e2", C.DATED_EVENT, S.CONFLICTING_EVIDENCE),
        oc("c-cust", C.CUSTOMER_PARTNERSHIP, S.CONFLICTING_EVIDENCE),
        oc("c-cust2", C.CUSTOMER_PARTNERSHIP, S.CONFLICTING_EVIDENCE),
        oc("c-debt", C.DEBT_SECURITY, S.CANNOT_VERIFY),  # changes nothing
    ]


def test_greedy_search_above_six_candidates_is_irreducible():
    v = build(_greedy_outcomes())
    a = run(v)
    assert len(a.items) == 9
    assert a.search is FlipSearch.GREEDY and a.greedy is True
    assert len(a.minimal_sets) == 1
    chosen = a.minimum_evidence.item_ids
    assert "claim:c-debt" not in chosen and len(chosen) == 8
    assert a.minimum_evidence.outcome.disposition is Disposition.PRIORITISE
    # Irreducible: dropping any member no longer reaches the target.
    base = _normalise(v, None, None, None)
    runner = _Runner(base, _enumerate(base))
    for drop in chosen:
        rest = {i: "supported" for i in chosen if i != drop}
        assert rank(runner.run(rest).disposition) < rank(Disposition.PRIORITISE)
    assert a.evaluations <= 3 * len(a.items) + 2 + 2 * len(a.items) ** 2
    assert analyse(v).model_dump_json() == a.model_dump_json()


def test_greedy_result_does_not_depend_on_input_order():
    a = run(build(_greedy_outcomes()))
    b = run(build(list(reversed(_greedy_outcomes()))))
    assert [i.id for i in a.items] == [i.id for i in b.items]
    assert [i.classification for i in a.items] == [i.classification for i in b.items]
    assert [s.item_ids for s in a.minimal_sets] == [s.item_ids for s in b.minimal_sets]
    assert a.next_best_action == b.next_best_action
    assert a.analysis_key == b.analysis_key


# --- 10. Determinism ---


def test_same_inputs_same_output_and_key():
    a, b = analyse(PRD_INPUTS), analyse(PRD_INPUTS)
    assert a == b
    assert a.model_dump_json() == b.model_dump_json()
    assert a.flip_version == FLIP_VERSION and a.policy_version == POLICY_VERSION
    assert a.inputs_hash == assess(PRD_INPUTS).inputs_hash
    assert len(a.analysis_key) == 64


def test_analysis_key_changes_when_materiality_changes():
    v = assess(PRD_INPUTS)
    claims = {c.claim.id: c.claim for c in PRD_INPUTS.claim_checks}
    criteria = PRD_INPUTS.criteria
    a = analyse(v, claims=claims, criteria=criteria)
    flipped = dict(claims, **{"c-debt": claims["c-debt"].model_copy(update={"material": False})})
    b = analyse(v, claims=flipped, criteria=criteria)
    assert a.analysis_key != b.analysis_key
    assert analyse(v, claims=claims, criteria=criteria).analysis_key == a.analysis_key


# --- 11. One code path ---


def test_prd_case_end_to_end():
    a = analyse(PRD_INPUTS)
    assert a.current is Disposition.INVESTIGATE_FURTHER
    assert a.current_rule == "evidence_incomplete"
    assert a.target is Disposition.PRIORITISE
    assert blockers(a) == ["claim:c-employees"]
    assert item(a, "claim:c-employees").flips_alone
    assert a.minimum_evidence.documents[0].document == policy.DOC_PAYROLL
    # Not covered by v1, so not blocking (design note 2).
    assert item(a, "check:financials").classification is ItemClass.NON_BLOCKING
    assert item(a, "financial_inputs").classification is ItemClass.NON_BLOCKING
    assert item(a, "claim:c-debt").classification is ItemClass.NON_BLOCKING


def test_inputs_version_and_stored_payload_give_the_same_analysis():
    v = assess(PRD_INPUTS)
    claims = {c.claim.id: c.claim for c in PRD_INPUTS.claim_checks}
    from_inputs = analyse(PRD_INPUTS)
    from_version = analyse(v, claims=claims, criteria=PRD_INPUTS.criteria)
    stored = {"assessment": v.model_dump(mode="json"), "today": "2026-11-22"}
    from_payload = analyse(stored, claims=claims, criteria=PRD_INPUTS.criteria)
    # Without claims or criteria: every claim material, kind-default weights.
    from_skeleton = analyse(v.model_dump(mode="json"))
    assert from_inputs == from_version == from_payload
    assert [i.id for i in from_skeleton.items] == [i.id for i in from_inputs.items]
    assert from_skeleton.minimum_evidence == from_inputs.minimum_evidence


@pytest.mark.parametrize(
    "version",
    [
        build(startup_supported()),
        build(startup_supported(c_team=S.CANNOT_VERIFY)),
        build([oc("c-inc", C.IDENTITY_INCORPORATION)], identity=IdentityStatus.UNRESOLVED),
        build(startup_supported(), [crit("geo", MUST, F)]),
    ],
)
def test_redecide_reproduces_the_stored_decision(version):
    a = analyse(version)
    stored = version.judgments.disposition
    assert (a.current, a.current_rule, a.current_reasons) == (
        stored.disposition,
        stored.rule,
        stored.reasons,
    )


def test_redecide_reproduces_assess():
    v = assess(PRD_INPUTS)
    _, _, decision = redecide(
        identity_status=PRD_INPUTS.identity_status,
        company_type=v.company_type.company_type,
        outcomes=v.outcomes,
        evaluations=v.candidate.fit.evaluations,
        criteria=PRD_INPUTS.criteria,
        claims={c.claim.id: c.claim for c in PRD_INPUTS.claim_checks},
    )
    assert decision == v.judgments.disposition


def test_a_version_the_rules_do_not_reproduce_is_rejected():
    v = build(startup_supported(c_team=S.CANNOT_VERIFY))
    tampered = v.model_copy(
        update={
            "judgments": v.judgments.model_copy(
                update={
                    "disposition": v.judgments.disposition.model_copy(
                        update={"disposition": Disposition.PRIORITISE}
                    )
                }
            )
        }
    )
    with pytest.raises(ReplayMismatch):
        analyse(tampered)


# --- 12. Hypothetical marking ---


def test_every_simulated_output_is_hypothetical():
    for a in (
        analyse(PRD_INPUTS),
        run(build(startup_supported(c_team=S.CANNOT_VERIFY, c_fund=S.CANNOT_VERIFY))),
        run(build(_greedy_outcomes())),
    ):
        assert a.hypothetical is True
        assert all(o.hypothetical is True for o in all_outcomes(a))
        assert all(s.hypothetical is True for s in a.minimal_sets)
        assert json.loads(a.model_dump_json())["hypothetical"] is True


def test_schema_rejects_a_non_hypothetical_outcome():
    with pytest.raises(ValidationError):
        ItemOutcome(
            hypothetical=False,
            disposition=Disposition.PRIORITISE,
            rule="x",
            reasons=[],
            changes_disposition=True,
        )


# --- 13. No leakage ---


def test_claim_text_never_reaches_the_analysis():
    checks = [
        c.model_copy(
            update={"claim": c.claim.model_copy(update={"text": f"MARKER-9F {c.claim.text}"})}
        )
        for c in PRD_INPUTS.claim_checks
    ]
    inputs = PRD_INPUTS.model_copy(update={"claim_checks": checks})
    assert "MARKER-9F" in assess(inputs).model_dump_json()  # outcomes quote it
    assert "MARKER-9F" not in analyse(inputs).model_dump_json()
