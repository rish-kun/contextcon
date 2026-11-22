"""Discover routes: thesis → criteria → search run → shortlist. Stubs until CP-17."""

from fastapi import status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.runs import RunOut
from app.api.schemas.theses import CriterionIn, ThesisCreate, ThesisOut, ThesisSummary

OWNER = "CP-17"

router = make_router(prefix="/theses", tags=["discover"])


def _fixture_thesis(thesis_id: str) -> ThesisOut:
    if thesis_id != fixtures.THESIS_ID:
        not_found("Thesis")
    return fixtures.thesis()


@router.post("", response_model=ThesisOut, status_code=status.HTTP_201_CREATED)
def create_thesis(body: ThesisCreate) -> ThesisOut:
    """Create a thesis; criteria are extracted synchronously for review before searching."""
    return fixture_or_501(OWNER, lambda: fixtures.thesis_draft(body.text))


@router.get("", response_model=list[ThesisSummary])
def list_theses() -> list[ThesisSummary]:
    return fixture_or_501(OWNER, fixtures.thesis_summaries)


@router.get("/{thesis_id}", response_model=ThesisOut)
def get_thesis(thesis_id: str) -> ThesisOut:
    """The thesis with its criteria, latest run and shortlist (ranked, then excluded)."""
    return fixture_or_501(OWNER, lambda: _fixture_thesis(thesis_id))


@router.put("/{thesis_id}/criteria", response_model=ThesisOut)
def update_criteria(thesis_id: str, body: list[CriterionIn]) -> ThesisOut:
    """Replace the criteria. Edited criteria are marked `edited`."""
    return fixture_or_501(OWNER, lambda: _fixture_thesis(thesis_id))


@router.post("/{thesis_id}/search", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def start_search(thesis_id: str) -> RunOut:
    """Start a discover run. Follow it with `GET /runs/{id}/events`."""
    return fixture_or_501(OWNER, lambda: _fixture_thesis(thesis_id).run)
