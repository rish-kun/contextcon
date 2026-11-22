"""Evaluate (CP-22): case records → `rules.assess` → immutable assessment versions.

Importing this package registers the `evaluate.assess` step handler. Verify and
recheck runs end with `evaluate_step(depends_on=[...])`.
"""

from app.pipelines.evaluate import step as _step  # noqa: F401  (registers the handler)
from app.pipelines.evaluate.cases import case_out, queue_evaluation, set_case_criteria
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
    "evaluate_case",
    "evaluate_step",
    "list_versions_out",
    "load_inputs",
    "load_snapshot",
    "queue_evaluation",
    "set_case_criteria",
    "stored_assessment",
]
