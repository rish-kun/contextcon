"""The `evaluate.decision_flip` step: DecisionFlip for the version `evaluate.assess` left.

Order in every run that assesses: `evaluate.assess` → `evaluate.decision_flip` →
`act.request_list`. Schedule it with `decision_flip_step(after=<evaluate step key>)`
right after each `evaluate_step(...)`; a run with several assessments (`evaluate@2`)
gets a matching `decision_flip@2`.

It costs nothing (`uses_budget=False`) and tolerates a failed assessment: it then
analyses the case's latest version, or reports that there is none. Restart-safe: a
re-claimed attempt recomputes the identical document and finds the row by its
`analysis_key`, so a version never gets two analyses.
"""

from __future__ import annotations

import uuid

from app.db import repo
from app.db.models import AssessmentVersion as VersionRow
from app.jobs import StepContext, StepSpec, step_handler
from app.pipelines.evaluate.flip import flip_for_version
from app.pipelines.evaluate.service import STEP_KEY as EVALUATE_KEY

HANDLER = "evaluate.decision_flip"
STEP_KEY = "decision_flip"
LABEL = "Work out what would change the decision"


def decision_flip_step(*, after: str = EVALUATE_KEY) -> StepSpec:
    """The step that follows the assessment step keyed `after` ("evaluate",
    "evaluate@2", ...). Its key carries the same suffix."""
    suffix = after[len(EVALUATE_KEY) :] if after.startswith(EVALUATE_KEY) else f"@{after}"
    return StepSpec(
        key=f"{STEP_KEY}{suffix}",
        handler=HANDLER,
        label=LABEL,
        input={"after": after},
        depends_on=(after,),
        uses_budget=False,
        tolerate_failed_deps=True,
    )


async def _version(ctx: StepContext) -> VersionRow | None:
    after = ctx.input.get("after") or EVALUATE_KEY
    dep = ctx.dependencies.get(after) or {}
    version_id = (dep.get("output") or {}).get("assessment_version_id")
    if dep.get("state") == "done" and version_id:
        assert ctx.run.case_id is not None
        return await repo.get_case_child(
            ctx.session,
            VersionRow,
            ctx.run.workspace_id,
            uuid.UUID(version_id),
            case_id=ctx.run.case_id,
        )
    if dep:
        ctx.log(f"assessment step {after} is {dep.get('state')}; using the latest version")
    assert ctx.run.case_id is not None
    return await repo.latest_assessment(ctx.session, ctx.run.workspace_id, ctx.run.case_id)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


@step_handler(HANDLER)
async def decision_flip(ctx: StepContext) -> dict:
    if ctx.run.case_id is None:
        raise ValueError("evaluate.decision_flip needs a case run")
    version = await _version(ctx)
    if version is None:
        ctx.result = "No assessment yet: nothing to analyse"
        return {"analysis_id": None, "created": False}
    flip = await flip_for_version(ctx.session, ctx.run.workspace_id, version, run_id=ctx.run.id)
    row, a = flip.row, flip.analysis
    blockers = row.blocker_count
    if not flip.created:
        ctx.result = f"No change: version {version.version} already analysed"
    elif a is None:
        # A version made under an older policy: stored as not reproducible; the
        # request list after this step still runs.
        ctx.result = f"Version {version.version} predates the current rules: not analysed"
    elif a.target is not None:
        ctx.result = (
            f"{_plural(blockers, 'decision blocker')} between "
            f"{a.current.value.replace('_', ' ')} and {a.target.value.replace('_', ' ')}"
        )
    else:
        ctx.result = {
            "no_blockers": "No open item stands in the way",
            "disqualified": "Deprioritise rests on verified evidence",
        }.get(a.state.value, "More evidence would not change the disposition")
    return {
        "analysis_id": str(row.id),
        "analysis_key": row.analysis_key,
        "assessment_version_id": str(version.id),
        "version": version.version,
        "created": flip.created,
        "state": row.state,
        "target": row.target,
        "blocker_count": blockers,
    }
