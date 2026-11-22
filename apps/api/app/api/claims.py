"""Typed claim intake. Stub until CP-20."""

from fastapi import status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.claims import ClaimCreate, ClaimOut

router = make_router(tags=["claims"])


@router.post(
    "/cases/{case_id}/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED
)
def add_claim(case_id: str, body: ClaimCreate) -> ClaimOut:
    """Add a typed claim. It is categorised and checked like a document claim."""

    def build() -> ClaimOut:
        if fixtures.case_out(case_id) is None:
            not_found("Case")
        return fixtures.typed_claim(body.text)

    return fixture_or_501("CP-20", build)
