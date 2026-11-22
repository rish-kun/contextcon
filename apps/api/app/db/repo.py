"""Repository helpers. Every read and write is scoped to a workspace.

Rows that hang off a case (documents, claims, evidence, assessments, requests…) are
authorised through the case: a query joins `cases` and filters on its `workspace_id`.
A row in another workspace is reported as `NotFound`, never as "forbidden", so ids
from other tenants do not leak.
"""

import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.db.enums import SendStatus
from app.db.models import (
    Approval,
    AssessmentVersion,
    Case,
    Claim,
    ClaimCheck,
    ClaimCheckEvidence,
    DiscoveryRun,
    Document,
    Evidence,
    InvestorRun,
    MessageRevision,
    RequestList,
    Run,
    SendAttempt,
    Thesis,
    User,
    Workspace,
)


class NotFound(LookupError):
    """The row does not exist, or it belongs to another workspace."""


class Forbidden(PermissionError):
    """The acting user may not do this (e.g. approve in another workspace)."""


class AlreadySent(RuntimeError):
    """A send for this key, revision or request list exists. `attempt` is that send when
    it is visible to the caller's workspace, else None."""

    def __init__(self, attempt: SendAttempt | None) -> None:
        detail = f" ({attempt.status})" if attempt is not None else ""
        super().__init__(f"this message was already sent or is being sent{detail}")
        self.attempt = attempt


# --- Scoping primitives ------------------------------------------------------

_WORKSPACE_OWNED = (Thesis, DiscoveryRun, InvestorRun, Case, Run, User)


def scoped[T: Base](model: type[T], workspace_id: uuid.UUID) -> Select[tuple[T]]:
    """`SELECT model` limited to one workspace, for models that carry `workspace_id`."""
    if model not in _WORKSPACE_OWNED:
        raise TypeError(f"{model.__name__} is not workspace-owned; use case_scoped()")
    return select(model).where(model.workspace_id == workspace_id)  # type: ignore[attr-defined]


def case_scoped[T: Base](
    model: type[T], workspace_id: uuid.UUID, case_id: uuid.UUID | None = None
) -> Select[tuple[T]]:
    """`SELECT model` for a model with `case_id`, authorised through its case."""
    stmt = (
        select(model)
        .join(Case, Case.id == model.case_id)  # type: ignore[attr-defined]
        .where(Case.workspace_id == workspace_id)
    )
    if case_id is not None:
        stmt = stmt.where(model.case_id == case_id)  # type: ignore[attr-defined]
    return stmt


async def _one[T: Base](session: AsyncSession, stmt: Select[tuple[T]], what: str) -> T:
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFound(what)
    return row


# --- Tenancy -----------------------------------------------------------------


async def create_workspace(session: AsyncSession, name: str) -> Workspace:
    ws = Workspace(name=name)
    session.add(ws)
    await session.flush()
    return ws


async def create_user(
    session: AsyncSession, workspace_id: uuid.UUID, *, email: str, display_name: str
) -> User:
    user = User(workspace_id=workspace_id, email=email.lower(), display_name=display_name)
    session.add(user)
    await session.flush()
    return user


async def get_user(session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> User:
    return await _one(session, scoped(User, workspace_id).where(User.id == user_id), "user")


# --- Discover / investors ----------------------------------------------------


async def get_thesis(
    session: AsyncSession, workspace_id: uuid.UUID, thesis_id: uuid.UUID
) -> Thesis:
    stmt = (
        scoped(Thesis, workspace_id)
        .where(Thesis.id == thesis_id)
        .options(selectinload(Thesis.criteria))
    )
    return await _one(session, stmt, "thesis")


async def get_discovery_run(
    session: AsyncSession, workspace_id: uuid.UUID, discovery_run_id: uuid.UUID
) -> DiscoveryRun:
    stmt = scoped(DiscoveryRun, workspace_id).where(DiscoveryRun.id == discovery_run_id)
    return await _one(session, stmt, "discovery run")


async def get_investor_run(
    session: AsyncSession, workspace_id: uuid.UUID, investor_run_id: uuid.UUID
) -> InvestorRun:
    stmt = scoped(InvestorRun, workspace_id).where(InvestorRun.id == investor_run_id)
    return await _one(session, stmt, "investor run")


# --- Cases ---------------------------------------------------------------------


async def create_case(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    company_name: str,
    website: str | None = None,
    created_by: uuid.UUID | None = None,
    credit_budget: Decimal | float | None = None,
    **fields: Any,
) -> Case:
    case = Case(
        workspace_id=workspace_id,
        company_name=company_name,
        website=website,
        created_by=created_by,
        credit_budget=None if credit_budget is None else Decimal(str(credit_budget)),
        **fields,
    )
    session.add(case)
    await session.flush()
    return case


async def get_case(session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID) -> Case:
    return await _one(session, scoped(Case, workspace_id).where(Case.id == case_id), "case")


async def list_cases(session: AsyncSession, workspace_id: uuid.UUID) -> list[Case]:
    stmt = scoped(Case, workspace_id).order_by(Case.created_at.desc())
    return list((await session.execute(stmt)).scalars())


async def get_case_child[T: Base](
    session: AsyncSession,
    model: type[T],
    workspace_id: uuid.UUID,
    row_id: uuid.UUID,
    *,
    case_id: uuid.UUID | None = None,
) -> T:
    """Fetch any case-owned row by id, authorised through its case."""
    stmt = case_scoped(model, workspace_id, case_id).where(model.id == row_id)  # type: ignore[attr-defined]
    return await _one(session, stmt, model.__tablename__)


async def list_case_children[T: Base](
    session: AsyncSession, model: type[T], workspace_id: uuid.UUID, case_id: uuid.UUID
) -> list[T]:
    stmt = case_scoped(model, workspace_id, case_id).order_by(model.created_at)  # type: ignore[attr-defined]
    return list((await session.execute(stmt)).scalars())


async def get_document(
    session: AsyncSession, workspace_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    return await get_case_child(session, Document, workspace_id, document_id)


async def list_claims(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> list[Claim]:
    return await list_case_children(session, Claim, workspace_id, case_id)


async def add_claim_check(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    claim_id: uuid.UUID,
    status: str,
    reason: str,
    policy_version: str,
    evidence_ids: Iterable[uuid.UUID] = (),
    what_would_settle: str | None = None,
    run_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
) -> ClaimCheck:
    claim = await get_case_child(session, Claim, workspace_id, claim_id)
    check = ClaimCheck(
        claim_id=claim.id,
        case_id=claim.case_id,
        status=status,
        reason=reason,
        policy_version=policy_version,
        what_would_settle=what_would_settle,
        run_id=run_id,
        step_id=step_id,
    )
    ids = list(evidence_ids)
    if ids:
        allowed = set(
            (
                await session.execute(
                    case_scoped(Evidence, workspace_id, claim.case_id).where(Evidence.id.in_(ids))
                )
            ).scalars()
        )
        if len(allowed) != len(set(ids)):
            raise NotFound("evidence outside this case")
        check.evidence_links = [ClaimCheckEvidence(evidence_id=e.id) for e in allowed]
    session.add(check)
    await session.flush()
    return check


async def latest_claim_checks(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> dict[uuid.UUID, ClaimCheck]:
    """Current check per claim (the newest row in the append-only history)."""
    stmt = (
        case_scoped(ClaimCheck, workspace_id, case_id)
        .distinct(ClaimCheck.claim_id)
        .order_by(ClaimCheck.claim_id, ClaimCheck.created_at.desc(), ClaimCheck.id.desc())
    )
    return {c.claim_id: c for c in (await session.execute(stmt)).scalars()}


# --- Assessments (immutable, versioned) --------------------------------------


async def latest_assessment(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> AssessmentVersion | None:
    stmt = (
        case_scoped(AssessmentVersion, workspace_id, case_id)
        .order_by(AssessmentVersion.version.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def add_assessment_version(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    case_id: uuid.UUID,
    *,
    policy_version: str,
    inputs_hash: str,
    judgments: dict,
    disposition: str,
    reasons: list,
    diff_from_previous: dict | None = None,
    trigger: str = "evaluate",
    run_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> AssessmentVersion:
    """Insert the next version. Earlier versions are never touched."""
    case = await get_case(session, workspace_id, case_id)
    # Serialise version numbering per case.
    await session.execute(select(Case.id).where(Case.id == case.id).with_for_update())
    previous = await latest_assessment(session, workspace_id, case.id)
    version = AssessmentVersion(
        case_id=case.id,
        version=(previous.version + 1) if previous else 1,
        previous_version_id=previous.id if previous else None,
        policy_version=policy_version,
        inputs_hash=inputs_hash,
        judgments=judgments,
        disposition=disposition,
        reasons=reasons,
        diff_from_previous=diff_from_previous,
        trigger=trigger,
        run_id=run_id,
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return version


# --- Act: revisions, approvals, send-once ------------------------------------


async def add_message_revision(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    request_list_id: uuid.UUID,
    *,
    subject: str,
    body: str,
    recipient: str,
    created_by: uuid.UUID | None = None,
) -> MessageRevision:
    request_list = await get_case_child(session, RequestList, workspace_id, request_list_id)
    await session.execute(
        select(RequestList.id).where(RequestList.id == request_list.id).with_for_update()
    )
    current = (
        await session.execute(
            select(func.max(MessageRevision.revision)).where(
                MessageRevision.request_list_id == request_list.id
            )
        )
    ).scalar_one()
    revision = MessageRevision(
        request_list_id=request_list.id,
        case_id=request_list.case_id,
        revision=(current or 0) + 1,
        subject=subject,
        body=body,
        recipient=recipient,
        created_by=created_by,
    )
    session.add(revision)
    await session.flush()
    return revision


async def approve_revision(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    message_revision_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
) -> Approval:
    revision = await get_case_child(session, MessageRevision, workspace_id, message_revision_id)
    try:
        user = await get_user(session, workspace_id, user_id)
    except NotFound as exc:
        raise Forbidden("approver is not a member of this workspace") from exc
    approval = Approval(
        message_revision_id=revision.id, user_id=user.id, user_display_name=user.display_name
    )
    session.add(approval)
    await session.flush()
    return approval


async def begin_send(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    approval_id: uuid.UUID,
    send_key: str,
    provider: str = "resend",
) -> SendAttempt:
    """Reserve the send and commit it *before* calling the email provider.

    Raises `AlreadySent` if the key was used before, the revision was already sent, or
    the request list has a send that left or may have left (pending/sent/unknown), so
    a message leaves at most once. Build `send_key` server-side from ids the caller
    owns (e.g. `f"request-list:{id}"`). Commits the session.
    """
    found = (
        await session.execute(
            select(Approval, MessageRevision.request_list_id)
            .join(MessageRevision, MessageRevision.id == Approval.message_revision_id)
            .join(Case, Case.id == MessageRevision.case_id)
            .where(Approval.id == approval_id, Case.workspace_id == workspace_id)
        )
    ).first()
    if found is None:
        raise NotFound("approval")
    approval, request_list_id = found
    revision_id = approval.message_revision_id  # plain value: survives a rollback
    attempt = SendAttempt(
        request_list_id=request_list_id,
        message_revision_id=approval.message_revision_id,
        approval_id=approval.id,
        send_key=send_key,
        provider=provider,
        status=SendStatus.PENDING,
    )
    session.add(attempt)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(SendAttempt)
                .join(RequestList, RequestList.id == SendAttempt.request_list_id)
                .join(Case, Case.id == RequestList.case_id)
                .where(
                    Case.workspace_id == workspace_id,
                    or_(
                        SendAttempt.send_key == send_key,
                        SendAttempt.message_revision_id == revision_id,
                        SendAttempt.request_list_id == request_list_id,
                    ),
                )
                .order_by(SendAttempt.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        raise AlreadySent(existing) from None
    return attempt


async def finish_send(
    session: AsyncSession,
    attempt_id: uuid.UUID,
    *,
    status: SendStatus | str,
    provider_message_id: str | None = None,
    error: str | None = None,
) -> SendAttempt:
    attempt = await session.get(SendAttempt, attempt_id)
    if attempt is None:
        raise NotFound("send attempt")
    if attempt.status != SendStatus.PENDING:
        raise AlreadySent(attempt)
    attempt.status = SendStatus(status)
    attempt.provider_message_id = provider_message_id
    attempt.error = error
    await session.flush()
    return attempt


# --- Runs --------------------------------------------------------------------


async def get_run(
    session: AsyncSession, workspace_id: uuid.UUID, run_id: uuid.UUID, *, with_steps: bool = True
) -> Run:
    stmt = scoped(Run, workspace_id).where(Run.id == run_id)
    if with_steps:
        stmt = stmt.options(selectinload(Run.steps))
    return await _one(session, stmt, "run")
