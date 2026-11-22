"""Job runner: runs made of idempotent steps, claimed by workers with leases.

Register a handler and enqueue a run:

    from app.jobs import StepContext, StepSpec, create_run, step_handler

    @step_handler("verify.identity")
    async def identify(ctx: StepContext) -> dict:
        await ctx.set_detail("Matching the domain")       # live sub-line (SSE)
        client = CrustdataClient(key, recorder=ctx.recorder, cache=ctx.cache)
        ...                                               # paid calls: cached + metered
        ctx.result = "Identity confirmed"                 # one-line result
        return {...}                                      # step output (JSON)

    run = await create_run(
        session, workspace_id=ws, kind="verify", case_id=case.id,
        steps=[StepSpec("identity", "verify.identity", label="Confirm identity"),
               StepSpec("profile", "verify.profile", depends_on=["identity"])],
    )
    await session.commit()

Paid calls inside a step: pass `ctx.recorder` and `ctx.cache` to the clients. Every
dispatch is fenced on the step's claim token and reserves credits atomically against
the owner's budget (`BudgetExceeded` / `LeaseLost` propagate to the worker). LLM calls
use the case-scoped, expiring cache unless called with `public=True`.

Confidential text: `ctx.keep_output_confidential()` stores the step output in an
expiring payload; `await ctx.store_confidential(payload, kind=...)` returns a reference
to embed in snapshots (e.g. an assessment version). See `app.jobs.retention`.
"""

from app.jobs.engine import (
    BUDGET_REACHED,
    BudgetExceeded,
    StepContext,
    StepSpec,
    append_steps,
    create_run,
    resume_run,
)
from app.jobs.registry import StepRegistry, load_handlers, registry, step_handler

__all__ = [
    "BUDGET_REACHED",
    "BudgetExceeded",
    "StepContext",
    "StepRegistry",
    "StepSpec",
    "append_steps",
    "create_run",
    "load_handlers",
    "registry",
    "resume_run",
    "step_handler",
]
