"""The `act.request_list` step handler."""

from __future__ import annotations

from app.clients.activity import activity_topic
from app.db.ledger import CostContext
from app.jobs import StepContext, StepSpec, step_handler
from app.jobs.activity import Subject, render
from app.pipelines.act import llm as llm_module
from app.pipelines.act.request_list import NoAssessment, build_request_list_for_case

HANDLER = "act.request_list"
STEP_KEY = "request_list"


def request_list_step(
    *, depends_on: list[str] | tuple[str, ...] = ("evaluate", "decision_flip")
) -> StepSpec:
    """Runs after `evaluate.assess` and `evaluate.decision_flip`: the request list for
    the new assessment version. A failed analysis does not block it."""
    return StepSpec(
        key=STEP_KEY,
        handler=HANDLER,
        label="Draft the document request",
        depends_on=tuple(depends_on),
        uses_budget=False,
        tolerate_failed_deps=True,
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
    await ctx.activity.status(render("status.drafting_request"))
    try:
        async with llm_module.llm_factory(ctx.sessionmaker, cost, ctx.recorder) as llm:
            with activity_topic(purpose="request"):
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
    if built.created:
        # Counts only: the request list's item text is not in the stream.
        nothing = rl.status == "nothing_to_request"
        await ctx.activity.finding(
            render("finding.nothing_to_request")
            if nothing
            else render("finding.request_list", n=built.item_count),
            subject=Subject.REQUEST_LIST,
            items=[{"id": str(rl.id), "stage": "nothing_to_request" if nothing else "drafted"}],
            counts={"request_items": 0 if nothing else built.item_count},
        )
    if built.used_fallback:
        ctx.log("seller email drafted from the template")
    return {
        "request_list_id": str(rl.id),
        "created": built.created,
        "items": built.item_count if built.created else None,
    }
