"""Case routes. Create/identity/verify: CP-19. Assessments: CP-22. Memo aggregate: CP-25."""

from fastapi import status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.assessments import AssessmentVersionOut
from app.api.schemas.cases import (
    CaseCreate,
    CaseCriteriaIn,
    CaseDetail,
    CaseOut,
    CaseSummary,
    IdentityPickIn,
)
from app.api.schemas.runs import RunOut

router = make_router(prefix="/cases", tags=["cases"])


def _fixture_case(case_id: str) -> CaseOut:
    case = fixtures.case_out(case_id)
    if case is None:
        not_found("Case")
    return case


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(body: CaseCreate) -> CaseOut:
    """Open a case from a shortlist item, or from a name and website. Starts a verify run."""
    return fixture_or_501("CP-19", lambda: _fixture_case(fixtures.CASE_ID))


@router.get("", response_model=list[CaseSummary])
def list_cases() -> list[CaseSummary]:
    """Cases dashboard: disposition, fit with coverage, and cost per case."""
    return fixture_or_501("CP-25", fixtures.case_summaries)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str) -> CaseDetail:
    """The finished-case memo aggregate, sections in PRD order."""

    def build() -> CaseDetail:
        detail = fixtures.case_detail(case_id)
        if detail is None:
            not_found("Case")
        return detail

    return fixture_or_501("CP-25", build)


@router.post("/{case_id}/identity", response_model=CaseOut)
def pick_identity(case_id: str, body: IdentityPickIn) -> CaseOut:
    """Pick one candidate when identity is ambiguous or unresolved. Records who and when."""
    return fixture_or_501("CP-19", lambda: _fixture_case(case_id))


@router.post("/{case_id}/verify", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def start_verify(case_id: str) -> RunOut:
    """Start (or re-run) verification for the case."""

    def build() -> RunOut:
        case = _fixture_case(case_id)
        assert case.run is not None
        return case.run

    return fixture_or_501("CP-19", build)


@router.put("/{case_id}/criteria", response_model=CaseOut)
def set_case_criteria(case_id: str, body: CaseCriteriaIn) -> CaseOut:
    """Strategy criteria for a direct-verify case, needed before any fit score is issued."""
    return fixture_or_501("CP-22", lambda: _fixture_case(case_id))


@router.get("/{case_id}/assessments", response_model=list[AssessmentVersionOut])
def list_assessments(case_id: str) -> list[AssessmentVersionOut]:
    """Every assessment version, oldest first, each with its diff from the previous one."""

    def build() -> list[AssessmentVersionOut]:
        _fixture_case(case_id)
        return fixtures.assessments(case_id)

    return fixture_or_501("CP-22", build)
