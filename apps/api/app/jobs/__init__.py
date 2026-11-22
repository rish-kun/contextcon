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
