"""Request list (Act, part 1): open questions → requested documents → drafted email.

`build_request_list_for_case` takes the case's latest assessment version, runs its
outcomes through `rules.build_request_list`, and stores:

- one `request_lists` row tied to that assessment version;
- one `request_items` row per requested document (deduplicated by the rules), each
  linked through `request_item_claims` to the claims it would settle;
- revision 1 of the seller email in `message_revisions`, drafted by
  `drafting.draft_seller_email`. It is a draft: no recipient (a person types it in),
  no approval. The request list *is* the Act message (`message_id == request_list.id`),
  so the Act router edits, approves and sends it.

Items are stored blocker-first (`rules.request_priority`): documents in the version's
DecisionFlip minimum evidence set, then other decision blockers, disqualifier risks and
the rest, ties broken by estimated effort. `build_request_list` still decides what is
requested; the analysis only orders and labels it (`priority`, `priority_reason`), and
without one the order is unchanged. The analysis is the one the `evaluate.decision_flip`
step stored for the version, else computed in memory (`pipelines.act.flip`).

It is idempotent per assessment version: asking again for the same version returns the
stored list, so a re-run step or a double-click never drafts (or pays for) a second one.

Retention: claim text is never copied into these tables. Question texts are rendered on
read from the `claims` rows, so the retention sweep's scrubbing shows through.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Case, Claim, MessageRevision, RequestItem, RequestItemClaim, RequestList
from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    IdentityStatus,
    NotCheckedReason,
    PriorityReason,
)
from app.domain.types import AssessmentVersion, CheckOutcome
from app.domain.types import Claim as DomainClaim
from app.drafting.seller_email import (
    RequestItem as EmailItem,
)
from app.drafting.seller_email import (
    SellerEmail,
    SellerEmailRequest,
    draft_seller_email,
    fallback_email,
)
from app.extraction.llm import DraftingLlm
from app.pipelines.act.flip import analysis_for_version
from app.pipelines.evaluate import stored_assessment
from app.pipelines.evaluate.inputs import load_claim_checks
from app.rules import build_request_list, policy
from app.rules.claim_status import status_label
from app.rules.company_type import required_checks
from app.rules.request_priority import RANK_NON_BLOCKING, Priority, group_label, prioritise

IDENTITY_QUESTION = (
    "Which legal entity is this? Records cannot be attached to the company until its "
    "identity is confirmed."
)
FINANCIAL_QUESTION = "No reliable financial inputs: the financial assessment cannot be made."


class NoAssessment(LookupError):
    """The case has no assessment version yet, so there is nothing to ask for."""


@dataclass
class ItemView:
    """One requested document as the API and the email show it."""

    document: str
    reason: str
    categories: list[str]
    claim_ids: list[str]
    questions: list[str]
    priority: int = RANK_NON_BLOCKING
    priority_reason: PriorityReason = PriorityReason.NON_BLOCKING
    # Seller-facing conditional sentences (both outcomes) for financial or threshold items.
    conditions: list[str] = field(default_factory=list)

    @property
    def needed(self) -> bool:
        """Listed under "Needed to complete our screening"."""
        return self.priority_reason is PriorityReason.DECISION_BLOCKER

    @property
    def group(self) -> str:
        return group_label(self.priority_reason)

    def apply(self, priority: Priority) -> ItemView:
        self.priority = priority.rank
        self.priority_reason = priority.reason
        self.conditions = list(priority.conditions)
        if self.conditions:
            # Both outcomes, never "this makes the company qualify".
            self.reason = f"{self.reason}. {' '.join(self.conditions)}"
        return self


@dataclass
class Context:
    """Everything the rendering needs from one assessment version."""

    version: VersionRow
    assessment: AssessmentVersion
    outcomes: dict[str, CheckOutcome]
    claims: dict[str, Claim]
    needs_financial_inputs: bool
    retries: list[tuple[str, NotCheckedReason | None, str]] = field(default_factory=list)


# --- reading the assessment --------------------------------------------------------------


async def _claims(session: AsyncSession, case_id: uuid.UUID) -> dict[str, Claim]:
    rows = await session.execute(select(Claim).where(Claim.case_id == case_id))
    return {str(c.id): c for c in rows.scalars()}


def _needs_financial_inputs(assessment: AssessmentVersion) -> bool:
    required = ClaimCategory.FINANCIALS in required_checks(assessment.company_type.company_type)
    financial = assessment.judgments.financial
    return required and (financial is None or not financial.assessed)


async def load_context(session: AsyncSession, version: VersionRow) -> Context:
    assessment = stored_assessment(version)
    outcomes = {o.claim_id: o for o in assessment.outcomes}
    retries = [
        (o.claim_id, o.not_checked_reason, o.reason)
        for o in assessment.outcomes
        if o.status is ClaimStatus.NOT_CHECKED
        and (o.analyst_retry or o.not_checked_reason is NotCheckedReason.IDENTITY_UNRESOLVED)
    ]
    return Context(
        version=version,
        assessment=assessment,
        outcomes=outcomes,
        claims=await _claims(session, version.case_id),
        needs_financial_inputs=_needs_financial_inputs(assessment),
        retries=retries,
    )


# --- rendering (shared by the email draft and the API) -----------------------------------


def _humanise(value: str) -> str:
    return value.replace("_", " ")


def claim_question(text: str, outcome: CheckOutcome | None) -> str:
    if outcome is None:
        return f'"{text}": still open.'
    if outcome.status is ClaimStatus.NOT_CHECKED:
        if outcome.not_checked_reason is NotCheckedReason.IDENTITY_UNRESOLVED:
            return f'"{text}": not checked until the legal entity is confirmed.'
        return f'"{text}": not checked, no reachable source covers it.'
    return f'"{text}": {status_label(outcome.status)}.'


def render_item(document: str, claim_ids: list[str], ctx: Context) -> ItemView:
    identity = document == policy.DOC_IDENTITY
    financial = document == policy.DOC_FINANCIAL_INPUTS and ctx.needs_financial_inputs
    categories: list[str] = []
    questions: list[str] = []
    because: list[str] = []
    if identity:
        categories.append(ClaimCategory.IDENTITY_INCORPORATION.value)
        questions.append(IDENTITY_QUESTION)
        because.append("confirms which legal entity this is")
    for claim_id in claim_ids:
        claim = ctx.claims.get(claim_id)
        outcome = ctx.outcomes.get(claim_id)
        category = claim.category if claim else (outcome.category.value if outcome else None)
        if category and category not in categories:
            categories.append(category)
        questions.append(claim_question(claim.original_text if claim else "claim", outcome))
        if outcome is not None and not (
            identity and outcome.not_checked_reason is NotCheckedReason.IDENTITY_UNRESOLVED
        ):
            label = (
                "not checked"
                if outcome.status is ClaimStatus.NOT_CHECKED
                else status_label(outcome.status)
            )
            because.append(f"settles {_humanise(outcome.category.value)} ({label})")
    if financial:
        if ClaimCategory.FINANCIALS.value not in categories:
            categories.append(ClaimCategory.FINANCIALS.value)
        questions.append(FINANCIAL_QUESTION)
        because.append("gives the financial assessment reliable inputs")
    reason = "; ".join(dict.fromkeys(because)) or "settles an open question"
    return ItemView(
        document=document,
        reason=reason[0].upper() + reason[1:],
        categories=[c for c in categories if c in ClaimCategory._value2member_map_],
        claim_ids=list(claim_ids),
        questions=questions,
    )


# --- building ----------------------------------------------------------------------------


async def _existing(session: AsyncSession, version_id: uuid.UUID) -> RequestList | None:
    return (
        await session.execute(
            select(RequestList)
            .where(RequestList.assessment_version_id == version_id)
            .order_by(RequestList.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()


async def draft_email(
    llm: DraftingLlm | None, company_name: str, items: list[ItemView], *, sender_name: str | None
) -> SellerEmail:
    request = SellerEmailRequest(
        company_name=company_name,
        items=[
            EmailItem(
                id=str(n),
                document=i.document,
                reason=i.reason,
                questions=i.questions,
                needed=i.needed,
                conditions=i.conditions,
            )
            for n, i in enumerate(items, 1)
        ],
        sender_name=sender_name,
    )
    if llm is None:  # no model configured (local dev): the deterministic template
        subject, body = fallback_email(request)
        return SellerEmail(subject=subject, body=body, used_fallback=True)
    return await draft_seller_email(llm, request)


@dataclass
class BuildResult:
    request_list: RequestList
    created: bool
    used_fallback: bool = False
    item_count: int = 0
    blocker_count: int = 0  # items under "Needed to complete our screening"
    analysis_source: str = "none"  # stored | computed | none


async def build_request_list_for_case(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    case_id: uuid.UUID,
    *,
    llm: DraftingLlm | None,
    sender_name: str | None = None,
    now: datetime | None = None,
) -> BuildResult:
    """Build, draft and store the request list for the latest assessment version.

    Flushes, does not commit. Raises `repo.NotFound` for a case outside the workspace
    and `NoAssessment` before the first assessment.
    """
    case = await repo.get_case(session, workspace_id, case_id)
    version = await repo.latest_assessment(session, workspace_id, case.id)
    if version is None:
        raise NoAssessment("The case has no assessment yet; run verification first.")
    existing = await _existing(session, version.id)
    if existing is not None:
        return BuildResult(existing, created=False)

    ctx = await load_context(session, version)
    checks = await load_claim_checks(session, case)
    domain_claims: dict[str, DomainClaim] = {c.claim.id: c.claim for c in checks}
    rules_list = build_request_list(
        ctx.assessment.outcomes,
        domain_claims,
        IdentityStatus(case.identity_status),
        ctx.assessment.judgments.financial,
        financials_required=ClaimCategory.FINANCIALS
        in required_checks(ctx.assessment.company_type.company_type),
    )
    analysis, analysis_source = await analysis_for_version(
        session, case, version, ctx.assessment, domain_claims
    )
    ranked = prioritise(rules_list.documents, lambda d: (d.document, d.claim_ids), analysis)
    items = [
        render_item(d.document, [c for c in d.claim_ids if c in ctx.claims], ctx).apply(p)
        for d, p in ranked
    ]

    email = (
        await draft_email(llm, case.company_name, items, sender_name=sender_name) if items else None
    )

    # Write phase: serialise per case, then re-check (a concurrent build may have won).
    await session.execute(select(Case.id).where(Case.id == case.id).with_for_update())
    existing = await _existing(session, version.id)
    if existing is not None:
        return BuildResult(existing, created=False)

    request_list = RequestList(
        case_id=case.id,
        assessment_version_id=version.id,
        status="draft" if items else "nothing_to_request",
    )
    if now is not None:
        request_list.created_at = now
    session.add(request_list)
    await session.flush()
    for position, item in enumerate(items):
        row = RequestItem(
            request_list_id=request_list.id,
            position=position,
            category=item.categories[0] if item.categories else ClaimCategory.OTHER.value,
            document_requested=item.document,
            reason=item.reason,
            priority=item.priority,
            priority_reason=item.priority_reason.value,
        )
        row.claim_links = [RequestItemClaim(claim_id=uuid.UUID(c)) for c in item.claim_ids]
        session.add(row)
    if email is not None:
        session.add(
            MessageRevision(
                request_list_id=request_list.id,
                case_id=case.id,
                revision=1,
                subject=email.subject,
                body=email.body,
                recipient="",  # typed in by a person before approval
                created_by=None,  # drafted by DealProof, not by a user
            )
        )
    await session.flush()
    return BuildResult(
        request_list,
        created=True,
        used_fallback=bool(email and email.used_fallback),
        item_count=len(items),
        blocker_count=sum(1 for i in items if i.needed),
        analysis_source=analysis_source,
    )


# --- reading back ------------------------------------------------------------------------


@dataclass
class StoredRequestList:
    request_list: RequestList
    version: VersionRow
    items: list[tuple[RequestItem, ItemView]]
    retries: list[tuple[str, NotCheckedReason | None, str, str]]  # id, reason, detail, text
    first_revision: MessageRevision | None


async def load_request_list(session: AsyncSession, request_list: RequestList) -> StoredRequestList:
    if request_list.assessment_version_id is None:
        raise NoAssessment("This request list is not tied to an assessment version.")
    version = await session.get(VersionRow, request_list.assessment_version_id)
    if version is None:  # pragma: no cover - assessment versions are never deleted
        raise NoAssessment("The assessment version behind this list is gone.")
    ctx = await load_context(session, version)
    rows = (
        await session.execute(
            select(RequestItem)
            .where(RequestItem.request_list_id == request_list.id)
            .order_by(RequestItem.position)
        )
    ).scalars()
    items: list[tuple[RequestItem, ItemView]] = []
    for row in list(rows):
        links = (
            await session.execute(
                select(RequestItemClaim.claim_id).where(RequestItemClaim.request_item_id == row.id)
            )
        ).scalars()
        claim_ids = sorted((str(c) for c in links), key=_order_by(ctx))
        view = render_item(row.document_requested, claim_ids, ctx)
        view.reason = row.reason
        view.priority = row.priority
        view.priority_reason = PriorityReason(row.priority_reason)
        items.append((row, view))
    first = (
        await session.execute(
            select(MessageRevision)
            .where(MessageRevision.request_list_id == request_list.id)
            .order_by(MessageRevision.revision)
            .limit(1)
        )
    ).scalar_one_or_none()
    retries = [
        (
            claim_id,
            reason,
            detail,
            ctx.claims[claim_id].original_text if claim_id in ctx.claims else "",
        )
        for claim_id, reason, detail in ctx.retries
    ]
    return StoredRequestList(request_list, version, items, retries, first)


def _order_by(ctx: Context):
    """Links come back unordered; keep the assessment's claim order."""
    order = {claim_id: n for n, claim_id in enumerate(ctx.outcomes)}
    return lambda claim_id: (order.get(claim_id, len(order)), claim_id)


async def latest_request_list(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> RequestList | None:
    case = await repo.get_case(session, workspace_id, case_id)
    return (
        await session.execute(
            select(RequestList)
            .where(RequestList.case_id == case.id, RequestList.assessment_version_id.is_not(None))
            .order_by(RequestList.created_at.desc(), RequestList.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
