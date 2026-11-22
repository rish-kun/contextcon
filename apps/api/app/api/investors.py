"""Investor discovery routes. Stubs until CP-18."""

from fastapi import status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.investors import (
    InvestorSearchIn,
    InvestorSearchOut,
    InvestorSearchSummary,
)

OWNER = "CP-18"

router = make_router(prefix="/investor-searches", tags=["investors"])


@router.post("", response_model=InvestorSearchOut, status_code=status.HTTP_201_CREATED)
def create_investor_search(body: InvestorSearchIn) -> InvestorSearchOut:
    """Start an investor search for a business profile. Includes the run to follow."""
    return fixture_or_501(
        OWNER,
        lambda: fixtures.investor_search().model_copy(update={"profile": body}),
    )


@router.get("", response_model=list[InvestorSearchSummary])
def list_investor_searches() -> list[InvestorSearchSummary]:
    return fixture_or_501(OWNER, fixtures.investor_summaries)


@router.get("/{search_id}", response_model=InvestorSearchOut)
def get_investor_search(search_id: str) -> InvestorSearchOut:
    """Ranked investors with the comparable rounds behind each entry."""

    def build() -> InvestorSearchOut:
        if search_id != fixtures.INVESTOR_SEARCH_ID:
            not_found("Investor search")
        return fixtures.investor_search()

    return fixture_or_501(OWNER, build)
