"""Run step `verify.checks.claim`: check one claim and append its ledger row.

A check waits for every other verify step of its run. Steps can be appended after
the check was scheduled (CP-19 adds profile, registry and events once identity is
confirmed), so a check that finds such a step still pending re-schedules itself
behind it (`checks.claim:<id>~<n>`) instead of reading evidence that is not there yet.

The step does its own budget accounting (`uses_budget=False`): when the case's
credits run out, the claim is recorded as `not_checked` ("budget") instead of the
step being skipped, so the ledger never silently lacks a row.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.db.enums import StepState
from app.db.models import Case, Claim, Step
from app.jobs import StepContext, StepSpec, step_handler
from app.pipelines.verify.checks.clients import client_factory, close_quietly
from app.pipelines.verify.checks.run import check_claim
from app.pipelines.verify.claims.intake import (
    CHECK_HANDLER,
    CHECK_PREFIX,
    DOWNSTREAM_HANDLERS,
    OWN_HANDLERS,
)
from app.rules.claim_status import status_label

MAX_DEFERRALS = 3


async def _defer_behind_unfinished(ctx: StepContext, claim: Claim) -> str | None:
    """Re-schedule this check behind verify steps it does not wait for yet."""
    rows = await ctx.session.execute(
        select(Step.key).where(
            Step.run_id == ctx.run.id,
            Step.id != ctx.step_id,
            Step.state.in_([StepState.PENDING, StepState.RUNNING]),
            Step.handler.notin_(OWN_HANDLERS | DOWNSTREAM_HANDLERS),
        )
    )
    waiting = sorted(rows.scalars())
    deferrals = int(ctx.input.get("deferrals", 0))
    if not waiting or deferrals >= MAX_DEFERRALS:
        return None
    key = f"{CHECK_PREFIX}{claim.id}~{deferrals + 1}"
    await ctx.append_steps(
        [
            StepSpec(
                key=key,
                handler=CHECK_HANDLER,
                label=f"Check claim: {claim.category.replace('_', ' ')}",
                input={"claim_id": str(claim.id), "deferrals": deferrals + 1},
                depends_on=[*waiting, ctx.key],
                uses_budget=False,
                tolerate_failed_deps=True,
            )
        ]
    )
    return key


def _optional(build: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return build(*args, **kwargs)
    except ValueError:  # an API key is not configured
        return None


@step_handler(CHECK_HANDLER)
async def check_claim_step(ctx: StepContext) -> dict[str, Any]:
    claim = await ctx.session.get(Claim, uuid.UUID(ctx.input["claim_id"]))
    if claim is None or claim.case_id != ctx.run.case_id:
        raise LookupError("claim not found for this case")
    case = await ctx.session.get(Case, claim.case_id)
    assert case is not None
    deferred_to = await _defer_behind_unfinished(ctx, claim)
    if deferred_to is not None:
        ctx.result = "Waiting for the company profile and records"
        return {"claim_id": str(claim.id), "deferred_to": deferred_to}
    await ctx.set_detail(f"Checking: {claim.category.replace('_', ' ')}")
    factory = client_factory()
    crustdata = _optional(factory.crustdata, ctx)
    llm = _optional(factory.llm, ctx, delete_after=claim.delete_after)
    try:
        meta = await check_claim(
            ctx.session,
            claim_row=claim,
            case=case,
            crustdata=crustdata,
            llm=llm,
            budget=ctx.require_budget,
            run_id=ctx.run.id,
            step_id=ctx.step_id,
            log=ctx.log,
        )
    finally:
        for client in (crustdata, llm):
            if client is not None:
                await close_quietly(client)
    from app.domain.enums import ClaimStatus

    ctx.result = status_label(ClaimStatus(meta["status"]))
    return {"claim_id": str(claim.id), "checks": {str(claim.id): meta}}
