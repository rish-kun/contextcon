"""Seller-response recheck (CP-24): a seller answers the request list with a document.

Upload (in the request):
    `answered_items` validates the request items the uploader says the document
    answers (they must belong to this case's request lists), `link_answers` stores
    the links, and `schedule_recheck` opens a `recheck` run:

        claims.extract:<doc>  →  evaluate  →  request_list

Extraction (the run's first step, `verify.claims.extract`):
    claims are read from the new document and each gets a check step, as for any
    upload. In a recheck run the step then re-checks the claims behind the answered
    request items (`plan_recheck`) and makes `evaluate` wait for every check step,
    so the new assessment version (whose `trigger_document_ids` names the upload)
    sees the new checks. `request_list` follows the new version.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import RunKind
from app.db.models import (
    Case,
    Claim,
    DocumentRequestItem,
    RequestItem,
    RequestItemClaim,
    RequestList,
    Run,
    Step,
)
from app.jobs import StepSpec, create_run
from app.pipelines.act.step import request_list_step
from app.pipelines.evaluate.service import STEP_KEY as EVALUATE_KEY
from app.pipelines.evaluate.service import evaluate_step
from app.pipelines.verify.claims.intake import (
    CHECK_HANDLER,
    EXTRACT_HANDLER,
    EXTRACT_PREFIX,
    StoredUpload,
    schedule_claim_checks,
)

EXTRACT_LABEL = "Read claims from the uploaded document"


class UnknownRequestItems(ValueError):
    """Some `answers_request_item_ids` are not request items of this case."""


async def answered_items(
    session: AsyncSession, case: Case, item_ids: Iterable[str]
) -> list[uuid.UUID]:
    """The request item ids, checked to belong to `case` (raises `UnknownRequestItems`)."""
    wanted: list[uuid.UUID] = []
    for raw in item_ids:
        for part in str(raw).split(","):  # a form may send one comma-separated field
            if not part.strip():
                continue
            try:
                item_id = uuid.UUID(part.strip())
            except ValueError:
                raise UnknownRequestItems("Unknown request item.") from None
            if item_id not in wanted:
                wanted.append(item_id)
    if not wanted:
        return []
    found = set(
        (
            await session.execute(
                select(RequestItem.id)
                .join(RequestList, RequestList.id == RequestItem.request_list_id)
                .where(RequestItem.id.in_(wanted), RequestList.case_id == case.id)
            )
        ).scalars()
    )
    if found != set(wanted):
        raise UnknownRequestItems("Unknown request item.")
    return wanted


async def link_answers(
    session: AsyncSession, document_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> None:
    for item_id in item_ids:
        session.add(DocumentRequestItem(document_id=document_id, request_item_id=item_id))
    await session.flush()


async def schedule_recheck(
    session: AsyncSession,
    *,
    case: Case,
    stored: StoredUpload,
    answered: Sequence[uuid.UUID],
    created_by: uuid.UUID | None = None,
) -> Run:
    """Open the recheck run for one seller response (flushes, does not commit)."""
    document = stored.document
    result = stored.result
    extract_key = f"{EXTRACT_PREFIX}{document.id}"
    return await create_run(
        session,
        workspace_id=case.workspace_id,
        kind=RunKind.RECHECK,
        case_id=case.id,
        created_by=created_by,
        steps=[
            StepSpec(
                key=extract_key,
                handler=EXTRACT_HANDLER,
                label=EXTRACT_LABEL,
                input={
                    "document_id": str(document.id),
                    "text_status": result.text_status,
                    "text_reason": result.text_status_reason,
                    "pages_without_text": list(result.pages_without_text),
                    "recheck": {"request_item_ids": [str(i) for i in answered]},
                },
                uses_budget=False,
            ),
            evaluate_step(depends_on=[extract_key], document_ids=[str(document.id)]),
            request_list_step(depends_on=(EVALUATE_KEY,)),
        ],
    )


async def _claims_behind(
    session: AsyncSession, case_id: uuid.UUID, item_ids: Sequence[str]
) -> list[Claim]:
    ids = [uuid.UUID(i) for i in item_ids]
    if not ids:
        return []
    rows = await session.execute(
        select(Claim)
        .join(RequestItemClaim, RequestItemClaim.claim_id == Claim.id)
        .where(RequestItemClaim.request_item_id.in_(ids), Claim.case_id == case_id)
        .order_by(Claim.created_at, Claim.id)
    )
    unique = {c.id: c for c in rows.scalars()}  # one claim may sit behind several items
    return [c for c in unique.values() if not (c.components or {}).get("intake")]


async def plan_recheck(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    case_id: uuid.UUID,
    plan: dict,
    new_claims: Sequence[Claim],
    document_id: uuid.UUID,
    after: str | None = None,
) -> int:
    """In a recheck run: check the new claims and re-check the claims behind the
    answered items in one batch, then make the run's `evaluate` wait for every check
    step. Returns how many existing claims were re-checked."""
    new_ids = {c.id for c in new_claims}
    affected = [
        c
        for c in await _claims_behind(session, case_id, plan.get("request_item_ids") or [])
        if c.id not in new_ids
    ]
    batch = [*new_claims, *affected]
    if batch:
        await schedule_claim_checks(
            session,
            run_id=run_id,
            claims=batch,
            after=[after] if after else None,
            document_ids=[document_id],
            evaluate=False,  # the recheck run already ends with evaluate → request list
        )
    steps = list(
        (
            await session.execute(select(Step).where(Step.run_id == run_id).order_by(Step.position))
        ).scalars()
    )
    evaluate = next((s for s in steps if s.key == EVALUATE_KEY), None)
    if evaluate is not None:
        checks = [s.key for s in steps if s.handler == CHECK_HANDLER]
        deps = list(dict.fromkeys([*evaluate.depends_on, *checks]))
        await session.execute(update(Step).where(Step.id == evaluate.id).values(depends_on=deps))
    return len(affected)
