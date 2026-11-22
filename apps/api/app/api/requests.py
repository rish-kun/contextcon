"""Act routes: request list, message revisions, named approval, send once. Stubs: CP-23."""

from fastapi import status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.requests import RequestApproveIn, RequestUpdateIn, SellerRequestOut

OWNER = "CP-23"

router = make_router(tags=["act"])


def _fixture(request_id: str, state: str) -> SellerRequestOut:
    if request_id != fixtures.REQUEST_ID:
        not_found("Request")
    return fixtures.seller_request(state)


@router.post(
    "/cases/{case_id}/requests",
    response_model=SellerRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_request(case_id: str) -> SellerRequestOut:
    """Build the request list from the latest assessment and draft one consolidated email."""

    def build() -> SellerRequestOut:
        if fixtures.case_out(case_id) is None:
            not_found("Case")
        return fixtures.seller_request("draft")

    return fixture_or_501(OWNER, build)


@router.get("/requests/{request_id}", response_model=SellerRequestOut)
def get_request(request_id: str) -> SellerRequestOut:
    return fixture_or_501(OWNER, lambda: _fixture(request_id, "suppressed"))


@router.patch(
    "/requests/{request_id}",
    response_model=SellerRequestOut,
    responses={409: {"description": "Already sending or sent."}},
)
def update_request(request_id: str, body: RequestUpdateIn) -> SellerRequestOut:
    """Edit recipient, subject or body. Creates a new revision and clears any approval."""
    return fixture_or_501(OWNER, lambda: _fixture(request_id, "edited"))


@router.post(
    "/requests/{request_id}/approve",
    response_model=SellerRequestOut,
    responses={409: {"description": "Revision is not the current one, or no recipient."}},
)
def approve_request(request_id: str, body: RequestApproveIn) -> SellerRequestOut:
    """Approve one exact revision as the signed-in user (name and time recorded)."""
    return fixture_or_501(OWNER, lambda: _fixture(request_id, "approved"))


@router.post(
    "/requests/{request_id}/send",
    response_model=SellerRequestOut,
    responses={409: {"description": "Not approved, or the approval is stale."}},
)
def send_request(request_id: str) -> SellerRequestOut:
    """Send the approved revision once. Repeat calls return the existing send state."""
    return fixture_or_501(OWNER, lambda: _fixture(request_id, "suppressed"))
