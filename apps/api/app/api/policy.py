"""Scoring policy route. Stub until CP-25 serialises `app.policy`."""

from app.api import fixtures
from app.api._base import fixture_or_501, make_router
from app.api.schemas.policy import PolicyOut

router = make_router(tags=["policy"])


@router.get("/policy", response_model=PolicyOut)
def get_policy() -> PolicyOut:
    """Weights, thresholds, adequacy table, required checks and the policy version."""
    return fixture_or_501("CP-25", fixtures.policy)
