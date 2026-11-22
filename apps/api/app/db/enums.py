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
    PriorityReason,
)

__all__ = [
    "AmountBand",
    "CallStatus",
    "ClaimOrigin",
    "ClaimStatus",
    "CriterionKind",
    "CriterionResult",
    "Disposition",
    "IdentityStatus",
    "OrgType",
    "PriorityReason",
    "ResearchGoal",
    "RowOrigin",
    "RunKind",
    "RunState",
    "SendStatus",
    "StepState",
    "TERMINAL_STEP_STATES",
    "UserStatus",
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
    ORG_RESEARCH = "org_research"


class UserStatus(StrEnum):
    """`pending`: signed up while signup test mode was on and not on the allowlist.
    A pending user cannot sign in until activated."""

    ACTIVE = "active"
    PENDING = "pending"


class OrgType(StrEnum):
    ACQUIRER = "acquirer"
    INVESTOR = "investor"
    BUSINESS = "business"
    ADVISER = "adviser"


class ResearchGoal(StrEnum):
    ACQUIRE = "acquire"
    RAISE = "raise"
    BOTH = "both"


class AmountBand(StrEnum):
    """Deal size, or funding sought, in USD."""

    UNDER_0_5M = "under_0_5m"
    FROM_0_5M_TO_2M = "0_5m_2m"
    FROM_2M_TO_10M = "2m_10m"
    FROM_10M_TO_50M = "10m_50m"
    OVER_50M = "over_50m"


class RowOrigin(StrEnum):
    """Who started a thesis or an investor search: a person, or the auto-research run
    started from the organisation profile."""

    USER = "user"
    AUTO_RESEARCH = "auto_research"


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
    # Left `started` by a crashed or expired worker and settled on resume: the
    # provider may or may not have processed (and billed) it.
    UNKNOWN = "unknown"


def check_in(column: str, enum: type[StrEnum]) -> str:
    """SQL for a CHECK constraint limiting `column` to the enum's values."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
