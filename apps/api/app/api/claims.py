"""Typed claim intake (CP-20). The claim is categorised now and checked by the case's
verify run (`verify.checks.claim`, CP-21)."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

# Register the intake and check step handlers with the in-process worker. (The
# shared pipeline registry imports `app.pipelines.verify`, owned by CP-19.)
import app.pipelines.verify.checks.steps  # noqa: E402, F401
import app.pipelines.verify.claims.steps  # noqa: E402, F401
from app.api import fixtures
from app.api._base import fixtures_enabled, make_router
from app.api.schemas.claims import ClaimCreate, ClaimOut
from app.auth.deps import AuthorizedCaseId, CurrentUser, load_case
from app.clients.llm import LLMError
from app.db.adapters import DbCache, DbCallRecorder
from app.db.ledger import CostContext
from app.db.models import Case
from app.db.session import get_sessionmaker
from app.documents.storage import compute_delete_after
from app.extraction.llm import LlmOutputError
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
