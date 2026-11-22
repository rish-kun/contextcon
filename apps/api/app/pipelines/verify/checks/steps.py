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

from app.clients.activity import reset_activity_topic, set_activity_topic
from app.db.enums import IdentityStatus, StepState
from app.db.models import Case, Claim, Step
from app.jobs import StepContext, StepSpec, step_handler
from app.jobs.activity import claim_ref
from app.pipelines.verify.checks import activity as check_activity
from app.pipelines.verify.checks.clients import client_factory, close_quietly
from app.pipelines.verify.checks.gather import IDENTITY_DEPENDENT
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
            # The closing evaluate waits for this check; waiting on it would deadlock.
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


async def _counts(ctx: StepContext, claim: Claim) -> dict[str, int]:
    return await check_activity.claim_counts(
        ctx.session, ctx.run.id, CHECK_HANDLER, current=str(claim.id)
    )


async def _check(ctx: StepContext, claim: Claim, case: Case) -> dict[str, Any]:
    await ctx.set_detail(f"Checking: {claim.category.replace('_', ' ')}")
    await check_activity.checking(await _counts(ctx, claim))
    if case.identity_status != IdentityStatus.CONFIRMED and claim.category in IDENTITY_DEPENDENT:
        await check_activity.status("status.waiting_identity")
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
    await check_activity.settled(meta, await _counts(ctx, claim))
    return meta


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
    # Every event of this check names the claim by id and category, never its text.
    topic = set_activity_topic(ref=claim_ref(claim.id), category=claim.category)
    try:
        meta = await _check(ctx, claim, case)
    finally:
        reset_activity_topic(topic)
    from app.domain.enums import ClaimStatus

    ctx.result = status_label(ClaimStatus(meta["status"]))
    return {"claim_id": str(claim.id), "checks": {str(claim.id): meta}}
