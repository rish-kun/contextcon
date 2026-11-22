"""Public, read-only showcase: one real worked example, served without a session.

An operator flags one thesis (its discovery run), one case and one investor search with
`is_showcase` (migration 0007). These routes read those rows live from the database,
through the same response builders the signed-in routes use, so the shapes match the
contract exactly. Nothing that is not flagged is ever reachable here:

- every lookup starts from a flagged row; a run is served only when it belongs to the
  flagged case, the flagged thesis's discovery runs or the flagged investor search;
- the response is scrubbed: user ids blanked, recipient addresses removed, and emails
  and phone numbers redacted from every string (`scrub`);
- GET only, rate-limited per client (`PublicRateLimiter`).

The showcase data is public information only: a company's own public website, Crustdata
records and public web pages, run through the real pipelines.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections import deque
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import fixture_activity, fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.cases_sections import build_case_detail
from app.api.schemas.assessments import AssessmentVersionOut
from app.api.schemas.cases import CaseDetail
from app.api.schemas.common import ApiModel
from app.api.schemas.investors import InvestorSearchOut
from app.api.schemas.runs import ActivityPage, RunOut
from app.api.schemas.theses import ThesisOut
from app.api.theses_views import load_thesis_out
from app.auth.config import get_auth_settings
from app.auth.cookies import client_ip_info
from app.db.models import AssessmentVersion, Case, DiscoveryRun, InvestorRun, Run, Thesis
from app.db.repo import list_case_children
from app.db.session import get_sessionmaker
from app.documents.redact import regex_redactor
from app.jobs import events
from app.pipelines import evaluate
from app.pipelines import investors as investor_pipeline
from app.pipelines.memo import detail as _memo_sections  # noqa: F401  (CP-25 sections)

router = make_router(prefix="/public/showcase", tags=["showcase"])

# --- Rate limit ---------------------------------------------------------------------


class PublicRateLimiter:
    """Sliding-window request counter per client, plus one global ceiling.

    In-process, like the sign-in limiter: with several API instances the effective
    limits multiply by the instance count, which is accepted for a demo."""

    def __init__(self, per_client: int = 120, total: int = 1200, window: float = 60.0) -> None:
        self.per_client = per_client
        self.total = total
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _count(self, key: str, limit: int, now: float) -> bool:
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def allow(self, client: str | None, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._hits) > 10_000:  # bounded memory under a flood of addresses
                self._hits.clear()
            if client is not None and not self._count(f"ip:{client}", self.per_client, now):
                return False
            return self._count("*", self.total, now)


LIMITER = PublicRateLimiter()


def public_rate_limit(request: Request) -> None:
    ip, trusted = client_ip_info(request, get_auth_settings())
    # An untrusted address may be shared by every browser behind the web proxy, so it
    # only counts toward the global ceiling.
    if not LIMITER.allow(ip if trusted else None):
        raise HTTPException(429, "Too many requests. Try again in a minute.", {"Retry-After": "60"})


RateLimited = Annotated[None, Depends(public_rate_limit)]


# --- Scrubbing ----------------------------------------------------------------------

# Keys whose values identify a signed-in user or a recipient: blanked, never served.
_BLANK_KEYS = {
    "user_id",
    "entered_by_user_id",
    "approver_user_id",
    "created_by",
    "uploaded_by",
}
_DROP_KEYS = {"recipient", "recipient_email", "reply_to"}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}([T ][\d:.]+(Z|[+-]\d{2}:?\d{2})?)?")


def _scrub_text(value: str) -> str:
    if _DATE.fullmatch(value):  # a date or timestamp, never a phone number
        return value
    # The same regex redactor uploads go through (emails, Indian and international phones).
    return regex_redactor(value)[0]


def scrub(node: Any) -> Any:
    """Blank user ids, drop recipient fields, redact emails and phones in every string."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in _DROP_KEYS:
                out[k] = "" if isinstance(v, str) else None
            elif k in _BLANK_KEYS:
                out[k] = "" if isinstance(v, str) else None
            else:
                out[k] = scrub(v)
        return out
    if isinstance(node, list):
        return [scrub(v) for v in node]
    if isinstance(node, str):
        return _scrub_text(node)
    return node


def public[M: BaseModel](model: M) -> M:
    """`model`, scrubbed and re-validated against its own contract type."""
    return type(model).model_validate(scrub(model.model_dump(mode="json")))


# --- Flagged rows -------------------------------------------------------------------


async def _flagged(session: AsyncSession, model: Any) -> Any | None:
    return (
        await session.execute(
            select(model)
            .where(model.is_showcase.is_(True))
            .order_by(model.created_at.desc(), model.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


class ShowcaseOut(ApiModel):
    """What the public showcase holds. Ids are given so the pages can link the parts."""

    company_name: str | None = None
    website: str | None = None
    case_id: str | None = None
    thesis_id: str | None = None
    investor_search_id: str | None = None
    run_ids: list[str] = Field(
        default_factory=list, description="Runs whose step list and activity log are public."
    )
    provenance: str = Field(
        default=(
            "Real runs of DealProof's pipelines on public information only: the company's "
            "own public website, Crustdata records and public web pages. Nothing was sent "
            "to the company."
        )
    )


async def _showcase_runs(
    session: AsyncSession,
    case: Case | None,
    thesis: Thesis | None,
    search: InvestorRun | None,
) -> list[Run]:
    owners = []
    if case is not None:
        owners.append(Run.case_id == case.id)
    if thesis is not None:
        owners.append(
            Run.discovery_run_id.in_(
                select(DiscoveryRun.id).where(DiscoveryRun.thesis_id == thesis.id)
            )
        )
    if search is not None:
        owners.append(Run.investor_run_id == search.id)
    if not owners:
        return []
    rows = await session.execute(select(Run).where(or_(*owners)).order_by(Run.created_at))
    return list(rows.scalars())


async def _all_flagged(session: AsyncSession) -> tuple[Case | None, Thesis | None, Any]:
    return (
        await _flagged(session, Case),
        await _flagged(session, Thesis),
        await _flagged(session, InvestorRun),
    )


# --- Routes -------------------------------------------------------------------------


@router.get("", response_model=ShowcaseOut)
async def get_showcase(_: RateLimited) -> ShowcaseOut:
    """The flagged showcase records, for linking. No session needed."""
    if fixtures_enabled():
        return ShowcaseOut(
            company_name=fixtures.case_detail(fixtures.CASE_ID).case.name,
            case_id=fixtures.CASE_ID,
            thesis_id=fixtures.THESIS_ID,
            investor_search_id=fixtures.INVESTOR_SEARCH_ID,
            run_ids=[fixtures.VERIFY_RUN_ID],
        )
    async with get_sessionmaker()() as db:
        case, thesis, search = await _all_flagged(db)
        runs = await _showcase_runs(db, case, thesis, search)
        return ShowcaseOut(
            company_name=case.company_name if case else None,
            website=case.website if case else None,
            case_id=str(case.id) if case else None,
            thesis_id=str(thesis.id) if thesis else None,
            investor_search_id=str(search.id) if search else None,
            run_ids=[str(r.id) for r in runs],
        )


@router.get("/case", response_model=CaseDetail)
async def get_showcase_case(_: RateLimited) -> CaseDetail:
    """The showcase case: the full case aggregate, read-only and scrubbed."""
    if fixtures_enabled():
        detail = fixtures.case_detail(fixtures.CASE_ID)
        assert detail is not None
        return public(detail)
    async with get_sessionmaker()() as db:
        case = await _flagged(db, Case)
        if case is None:
            not_found("Showcase case")
        return public(await build_case_detail(db, case.workspace_id, case))


@router.get("/case/assessments", response_model=list[AssessmentVersionOut])
async def get_showcase_assessments(_: RateLimited) -> list[AssessmentVersionOut]:
    """Every assessment version of the showcase case, oldest first, with diffs."""
    if fixtures_enabled():
        return [public(a) for a in fixtures.assessments(fixtures.CASE_ID)]
    async with get_sessionmaker()() as db:
        case = await _flagged(db, Case)
        if case is None:
            not_found("Showcase case")
        rows = await list_case_children(db, AssessmentVersion, case.workspace_id, case.id)
        rows.sort(key=lambda r: r.version)
        return [public(a) for a in await evaluate.list_versions_out(db, case.id, rows)]


@router.get("/discovery", response_model=ThesisOut)
async def get_showcase_discovery(_: RateLimited) -> ThesisOut:
    """The showcase thesis: criteria, latest discover run and the shortlist."""
    if fixtures_enabled():
        return public(fixtures.thesis())
    async with get_sessionmaker()() as db:
        thesis = await _flagged(db, Thesis)
        if thesis is None:
            not_found("Showcase discovery")
        return public(await load_thesis_out(db, thesis.workspace_id, thesis.id))


@router.get("/investors", response_model=InvestorSearchOut)
async def get_showcase_investors(_: RateLimited) -> InvestorSearchOut:
    """The showcase investor search: ranked investors and their comparable rounds."""
    if fixtures_enabled():
        return public(fixtures.investor_search())
    async with get_sessionmaker()() as db:
        search = await _flagged(db, InvestorRun)
        if search is None:
            not_found("Showcase investor search")
        return public(
            await investor_pipeline.load_investor_search(db, search.workspace_id, search.id)
        )


async def _showcase_run(db: AsyncSession, run_id: str) -> Run:
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        not_found("Run")
    runs = await _showcase_runs(db, *(await _all_flagged(db)))
    run = next((r for r in runs if r.id == rid), None)
    if run is None:
        not_found("Run")
    return run


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_showcase_run(run_id: str, _: RateLimited) -> RunOut:
    """A showcase run with every step (other runs are 404)."""
    if fixtures_enabled():
        run = fixtures.runs().get(run_id)
        if run is None:
            not_found("Run")
        return public(run)
    async with get_sessionmaker()() as db:
        run = await _showcase_run(db, run_id)
        return public(await events.load_run_out(db, run.workspace_id, run.id))


@router.get("/runs/{run_id}/activity", response_model=ActivityPage)
async def get_showcase_run_activity(
    run_id: str,
    _: RateLimited,
    after: int = Query(default=0, ge=0, description="Return activities with seq > after."),
    limit: int = Query(default=500, ge=1, le=2000),
) -> ActivityPage:
    """A showcase run's activity log, for the read-only run log."""
    if fixtures_enabled():
        if run_id not in fixtures.runs():
            not_found("Run")
        return public(fixture_activity.page(run_id, after=after, limit=limit))
    async with get_sessionmaker()() as db:
        run = await _showcase_run(db, run_id)
        return public(
            await events.load_activity_page(db, run.workspace_id, run.id, after=after, limit=limit)
        )
