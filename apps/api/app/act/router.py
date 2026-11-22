"""HTTP API for the Act step. Not mounted here; the integrator includes `router`.

    POST /cases/{case_id}/messages                          create (revision 1)
    GET  /cases/{case_id}/messages/send-summary             counts per send status
    GET  /cases/{case_id}/messages/{message_id}             status, revisions, approval, send
    POST /cases/{case_id}/messages/{message_id}/revisions   edit (new revision, needs re-approval)
    POST /cases/{case_id}/messages/{message_id}/approve     approve one revision id
    POST /cases/{case_id}/messages/{message_id}/send        send once
    POST /cases/{case_id}/messages/{message_id}/reconcile   resolve an `unknown` send (no dispatch)

Errors: 404 not found, 409 conflict (`not_approved`, `stale_revision`, `send_exists`
with the existing send), 422 invalid input, 503 email not configured.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.act.deps import authorize_case, get_act_service, get_actor
from app.act.models import (
    ActError,
    Actor,
    Approval,
    EmailNotConfiguredError,
    MessageRevision,
    MessageStatus,
    NotApprovedError,
    NotFoundError,
    SendExistsError,
    SendRecord,
    SendStatus,
    StaleRevisionError,
    ValidationError,
)
from app.act.service import ActService, MessageState

# --- schemas --------------------------------------------------------------------------


class RevisionIn(BaseModel):
    subject: str = Field(max_length=1_000)
    body: str = Field(max_length=100_000)
    recipient: str = Field(
        max_length=320, description="Typed in by the user; DealProof never scrapes contacts."
    )


class EditIn(RevisionIn):
    base_revision_id: str | None = Field(
        default=None, description="If set, must be the current revision (optimistic lock)."
    )


class ApproveIn(BaseModel):
    revision_id: str


class RevisionOut(BaseModel):
    id: str
    number: int
    subject: str
    body: str
    recipient: str
    entered_by_user_id: str
    created_at: datetime


class ApprovalOut(BaseModel):
    revision_id: str
    approver_user_id: str
    approver_display_name: str
    approved_at: datetime


class SendOut(BaseModel):
    id: str
    revision_id: str
    status: SendStatus
    test_mode: bool
    attempts: int
    provider_message_id: str | None
    error: str | None
    created_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None


class MessageOut(BaseModel):
    id: str
    case_id: str
    status: MessageStatus
    current_revision: RevisionOut
    approval: ApprovalOut | None
    send: SendOut | None
    revisions: list[RevisionOut]


class SendSummaryOut(BaseModel):
    """`sent` counts real provider acceptance only; test-mode suppressions are separate."""

    sent: int
    suppressed_test_mode: int
    failed: int
    unknown: int
    sending: int


def _revision_out(r: MessageRevision) -> RevisionOut:
    return RevisionOut(
        id=r.id,
        number=r.number,
        subject=r.subject,
        body=r.body,
        recipient=r.recipient,
        entered_by_user_id=r.entered_by_user_id,
        created_at=r.created_at,
    )


def _approval_out(a: Approval) -> ApprovalOut:
    return ApprovalOut(
        revision_id=a.revision_id,
        approver_user_id=a.approver_user_id,
        approver_display_name=a.approver_display_name,
        approved_at=a.approved_at,
    )


def _send_out(s: SendRecord) -> SendOut:
    return SendOut(
        id=s.id,
        revision_id=s.revision_id,
        status=s.status,
        test_mode=s.test_mode,
        attempts=s.attempts,
        provider_message_id=s.provider_message_id,
        error=s.error,
        created_at=s.created_at,
        dispatched_at=s.dispatched_at,
        completed_at=s.completed_at,
    )


def _message_out(state: MessageState) -> MessageOut:
    return MessageOut(
        id=state.message.id,
        case_id=state.message.case_id,
        status=state.status,
        current_revision=_revision_out(state.current_revision),
        approval=_approval_out(state.approval) if state.approval else None,
        send=_send_out(state.send) if state.send else None,
        revisions=[_revision_out(r) for r in state.revisions],
    )


def _raise_http(exc: ActError) -> NoReturn:
    detail: dict[str, object] = {"message": str(exc)}
    match exc:
        case NotFoundError():
            code, detail["code"] = status.HTTP_404_NOT_FOUND, "not_found"
        case ValidationError():
            code, detail["code"] = status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid"
        case NotApprovedError():
            code, detail["code"] = status.HTTP_409_CONFLICT, "not_approved"
        case StaleRevisionError():
            code, detail["code"] = status.HTTP_409_CONFLICT, "stale_revision"
        case SendExistsError():
            code, detail["code"] = status.HTTP_409_CONFLICT, "send_exists"
            detail["send"] = _send_out(exc.send).model_dump(mode="json")
        case EmailNotConfiguredError():
            code, detail["code"] = status.HTTP_503_SERVICE_UNAVAILABLE, "email_not_configured"
        case _:
            code, detail["code"] = status.HTTP_409_CONFLICT, "conflict"
    raise HTTPException(status_code=code, detail=detail) from exc


# --- routes ---------------------------------------------------------------------------

router = APIRouter(prefix="/cases/{case_id}/messages", tags=["act"])

CaseId = Annotated[str, Depends(authorize_case)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
Service = Annotated[ActService, Depends(get_act_service)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MessageOut)
async def create_message(
    case_id: CaseId, actor: CurrentActor, service: Service, payload: RevisionIn
) -> MessageOut:
    try:
        state = await service.create_message(
            case_id,
            actor,
            subject=payload.subject,
            body=payload.body,
            recipient=payload.recipient,
        )
    except ActError as exc:
        _raise_http(exc)
    return _message_out(state)


@router.get("/send-summary", response_model=SendSummaryOut)
async def send_summary(case_id: CaseId, service: Service) -> SendSummaryOut:
    counts = await service.send_summary(case_id)
    return SendSummaryOut(**{s.value: counts.get(s, 0) for s in SendStatus})


@router.get("/{message_id}", response_model=MessageOut)
async def get_message(case_id: CaseId, message_id: str, service: Service) -> MessageOut:
    try:
        state = await service.get_state(case_id, message_id)
    except ActError as exc:
        _raise_http(exc)
    return _message_out(state)


@router.post("/{message_id}/revisions", response_model=MessageOut)
async def edit_message(
    case_id: CaseId, message_id: str, actor: CurrentActor, service: Service, payload: EditIn
) -> MessageOut:
    try:
        state = await service.revise(
            case_id,
            message_id,
            actor,
            subject=payload.subject,
            body=payload.body,
            recipient=payload.recipient,
            base_revision_id=payload.base_revision_id,
        )
    except ActError as exc:
        _raise_http(exc)
    return _message_out(state)


@router.post("/{message_id}/approve", response_model=MessageOut)
async def approve_message(
    case_id: CaseId, message_id: str, actor: CurrentActor, service: Service, payload: ApproveIn
) -> MessageOut:
    try:
        state = await service.approve(case_id, message_id, actor, revision_id=payload.revision_id)
    except ActError as exc:
        _raise_http(exc)
    return _message_out(state)


@router.post("/{message_id}/send", response_model=SendOut)
async def send_message(
    case_id: CaseId, message_id: str, actor: CurrentActor, service: Service
) -> SendOut:
    try:
        record = await service.send(case_id, message_id, actor)
    except ActError as exc:
        _raise_http(exc)
    return _send_out(record)


@router.post("/{message_id}/reconcile", response_model=SendOut)
async def reconcile_message(case_id: CaseId, message_id: str, service: Service) -> SendOut:
    try:
        record = await service.reconcile(case_id, message_id)
    except ActError as exc:
        _raise_http(exc)
    return _send_out(record)
