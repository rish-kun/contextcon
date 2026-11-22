"""Typed claim intake (CP-20). The claim is categorised now and checked by the case's
verify run (`verify.checks.claim`, CP-21)."""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

# Register the intake and check step handlers with the in-process worker. (The
# shared pipeline registry imports `app.pipelines.verify`, owned by CP-19.)
import app.pipelines.verify.checks.steps  # noqa: E402, F401
import app.pipelines.verify.claims.steps  # noqa: E402, F401
from app.api import fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.schemas.claims import ClaimCreate, ClaimOut
from app.api.schemas.runs import RunOut
from app.auth.deps import AuthorizedCaseId, CurrentUser, load_case
from app.clients.llm import LLMError
from app.db.adapters import DbCache, DbCallRecorder
from app.db.ledger import CostContext
from app.db.models import Case, Claim
from app.db.session import get_sessionmaker
from app.documents.storage import compute_delete_after
from app.extraction.llm import LlmOutputError
from app.jobs import events
from app.pipelines.verify.claims.intake import (
    add_typed_claim,
    schedule_claim_checks,
    verify_run_for_case,
)
from app.pipelines.verify.claims.ledger import build_claims_section
from app.settings import get_settings

router = make_router(tags=["claims"])

LlmForCase = Callable[[Case], Any]


def typed_claim_llm() -> LlmForCase:
    """LLM client for one case: metered to the case, cache scoped to it (confidential)."""

    def build(case: Case) -> Any:
        from datetime import UTC, datetime

        from app.clients import LLMClient

        settings = get_settings()
        ctx = CostContext(workspace_id=case.workspace_id, case_id=case.id)
        sm = get_sessionmaker()
        expires = compute_delete_after(datetime.now(UTC), settings.upload_retention_days)
        return LLMClient.from_settings(
            settings,
            recorder=DbCallRecorder(sm, ctx),
            cache=DbCache(sm, ctx, confidential=True, delete_after=expires),
        )

    return build


@router.post(
    "/cases/{case_id}/claims",
    response_model=ClaimOut,
    status_code=status.HTTP_201_CREATED,
    responses={503: {"description": "The claim could not be categorised; nothing was stored."}},
)
async def add_claim(
    case_id: AuthorizedCaseId,
    body: ClaimCreate,
    user: CurrentUser,
    llm_for_case: Annotated[LlmForCase, Depends(typed_claim_llm)],
) -> ClaimOut:
    """Add a typed claim. It is categorised and checked like a document claim."""
    if fixtures_enabled():  # `authorize_case` has already checked the fixture case id
        return fixtures.typed_claim(body.text)

    settings = get_settings()
    async with get_sessionmaker()() as db:
        case = await load_case(db, user.workspace_id, case_id)
        llm = llm_for_case(case)
        try:
            claim = await add_typed_claim(
                db,
                case=case,
                text=body.text,
                llm=llm,
                retention_days=settings.upload_retention_days,
                created_by=user.id,
            )
        except (LLMError, LlmOutputError) as exc:
            await db.rollback()
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The claim could not be categorised right now. Try again.",
            ) from exc
        finally:
            close = getattr(llm, "aclose", None)
            if close is not None:
                await close()
        run = await verify_run_for_case(db, case, created_by=user.id)
        await schedule_claim_checks(db, run_id=run.id, claims=[claim])
        await db.commit()
        [out] = await build_claims_section(db, case, claim_ids=[claim.id])
        return out


@router.post(
    "/cases/{case_id}/claims/{claim_id}/check",
    response_model=RunOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"description": "No such claim on this case."},
        409: {"description": "The claim's text could not be read, so it cannot be checked."},
    },
)
async def check_claim(
    case_id: AuthorizedCaseId, claim_id: str, user: CurrentUser, request: Request
) -> RunOut:
    """Check one claim again: its check step is queued on the case's verify run, then
    the case is re-assessed and its request list redrafted. Returns the run to follow."""
    if fixtures_enabled():
        detail = fixtures.case_detail(request.path_params["case_id"])  # the raw fixture id
        if detail is None or claim_id not in {c.id for c in detail.claims}:
            not_found("Claim")
        return fixtures.runs()[fixtures.VERIFY_RUN_ID]
    try:
        claim_uuid = uuid.UUID(claim_id)
    except ValueError:
        not_found("Claim")
    async with get_sessionmaker()() as db:
        case = await load_case(db, user.workspace_id, case_id)
        claim = await db.scalar(
            select(Claim).where(Claim.id == claim_uuid, Claim.case_id == case.id)
        )
        if claim is None:
            not_found("Claim")
        if (claim.components or {}).get("intake"):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This claim's text could not be read, so it cannot be checked.",
            )
        run = await verify_run_for_case(db, case, created_by=user.id)
        await schedule_claim_checks(db, run_id=run.id, claims=[claim])
        await db.commit()
        return await events.load_run_out(db, user.workspace_id, run.id)
