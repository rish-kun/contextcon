"""The `act.request_list` step handler."""

from __future__ import annotations

from app.db.ledger import CostContext
from app.jobs import StepContext, StepSpec, step_handler
from app.pipelines.act import llm as llm_module
from app.pipelines.act.request_list import NoAssessment, build_request_list_for_case

HANDLER = "act.request_list"
STEP_KEY = "request_list"


def request_list_step(*, depends_on: list[str] | tuple[str, ...] = ("evaluate",)) -> StepSpec:
    """Runs after `evaluate.assess`: the request list for the new assessment version."""
    return StepSpec(
        key=STEP_KEY,
        handler=HANDLER,
        label="Draft the document request",
        depends_on=tuple(depends_on),
        uses_budget=False,
    )


@step_handler(HANDLER)
async def build_request_list_step(ctx: StepContext) -> dict:
    if ctx.run.case_id is None:
        raise ValueError("act.request_list needs a case run")
    cost = ctx.cost or CostContext(
        workspace_id=ctx.run.workspace_id,
        case_id=ctx.run.case_id,
        run_id=ctx.run.id,
        step_id=ctx.step_id,
    )
    try:
        async with llm_module.llm_factory(ctx.sessionmaker, cost, ctx.recorder) as llm:
            built = await build_request_list_for_case(
                ctx.session, ctx.run.workspace_id, ctx.run.case_id, llm=llm
            )
    except NoAssessment:
        ctx.result = "No assessment yet: nothing to request"
        return {"request_list_id": None, "items": 0}
    rl = built.request_list
    if not built.created:
        ctx.result = "Request list already drafted for this assessment"
    elif rl.status == "nothing_to_request":
        ctx.result = "Nothing to request from the seller"
    else:
        ctx.result = "Request list drafted"
    if built.used_fallback:
        ctx.log("seller email drafted from the template")
    return {
        "request_list_id": str(rl.id),
        "created": built.created,
        "items": built.item_count if built.created else None,
    }
