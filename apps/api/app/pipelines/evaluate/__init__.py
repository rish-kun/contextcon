"""Evaluate (CP-22): case records → `rules.assess` → immutable assessment versions.

Importing this package registers the `evaluate.assess` and `evaluate.decision_flip`
step handlers. Verify and recheck runs end with `evaluate_step(depends_on=[...])`
followed by `decision_flip_step(after=<its key>)`.
"""

from app.pipelines.evaluate import flip_step as _flip_step  # noqa: F401  (registers)
from app.pipelines.evaluate import step as _step  # noqa: F401  (registers the handler)
from app.pipelines.evaluate.cases import case_out, queue_evaluation, set_case_criteria
from app.pipelines.evaluate.flip_step import decision_flip_step
from app.pipelines.evaluate.inputs import load_inputs
from app.pipelines.evaluate.present import list_versions_out
from app.pipelines.evaluate.service import (
    HANDLER,
    STEP_KEY,
    EvaluationOutcome,
    evaluate_case,
    evaluate_step,
    stored_assessment,
)
from app.pipelines.evaluate.snapshot import Snapshot, load_snapshot

__all__ = [
    "HANDLER",
    "STEP_KEY",
    "Snapshot",
    "EvaluationOutcome",
    "case_out",
    "decision_flip_step",
    "evaluate_case",
    "evaluate_step",
    "list_versions_out",
    "load_inputs",
    "load_snapshot",
    "queue_evaluation",
    "set_case_criteria",
    "stored_assessment",
]
