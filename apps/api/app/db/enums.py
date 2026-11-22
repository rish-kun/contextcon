"""String values stored in the database.

Claim statuses, dispositions, criterion kinds/results and identity states come from
the shared vocabulary in `app.domain.enums`. The rest are persistence-level states.
Columns store plain strings; CHECK constraints enforce the allowed sets.
"""

from enum import StrEnum

from app.domain.enums import (
    ClaimStatus,
    CriterionKind,
    CriterionResult,
    Disposition,
    IdentityStatus,
)

__all__ = [
    "CallStatus",
    "ClaimOrigin",
    "ClaimStatus",
    "CriterionKind",
    "CriterionResult",
    "Disposition",
    "IdentityStatus",
    "RunKind",
    "RunState",
    "SendStatus",
    "StepState",
    "TERMINAL_STEP_STATES",
    "check_in",
]


class ClaimOrigin(StrEnum):
    DECK = "deck"
    TYPED = "typed"
    PROFILE = "profile"


class RunKind(StrEnum):
    """Matches the API contract's RunKind."""

    DISCOVER = "discover"
    INVESTOR_DISCOVER = "investor_discover"
    VERIFY = "verify"
    EVALUATE = "evaluate"
    RECHECK = "recheck"


class RunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class StepState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED_BUDGET = "skipped_budget"


TERMINAL_STEP_STATES = frozenset(
    {StepState.DONE, StepState.FAILED, StepState.SKIPPED_BUDGET},
)


class SendStatus(StrEnum):
    # `pending` is the reserved-before-calling-the-provider state (`sending` in app.act).
    PENDING = "pending"
    SENT = "sent"
    SUPPRESSED_TEST_MODE = "suppressed_test_mode"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CallStatus(StrEnum):
    """Mirrors `app.clients.base.CallStatus`."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CACHE_HIT = "cache_hit"


def check_in(column: str, enum: type[StrEnum]) -> str:
    """SQL for a CHECK constraint limiting `column` to the enum's values."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
