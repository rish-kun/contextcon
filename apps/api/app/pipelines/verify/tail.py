"""How a case's verify run ends: `evaluate.assess`, then `act.request_list`.

The evaluate step is marked `after_all`, so while it is pending it also waits for every
step appended later: identity-dependent steps, claim checks fanned out by extraction,
deferred re-checks (see `app.jobs.engine.append_steps`). Work added while it is pending
joins it (its trigger documents are merged in). Once an earlier tail has started or
finished, new work (a manual identity pick, a later claim) gets a fresh
`evaluate@n` → `request_list@n`, so the case is re-assessed with it.

Scheduled by `schedule_claim_checks` after every batch of checks, by the identity step
once it confirms the company, and by a manual identity pick.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Step
from app.jobs import AFTER_ALL, append_steps
from app.jobs.engine import pending_after_all
from app.pipelines.act.step import HANDLER as REQUEST_LIST_HANDLER
from app.pipelines.act.step import STEP_KEY as REQUEST_LIST_KEY
from app.pipelines.act.step import request_list_step
from app.pipelines.evaluate.service import HANDLER as EVALUATE_HANDLER
from app.pipelines.evaluate.service import STEP_KEY as EVALUATE_KEY
from app.pipelines.evaluate.service import evaluate_step

TAIL_HANDLERS = frozenset({EVALUATE_HANDLER, REQUEST_LIST_HANDLER})


async def ensure_assessment_tail(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID | str] = (),
    trigger: str | None = None,
) -> list[Step]:
    """Make sure the run ends by re-assessing the case and drafting its request list
    (flushes). Returns the steps it added: none when a closing evaluate is still pending
    (it already waits for everything appended since)."""
    docs = [str(d) for d in document_ids]
    pending = [s for s in await pending_after_all(session, run_id) if s.handler == EVALUATE_HANDLER]
    if pending:
        if docs:
            step = pending[-1]
            known = list(step.input.get("document_ids") or [])
            step.input = {**step.input, "document_ids": list(dict.fromkeys([*known, *docs]))}
            await session.flush()
        return []
    rows = await session.execute(
        select(Step.key, Step.handler).where(Step.run_id == run_id).order_by(Step.position)
    )
    existing = rows.all()
    used = {key for key, _ in existing}
    n = 1
    while (f"{EVALUATE_KEY}@{n}" if n > 1 else EVALUATE_KEY) in used:
        n += 1
    suffix = "" if n == 1 else f"@{n}"
    evaluate_key = f"{EVALUATE_KEY}{suffix}"
    base = evaluate_step(
        depends_on=[key for key, _ in existing], trigger=trigger, document_ids=docs
    )
    evaluate = replace(base, key=evaluate_key, input={**base.input, AFTER_ALL: True})
    request_list = replace(
        request_list_step(depends_on=[evaluate_key]), key=f"{REQUEST_LIST_KEY}{suffix}"
    )
    return await append_steps(session, run_id, [evaluate, request_list])
