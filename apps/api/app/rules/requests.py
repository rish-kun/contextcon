"""Request list: every open question mapped to the document that would settle it.

Seller requests and analyst-side retries are kept apart: a check that did not
run because of budget or an error is the analyst's job to re-run, not the
seller's to answer.
"""

from __future__ import annotations

from app.domain.enums import ClaimStatus, IdentityStatus, NotCheckedReason
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
from app.rules.claim_status import status_label

_DOCUMENT_SETTLEABLE = frozenset(
    {NotCheckedReason.SOURCE_UNAVAILABLE, NotCheckedReason.NO_SOURCE_IN_SCOPE}
)


def build_request_list(
    outcomes: list[CheckOutcome],
    claims: dict[str, Claim],
    identity_status: IdentityStatus = IdentityStatus.CONFIRMED,
    financial: FinancialAssessment | None = None,
    financials_required: bool = False,
) -> RequestList:
    questions: list[RequestQuestion] = []
    docs: dict[str, tuple[list[str], list[str]]] = {}
    retries: list[AnalystRetry] = []

    def ask(question: RequestQuestion, documents: list[str]) -> None:
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
                ask(
                    RequestQuestion(
                        id=f"q-{o.claim_id}",
                        text=f'"{text}": not checked, no reachable source covers it.',
                        claim_id=o.claim_id,
                        kind="unrun_check",
                    ),
                    o.settle_with,
                )
            continue
        ask(
            RequestQuestion(
                id=f"q-{o.claim_id}",
                text=f'"{text}": {status_label(o.status)}.',
                claim_id=o.claim_id,
                kind="claim",
            ),
            o.settle_with,
        )

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
    )
