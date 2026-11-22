"""The `evaluate.assess` step handler."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import AssessmentVersion as VersionRow
from app.jobs import StepContext, step_handler
from app.jobs.activity import Subject, render
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


async def _announce(ctx: StepContext, outcome) -> None:  # type: ignore[no-untyped-def]
    """Live activity: the assessment version this run wrote (statuses and scores only)."""
    a, row = outcome.assessment, outcome.version
    previous = None
    if row.previous_version_id is not None:
        previous = await ctx.session.scalar(
            select(VersionRow.disposition).where(VersionRow.id == row.previous_version_id)
        )
    fit = a.candidate.fit
    pct = getattr(fit, "assessable_pct", None)
    supported = sum(o.status.value == "supported" for o in a.outcomes)
    await ctx.activity.finding(
        render("finding.assessment", disposition=a.disposition.value),
        subject=Subject.ASSESSMENT,
        items=[
            {
                "id": str(row.id),
                "stage": "written",
                "version": row.version,
                "disposition": a.disposition.value,
                "previous_disposition": previous,
                "fit": getattr(fit, "fit", None),
                "assessable": None if pct is None else round(pct / 100 if pct > 1 else pct, 3),
            }
        ],
        counts={"supported": supported, "open": len(a.outcomes) - supported},
    )


@step_handler(HANDLER)
async def assess_case(ctx: StepContext) -> dict:
    if ctx.run.case_id is None:
        raise ValueError("evaluate.assess needs a case run")
    await ctx.activity.status(render("status.assessing"))
    failed = sorted(k for k, d in ctx.dependencies.items() if d.get("state") != "done")
    trigger = ctx.input.get("trigger") or TRIGGERS.get(ctx.run.kind, ctx.run.kind)
    outcome = await evaluate_case(
        ctx.session,
        ctx.run.workspace_id,
        ctx.run.case_id,
        today=today(),
        trigger=trigger,
        run_id=ctx.run.id,
        trigger_document_ids=[str(d) for d in ctx.input.get("document_ids") or []],
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
    await _announce(ctx, outcome)
    return {
        "assessment_version_id": str(outcome.version.id),
        "version": outcome.version.version,
        "created": outcome.created,
        "disposition": a.disposition.value,
        "inputs_hash": a.inputs_hash,
    }
