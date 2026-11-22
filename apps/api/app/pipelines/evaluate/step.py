"""The `evaluate.assess` step handler."""

from __future__ import annotations

import datetime as dt

from app.jobs import StepContext, step_handler
from app.pipelines.evaluate.service import HANDLER, evaluate_case
from app.pipelines.memo.llm import memo_llm, memo_section_builder

TRIGGERS = {
    "verify": "initial verify",
    "recheck": "seller documents",
    "evaluate": "manual re-run",
}


def today() -> dt.date:
    """The evaluation date passed to the rules (they never read the clock)."""
    return dt.datetime.now(dt.UTC).date()


@step_handler(HANDLER)
async def assess_case(ctx: StepContext) -> dict:
    if ctx.run.case_id is None:
        raise ValueError("evaluate.assess needs a case run")
    failed = sorted(k for k, d in ctx.dependencies.items() if d.get("state") != "done")
    trigger = ctx.input.get("trigger") or TRIGGERS.get(ctx.run.kind, ctx.run.kind)
    outcome = await evaluate_case(
        ctx.session,
        ctx.run.workspace_id,
        ctx.run.case_id,
        today=today(),
        trigger=trigger,
        run_id=ctx.run.id,
        enrich=memo_section_builder(),
        enrich_arg=memo_llm(ctx),
    )
    a = outcome.assessment
    label = a.disposition.value.replace("_", " ")
    ctx.result = (
        f"Version {outcome.version.version}: {label}"
        if outcome.created
        else f"No change: version {outcome.version.version} still stands"
    )
    if failed:
        ctx.log(f"assessed with unfinished steps: {', '.join(failed)}")
    return {
        "assessment_version_id": str(outcome.version.id),
        "version": outcome.version.version,
        "created": outcome.created,
        "disposition": a.disposition.value,
        "inputs_hash": a.inputs_hash,
    }
