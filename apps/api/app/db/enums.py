"""String values stored in the database.

These match the shared vocabulary in `app.domain` (built in parallel). Columns store
plain strings and the database enforces the allowed set with CHECK constraints, so
the two modules only have to agree on values; `tests/db/test_enums.py` checks that
they do whenever `app.domain` is importable.
"""

from enum import StrEnum


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    PARTIALLY_CORROBORATED = "partially_corroborated"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    CANNOT_VERIFY = "cannot_verify"
    NOT_CHECKED = "not_checked"


class Disposition(StrEnum):
    PRIORITISE = "prioritise"
    INVESTIGATE_FURTHER = "investigate_further"
    DEPRIORITISE = "deprioritise"
    CANNOT_ASSESS = "cannot_assess"


class CriterionKind(StrEnum):
    MUST = "must"
    PREFERENCE = "preference"


class CriterionResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class IdentityStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class ClaimOrigin(StrEnum):
    DECK = "deck"
    TYPED = "typed"
    PROFILE = "profile"


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
    PENDING = "pending"
    SENT = "sent"
    SUPPRESSED_TEST_MODE = "suppressed_test_mode"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def check_in(column: str, enum: type[StrEnum]) -> str:
    """SQL for a CHECK constraint limiting `column` to the enum's values."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
