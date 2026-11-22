"""Act, part 1: the request list and drafted seller email. Stubs until CP-23.

Message revisions, approval and send-once live in `app.act.router`, mounted by
`app.api.router` under `/cases/{case_id}/messages`.
"""

from fastapi import status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.requests import RequestListOut

OWNER = "CP-23"

router = make_router(prefix="/cases/{case_id}/requests", tags=["act"])


def _fixture(case_id: str) -> RequestListOut:
    if case_id != fixtures.CASE_ID:
        not_found("Request list")
    return fixtures.request_list()


@router.post("", response_model=RequestListOut, status_code=status.HTTP_201_CREATED)
def create_request_list(case_id: str) -> RequestListOut:
    """Build the request list from the latest assessment and draft one consolidated email."""
    return fixture_or_501(OWNER, lambda: _fixture(case_id))


@router.get("", response_model=RequestListOut)
def get_request_list(case_id: str) -> RequestListOut:
    """The latest request list for the case."""
    return fixture_or_501(OWNER, lambda: _fixture(case_id))
