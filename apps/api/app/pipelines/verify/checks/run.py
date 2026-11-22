"""Check one claim: gather evidence, build `ClaimCheck`, decide, persist.

A check that cannot run is still recorded, as `not_checked` with the reason:
- identity is not confirmed (identity-dependent categories only),
- the case's credit budget is spent (`BudgetExceeded`),
- a provider is unavailable or failed.
Customer, partnership, certification and trademark claims run up to two targeted
public lookups from their source module (`gather.SOURCE_MODULES`); financials one
results search. The registry-only ones (debt, litigation) and `other` run without
paid calls. With nothing adequate the rules answer `cannot_verify`, name what would
settle it and, when a lookup ran, what was searched.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.crustdata import CrustdataCreditsError, CrustdataError, CrustdataPlanError
from app.clients.llm import LLMError
from app.db.models import Case
from app.db.models import Claim as ClaimRow
from app.domain.enums import ClaimCategory, ClaimStatus, IdentityStatus, NotCheckedReason
from app.domain.types import Claim, ClaimCheck
from app.extraction.llm import LlmOutputError, StructuredLlm
from app.jobs import BudgetExceeded
from app.pipelines.verify.checks import activity as check_activity
from app.pipelines.verify.checks.gather import (
    IDENTITY_DEPENDENT,
    Budget,
    CheckEnv,
    Gathered,
    gatherer_for,
)
from app.pipelines.verify.checks.persist import persist_outcome
from app.pipelines.verify.checks.sources import EvidenceStore, domain_source
from app.pipelines.verify.claims.components import from_jsonb
from app.rules import decide_all

_ORIGINS = {"deck": "seller_document", "typed": "seller_typed", "profile": "profile"}
# Categories whose check makes no model call.
_NO_MODEL = frozenset({ClaimCategory.TEAM_SIZE, ClaimCategory.OTHER})


def domain_claim(row: ClaimRow) -> Claim:
    try:
        category = ClaimCategory(row.category)
    except ValueError:
        category = ClaimCategory.OTHER
    return Claim(
        id=str(row.id),
        text=row.original_text,
        category=category,
        components=from_jsonb(row.components),
        origin=_ORIGINS.get(row.origin, "seller_document"),  # type: ignore[arg-type]
    )


def _not_run(claim: Claim, reason: NotCheckedReason, detail: str) -> ClaimCheck:
    return ClaimCheck(claim=claim, ran=False, not_run_reason=reason, not_run_detail=detail)


async def check_claim(
    session: AsyncSession,
    *,
    claim_row: ClaimRow,
    case: Case,
    crustdata: Any,
    llm: StructuredLlm | None,
    budget: Budget,
    run_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    """Decide and persist one claim's status (flushes). Returns the step metadata."""
    claim = domain_claim(claim_row)
    category = claim.category
    try:
        company_id = int(case.crustdata_company_id) if case.crustdata_company_id else None
    except ValueError:
        company_id = None
    store = EvidenceStore(session, case.workspace_id, case.id, run_id, company_id=company_id)
    identity_ok = (
        case.identity_status == IdentityStatus.CONFIRMED and case.crustdata_company_id is not None
    )
    gathered: Gathered | None = None
    if category in IDENTITY_DEPENDENT and not identity_ok:
        check = _not_run(
            claim,
            NotCheckedReason.IDENTITY_UNRESOLVED,
            f"the company's identity is {case.identity_status}",
        )
    elif category in IDENTITY_DEPENDENT and crustdata is None:
        check = _not_run(claim, NotCheckedReason.SOURCE_UNAVAILABLE, "Crustdata is not configured")
    elif category not in _NO_MODEL and llm is None:
        check = _not_run(claim, NotCheckedReason.SOURCE_UNAVAILABLE, "the model is not configured")
    else:
        env = CheckEnv(
            session=session,
            case=case,
            crustdata=crustdata,
            llm=llm,  # type: ignore[arg-type]
            budget=budget,
            store=store,
            log=log,
        )
        try:
            gathered = await gatherer_for(claim)(env, claim)
            check = ClaimCheck(
                claim=claim.model_copy(update={"entity_ids": gathered.entity_ids}),
                facts=gathered.facts,
                sources_read=[domain_source(s) for s in gathered.sources_read],
            )
        except BudgetExceeded:
            check = _not_run(
                claim, NotCheckedReason.BUDGET_EXHAUSTED, "the case's credit budget is spent"
            )
        except CrustdataCreditsError:
            check = _not_run(
                claim,
                NotCheckedReason.SOURCE_UNAVAILABLE,
                "the Crustdata account is out of credits",
            )
        except CrustdataPlanError:
            check = _not_run(
                claim,
                NotCheckedReason.SOURCE_UNAVAILABLE,
                "a Crustdata endpoint is not on the plan",
            )
        except CrustdataError:
            check = _not_run(claim, NotCheckedReason.SOURCE_ERROR, "a Crustdata call failed")
        except (LLMError, LlmOutputError):
            check = _not_run(claim, NotCheckedReason.SOURCE_ERROR, "the model call failed")

    read_markers: dict[str, uuid.UUID] = {}
    if check.ran and gathered is not None:
        spoke = {f.evidence.source.id for f in check.facts}
        entity = gathered.read_ref or f"case:{case.id}"
        for source in gathered.sources_read:
            if str(source.id) not in spoke:
                marker = await store.read_marker(source, entity_ref=entity)
                read_markers[str(source.id)] = marker.id
        log(
            f"{category.value}: {len(check.facts)} facts ({gathered.rejected} rejected), "
            f"{len(gathered.sources_read)} sources read, {gathered.llm_calls} model calls"
        )

    if check.ran:
        await check_activity.status("status.comparing_facts", n=len(check.facts))
    [outcome] = decide_all([check])
    searched = gathered.searched if gathered is not None and check.ran else []
    if searched and outcome.status is not ClaimStatus.SUPPORTED:
        outcome = outcome.model_copy(
            update={"reason": f"{outcome.reason} {searched_sentence(searched)}"}
        )
    meta = await persist_outcome(
        session,
        claim=claim_row,
        check=check,
        outcome=outcome,
        run_id=run_id,
        step_id=step_id,
        read_markers=read_markers,
        searched=searched,
    )
    return meta


def searched_sentence(searched: list[dict[str, Any]]) -> str:
    """ "Searched: Microsoft partner directory (2 results), ..." for the reason text."""
    parts = []
    for entry in searched:
        if entry.get("skipped"):
            parts.append(f"{entry['label']} (not run: {entry['skipped'].replace('_', ' ')})")
        else:
            n = len(entry.get("results") or [])
            parts.append(f"{entry['label']} ({n} result{'s' if n != 1 else ''})")
    return f"Searched: {'; '.join(parts)}."
