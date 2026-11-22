"""Exceptions shared by the job runner (`app.jobs`) and the DB adapters it hands to
step handlers (`app.db.adapters`). Defined here so neither imports the other."""

BUDGET_REACHED = "budget reached"


class BudgetExceeded(Exception):
    """A metered call would overspend the owner's credit budget. Raised by
    `StepContext.require_budget`, or by the recorder when it cannot reserve credits
    before a dispatch; the worker marks the step `skipped_budget`."""

    def __init__(self, reason: str = BUDGET_REACHED) -> None:
        super().__init__(reason)
        self.reason = reason


class LeaseLost(Exception):
    """This worker no longer holds the step (its claim token was replaced or its lease
    expired). Its result is discarded and it must not start new paid calls."""
