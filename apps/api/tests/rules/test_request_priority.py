"""Blocker-first request lists (`rules.request_priority`), pure."""

from __future__ import annotations

from app.domain import (
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
)
from app.domain.enums import EffortLevel, PriorityReason
from app.domain.types import DecisionFlipAnalysis, RequestItem
from app.rules import analyse, assess, policy
from app.rules.request_priority import (
    ALSO_HELPFUL_HEADING,
    NEEDED_HEADING,
    RANK_BLOCKER,
    RANK_MINIMUM_EVIDENCE,
    RANK_NON_BLOCKING,
    RANK_RISK,
    group_label,
    item_priority,
    prioritise,
    seller_condition,
)
from tests.rules.test_decision_flip import GOOD, build, crit, oc, run, startup_supported
from tests.rules.test_evaluate import PRD_INPUTS

C, S = ClaimCategory, ClaimStatus
MUST = CriterionKind.MUST
U = CriterionResult.UNKNOWN


def _key(d: RequestItem) -> tuple[str, list[str]]:
    return d.document, d.claim_ids


def _docs(ranked) -> list[str]:
    return [d.document for d, _ in ranked]


def _flip(a: DecisionFlipAnalysis, **item_updates) -> DecisionFlipAnalysis:
    """`a` with fields of some items replaced: {item_id: {field: value}}."""
    items = [i.model_copy(update=item_updates.get(i.id, {})) for i in a.items]
    return a.model_copy(update={"items": items})


def test_without_an_analysis_nothing_moves():
    v = assess(PRD_INPUTS)
    ranked = prioritise(v.requests.documents, _key, None)
    assert _docs(ranked) == [d.document for d in v.requests.documents]
    assert {p.reason for _, p in ranked} == {PriorityReason.NON_BLOCKING}
    assert all(not p.needed for _, p in ranked)


def test_blockers_come_first_and_deduplication_holds():
    v = assess(PRD_INPUTS)
    a = analyse(PRD_INPUTS)
    original = [d.document for d in v.requests.documents]
    ranked = prioritise(v.requests.documents, _key, a)
    docs = _docs(ranked)
    # Same documents, each once: the analysis orders, it never adds or drops.
    assert sorted(docs) == sorted(original) and len(set(docs)) == len(docs)
    needed = [d.document for d, p in ranked if p.needed]
    assert set(needed) == {d.document for d in a.minimum_evidence.documents}
    assert docs[: len(needed)] == needed  # blockers before everything else
    assert docs[-1] == policy.DOC_FINANCIAL_INPUTS
    last = ranked[-1][1]
    assert last.reason is PriorityReason.NON_BLOCKING and last.rank == RANK_NON_BLOCKING


def test_minimum_evidence_documents_come_before_other_blockers():
    v = build(startup_supported(c_team=S.CANNOT_VERIFY, c_fund=S.PARTIALLY_CORROBORATED))
    a = run(v)
    chosen = {d.document for d in a.minimum_evidence.documents}
    assert chosen == {policy.DOC_FUNDING, policy.DOC_PAYROLL}
    # Keep only the chosen set's first document; the other claim stays a decision
    # blocker (it is in a minimal set) but is no longer minimum evidence.
    minimum = a.minimum_evidence.model_copy(update={"documents": a.minimum_evidence.documents[:1]})
    a = a.model_copy(update={"minimum_evidence": minimum})
    first = minimum.documents[0].document
    payroll = RequestItem(document=policy.DOC_PAYROLL, question_ids=[], claim_ids=["c-team"])
    funding = RequestItem(document=policy.DOC_FUNDING, question_ids=[], claim_ids=["c-fund"])
    ranked = prioritise([payroll, funding], _key, a)
    assert _docs(ranked)[0] == first
    ranks = {d.document: p.rank for d, p in ranked}
    assert ranks[first] == RANK_MINIMUM_EVIDENCE
    other = ({policy.DOC_PAYROLL, policy.DOC_FUNDING} - {first}).pop()
    assert ranks[other] == RANK_BLOCKER
    assert all(p.reason is PriorityReason.DECISION_BLOCKER for _, p in ranked)


def test_disqualifier_risks_come_after_blockers_and_before_the_rest():
    v = build(startup_supported(c_team=S.CANNOT_VERIFY), [*GOOD, crit("hq", MUST, U)])
    a = run(v, [*GOOD, crit("hq", MUST, U)])
    # Add a location claim that is a disqualifier risk (unresolved, on a must-have).
    risk = a.items[0].model_copy(
        update={
            "id": "claim:c-loc",
            "claim_id": "c-loc",
            "decision_blocker": False,
            "disqualifier_risk": True,
        }
    )
    a = a.model_copy(update={"items": [*a.items, risk]})
    items = [
        RequestItem(document=policy.DOC_CV, question_ids=[], claim_ids=["c-other"]),
        RequestItem(document=policy.DOC_INCORPORATION, question_ids=[], claim_ids=["c-loc"]),
        RequestItem(document=policy.DOC_PAYROLL, question_ids=[], claim_ids=["c-team"]),
    ]
    ranked = prioritise(items, _key, a)
    assert _docs(ranked) == [policy.DOC_PAYROLL, policy.DOC_INCORPORATION, policy.DOC_CV]
    assert [p.reason for _, p in ranked] == [
        PriorityReason.DECISION_BLOCKER,
        PriorityReason.DISQUALIFIER_RISK,
        PriorityReason.NON_BLOCKING,
    ]
    assert ranked[1][1].rank == RANK_RISK


def test_ties_break_by_estimated_effort_then_original_order():
    a = run(build(startup_supported()))  # nothing open: every request is non-blocking
    items = [
        RequestItem(document=policy.DOC_CUSTOMER, question_ids=[], claim_ids=["x1"]),  # high
        RequestItem(document=policy.DOC_PAYROLL, question_ids=[], claim_ids=["x2"]),  # medium
        RequestItem(document=policy.DOC_CV, question_ids=[], claim_ids=["x3"]),  # low
        RequestItem(document="Unknown document", question_ids=[], claim_ids=["x4"]),  # medium
        RequestItem(document=policy.DOC_INCORPORATION, question_ids=[], claim_ids=["x5"]),  # low
    ]
    ranked = prioritise(items, _key, a)
    assert _docs(ranked) == [
        policy.DOC_CV,
        policy.DOC_INCORPORATION,
        policy.DOC_PAYROLL,
        "Unknown document",
        policy.DOC_CUSTOMER,
    ]
    assert [p.effort for _, p in ranked] == [
        EffortLevel.LOW,
        EffortLevel.LOW,
        EffortLevel.MEDIUM,
        EffortLevel.MEDIUM,
        EffortLevel.HIGH,
    ]


def test_effort_never_beats_a_blocker():
    v = build(startup_supported(c_fund=S.CANNOT_VERIFY))
    a = run(v)
    items = [
        RequestItem(document=policy.DOC_CV, question_ids=[], claim_ids=["c-other"]),  # low
        RequestItem(document=policy.DOC_FUNDING, question_ids=[], claim_ids=["c-fund"]),  # medium
    ]
    assert _docs(prioritise(items, _key, a)) == [policy.DOC_FUNDING, policy.DOC_CV]


def test_threshold_and_financial_conditions_are_seller_safe():
    size = crit("size", MUST, U, op=CriterionOperator.GTE, value=100, label="Headcount")
    crits = [*GOOD, size]
    a = run(build(startup_supported(), crits), crits)
    threshold = next(i for i in a.items if i.id == "criterion:size").conditional_action
    assert "Hypothetically" in threshold
    said = seller_condition(threshold)
    assert said == "If the verified figure is at least 100, Headcount passes; otherwise it fails."

    outcomes = [
        oc("c-inc", C.IDENTITY_INCORPORATION),
        oc("c-loc", C.LOCATION),
        oc("c-team", C.TEAM_SIZE),
        oc("c-founder", C.LEADERSHIP_HISTORY),
        oc("c-rev", C.FINANCIALS, S.CANNOT_VERIFY),
    ]
    a = run(build(outcomes, ctype=CompanyType.ESTABLISHED))
    doc = RequestItem(document=policy.DOC_FINANCIALS, question_ids=[], claim_ids=["c-rev"])
    p = item_priority(doc.document, doc.claim_ids, a)
    assert p.needed  # a material unverified claim outside the covered checks
    assert (
        "If the verified figures match the claim, it is supported; otherwise it is contradicted."
        in p.conditions
    )
    for c in p.conditions:
        low = c.lower()
        assert "c-rev" not in c and "hypothetically" not in low and "obtain" not in low
        assert "prioriti" not in low and "qualif" not in low
        assert "otherwise" in low  # both outcomes, always


def test_group_labels():
    assert group_label(PriorityReason.DECISION_BLOCKER) == NEEDED_HEADING
    for r in (
        PriorityReason.DISQUALIFIER_RISK,
        PriorityReason.NON_BLOCKING,
        PriorityReason.ANALYST_RETRY,
    ):
        assert group_label(r) == ALSO_HELPFUL_HEADING
    assert NEEDED_HEADING == "Needed to complete our screening"


def test_a_document_settling_only_reruns_is_an_analyst_retry():
    a = run(build(startup_supported(c_fund=S.CANNOT_VERIFY)))
    a = _flip(a, **{"claim:c-fund": {"analyst_retry": True, "decision_blocker": False}})
    a = a.model_copy(update={"minimum_evidence": None})
    p = item_priority(policy.DOC_FUNDING, ["c-fund"], a)
    assert p.reason is PriorityReason.ANALYST_RETRY and not p.needed
