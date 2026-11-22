from app.domain import (
    Claim,
    ClaimCategory,
    ClaimCheck,
    ClaimComponent,
    ClaimStatus,
    FinancialAssessment,
    IdentityStatus,
    NotCheckedReason,
)
from app.rules.claim_status import decide_all
from app.rules.requests import build_request_list
from tests.rules import prd_fixtures as prd

CLAIMS = {c.claim.id: c.claim for c in prd.PRD_CHECKS}


def test_prd_request_list_three_documents():
    r = build_request_list(decide_all(prd.PRD_CHECKS), CLAIMS)
    assert [d.document for d in r.documents] == [
        "Dated payroll summary",
        "Lease or occupancy evidence for the facility",
        "Lender statements",
    ]
    assert [d.claim_ids for d in r.documents] == [["c-employees"], ["c-facility"], ["c-debt"]]
    assert r.analyst_retries == []
    assert {q.claim_id for q in r.questions} == {"c-employees", "c-facility", "c-debt"}


def test_documents_are_deduplicated_and_linked_to_every_question():
    second_team_claim = prd.EMPLOYEES.model_copy(
        update={"claim": prd.EMPLOYEES.claim.model_copy(update={"id": "c-employees-2"})}
    )
    checks = [prd.EMPLOYEES, second_team_claim]
    claims = {c.claim.id: c.claim for c in checks}
    r = build_request_list(decide_all(checks), claims)
    assert len(r.documents) == 1
    assert r.documents[0].question_ids == [
        "q-c-employees:employee_count",
        "q-c-employees-2:employee_count",
    ]
    assert r.documents[0].claim_ids == ["c-employees", "c-employees-2"]


def test_budget_and_error_skips_are_analyst_retries_not_seller_requests():
    checks = [
        ClaimCheck(
            claim=prd.FUNDING.claim, ran=False, not_run_reason=NotCheckedReason.BUDGET_EXHAUSTED
        ),
        ClaimCheck(
            claim=prd.FOUNDER_HISTORY.claim,
            ran=False,
            not_run_reason=NotCheckedReason.SOURCE_ERROR,
            not_run_detail="HTTP 503",
        ),
    ]
    r = build_request_list(decide_all(checks), CLAIMS)
    assert r.documents == []
    assert [(x.claim_id, x.reason) for x in r.analyst_retries] == [
        ("c-funding", NotCheckedReason.BUDGET_EXHAUSTED),
        ("c-founder", NotCheckedReason.SOURCE_ERROR),
    ]


def test_unrun_check_a_document_could_settle_is_requested():
    checks = [
        ClaimCheck(
            claim=prd.NO_DEBT.claim, ran=False, not_run_reason=NotCheckedReason.NO_SOURCE_IN_SCOPE
        )
    ]
    r = build_request_list(decide_all(checks), CLAIMS)
    assert [d.document for d in r.documents] == ["Lender statements"]
    assert r.questions[0].kind == "unrun_check"


def test_identity_ambiguity_and_missing_financials_become_requests():
    checks = [
        ClaimCheck(
            claim=prd.FUNDING.claim, ran=False, not_run_reason=NotCheckedReason.IDENTITY_UNRESOLVED
        )
    ]
    r = build_request_list(
        decide_all(checks),
        CLAIMS,
        IdentityStatus.AMBIGUOUS,
        FinancialAssessment(assessed=False, reason="none"),
        financials_required=True,
    )
    docs = {d.document: d for d in r.documents}
    identity = docs["Certificate of incorporation showing the CIN and registered office"]
    assert identity.question_ids == ["q-identity"]
    assert identity.claim_ids == ["c-funding"]
    assert "Audited financial statements" in docs
    assert [q.kind for q in r.questions] == ["identity", "financial_inputs"]
    assert [x.claim_id for x in r.analyst_retries] == ["c-funding"]


def test_supported_claims_ask_for_nothing():
    outcomes = decide_all([prd.INCORPORATION, prd.FUNDING])
    assert all(o.status is ClaimStatus.SUPPORTED for o in outcomes)
    r = build_request_list(outcomes, CLAIMS)
    assert r.documents == [] and r.questions == []


def test_each_question_maps_to_the_precise_unresolved_component():
    r = build_request_list(decide_all(prd.PRD_CHECKS), CLAIMS)
    assert [(q.claim_id, q.component) for q in r.questions] == [
        ("c-employees", "employee_count"),
        ("c-facility", "event_date"),
        ("c-facility", "stage"),
        ("c-debt", "has_debt"),
    ]
    # The announced facility itself is matched, so it is not asked about.
    assert all(q.component != "event" for q in r.questions)
    facility = next(d for d in r.documents if d.claim_ids == ["c-facility"])
    assert facility.question_ids == ["q-c-facility:event_date", "q-c-facility:stage"]
    assert all(q.seller_resolvable for q in r.questions)
    assert r.analyst_questions == []


def test_funding_request_asks_for_proof_of_completion_not_a_term_sheet():
    announcement_only = prd.FUNDING.model_copy(
        update={"facts": [f for f in prd.FUNDING.facts if f.evidence.id == "ev-funding-pr"]}
    )
    r = build_request_list(decide_all([announcement_only]), CLAIMS)
    assert [d.document for d in r.documents] == [
        "Share allotment filing, closing statement or bank receipt of the funds"
    ]
    assert not any("term sheet" in d.document.lower() for d in r.documents)
    assert {q.component for q in r.questions} == {"raised", "round_year", "round_type"}


def test_items_the_seller_cannot_resolve_are_not_sent_to_the_seller():
    claim = Claim(
        id="c-charge",
        text="No security has been registered over our assets",
        category=ClaimCategory.DEBT_SECURITY,
        components=[ClaimComponent(name="security_registered", value=False)],
        entity_ids=[prd.COMPANY],
    )
    checks = [ClaimCheck(claim=claim), prd.NO_DEBT]
    r = build_request_list(decide_all(checks), {c.claim.id: c.claim for c in checks})
    assert [(q.claim_id, q.component, q.seller_resolvable) for q in r.analyst_questions] == [
        ("c-charge", "security_registered", False)
    ]
    assert [d.document for d in r.documents] == ["Lender statements"]
    assert all(q.claim_id != "c-charge" for q in r.questions)
