"""Request list: every open question mapped to the document that would settle it.

Each question is about one unresolved component of a claim, and maps to the
document that settles that component (a completed round needs an allotment,
closing statement or receipt of funds, not a term sheet).

Seller requests and analyst-side work are kept apart: a check that did not run
because of budget or an error is the analyst's job to re-run, and a question
the seller cannot resolve (for example a registry charge record) is the
analyst's to follow up. Neither is sent to the seller.
"""

from __future__ import annotations

from app.domain.enums import ClaimStatus, ComponentState, IdentityStatus, NotCheckedReason
from app.domain.types import (
    AnalystRetry,
    CheckOutcome,
    Claim,
    FinancialAssessment,
    RequestItem,
    RequestList,
    RequestQuestion,
)
from app.rules import policy
from app.rules.claim_status import document_for, status_label

_DOCUMENT_SETTLEABLE = frozenset(
    {NotCheckedReason.SOURCE_UNAVAILABLE, NotCheckedReason.NO_SOURCE_IN_SCOPE}
)


_STATE_PHRASE = {
    ComponentState.UNSETTLED: "no adequate evidence settles it",
    ComponentState.CONFLICTING: "sources disagree",
    ComponentState.CONTRADICTED: "the evidence contradicts it",
    ComponentState.NOT_CHECKED: "not checked, no reachable source covers it",
}


def seller_can_resolve(component: str) -> bool:
    rule = policy.COMPONENT_RULES.get(component)
    return rule.seller_resolvable if rule is not None else True


def build_request_list(
    outcomes: list[CheckOutcome],
    claims: dict[str, Claim],
    identity_status: IdentityStatus = IdentityStatus.CONFIRMED,
    financial: FinancialAssessment | None = None,
    financials_required: bool = False,
) -> RequestList:
    """One question per unresolved claim component, each mapped to the
    document that settles that component. Whether the seller can resolve a
    question is tracked separately from its status: questions only the
    analyst can follow up go to ``analyst_questions``, never to the seller."""
    questions: list[RequestQuestion] = []
    analyst_questions: list[RequestQuestion] = []
    docs: dict[str, tuple[list[str], list[str]]] = {}
    retries: list[AnalystRetry] = []

    def ask(question: RequestQuestion, documents: list[str]) -> None:
        if not question.seller_resolvable:
            analyst_questions.append(question)
            return
        questions.append(question)
        for d in documents:
            q_ids, c_ids = docs.setdefault(d, ([], []))
            q_ids.append(question.id)
            if question.claim_id and question.claim_id not in c_ids:
                c_ids.append(question.claim_id)

    identity_q: RequestQuestion | None = None
    if identity_status is not IdentityStatus.CONFIRMED:
        identity_q = RequestQuestion(
            id="q-identity",
            text=f"Which legal entity is this? Identity is {identity_status.value}, so "
            "records cannot be attached to the company safely.",
            kind="identity",
        )
        ask(identity_q, [policy.DOC_IDENTITY])

    def ask_components(o: CheckOutcome, text: str, kind: str) -> None:
        claim = claims.get(o.claim_id)
        open_findings = [f for f in o.components if f.state is not ComponentState.MATCHED]
        if not open_findings:
            ask(
                RequestQuestion(
                    id=f"q-{o.claim_id}",
                    text=f'"{text}": {status_label(o.status)}.',
                    claim_id=o.claim_id,
                    kind=kind,
                ),
                o.settle_with,
            )
            return
        for f in open_findings:
            doc = (
                document_for(f.component, claim)
                if claim is not None
                else (
                    policy.COMPONENT_RULES[f.component].document
                    if f.component in policy.COMPONENT_RULES
                    else policy.CATEGORY_DOCUMENTS[o.category]
                )
            )
            label = f.component.replace("_", " ")
            ask(
                RequestQuestion(
                    id=f"q-{o.claim_id}:{f.component}",
                    text=f'"{text}" ({status_label(o.status)}): {label}: {_STATE_PHRASE[f.state]}.',
                    claim_id=o.claim_id,
                    kind=kind,
                    component=f.component,
                    seller_resolvable=seller_can_resolve(f.component),
                ),
                [doc],
            )

    for o in outcomes:
        claim = claims.get(o.claim_id)
        text = claim.text if claim else o.claim_id
        if o.status is ClaimStatus.SUPPORTED:
            continue
        if o.status is ClaimStatus.NOT_CHECKED:
            reason = o.not_checked_reason
            if o.analyst_retry:
                retries.append(AnalystRetry(claim_id=o.claim_id, reason=reason, detail=o.reason))
            elif reason is NotCheckedReason.IDENTITY_UNRESOLVED:
                # Settled by the identity document, then re-run.
                if identity_q is None:
                    identity_q = RequestQuestion(
                        id="q-identity",
                        text="Which legal entity is this? Some checks could not run "
                        "until identity is resolved.",
                        kind="identity",
                    )
                    ask(identity_q, [policy.DOC_IDENTITY])
                _, c_ids = docs[policy.DOC_IDENTITY]
                if o.claim_id not in c_ids:
                    c_ids.append(o.claim_id)
                retries.append(AnalystRetry(claim_id=o.claim_id, reason=reason, detail=o.reason))
            elif reason in _DOCUMENT_SETTLEABLE:
                ask_components(o, text, "unrun_check")
            continue
        ask_components(o, text, "claim")

    if financials_required and (financial is None or not financial.assessed):
        ask(
            RequestQuestion(
                id="q-financial-inputs",
                text="No reliable financial inputs: the financial assessment cannot be made.",
                kind="financial_inputs",
            ),
            [policy.DOC_FINANCIAL_INPUTS],
        )

    return RequestList(
        questions=questions,
        documents=[
            RequestItem(document=d, question_ids=q_ids, claim_ids=c_ids)
            for d, (q_ids, c_ids) in docs.items()
        ],
        analyst_retries=retries,
        analyst_questions=analyst_questions,
    )
