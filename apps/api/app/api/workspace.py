"""`GET /workspace`: the book of work in one read.

The screens that span cases (Overview, Pipeline, Signals, Approvals, Companies, and the
app shell's counts) used to read `GET /cases` and then `GET /cases/{id}` for up to
twenty cases, about fifty queries each. This route returns every case's list row and
the part of its record those screens read, built in a fixed number of queries on the
request's one session (`app.api.workspace_records`). Scoping is that of `GET /cases`:
the signed-in user's workspace, every case in it.
"""

from __future__ import annotations

from app.api import fixtures
from app.api._base import fixture_or_501, make_router
from app.api.cases_deps import Actor, CaseSession
from app.api.cases_sections import build_case_summaries
from app.api.schemas.workspace import WorkspaceOut
from app.api.workspace_records import build_workspace_records, record_from_detail
from app.db.repo import list_cases

router = make_router(tags=["cases"])


def fixture_workspace() -> WorkspaceOut:
    cases = fixtures.case_summaries()
    records = []
    for item in cases:
        detail = fixtures.case_detail(item.id)
        assert detail is not None
        records.append(record_from_detail(detail))
    return WorkspaceOut(cases=cases, records=records)


@router.get("/workspace", response_model=WorkspaceOut)
async def get_workspace(actor: Actor, session: CaseSession) -> WorkspaceOut:
    """Every case with what the cross-case screens show: claim counts by status, the
    request and its message, the latest assessment's disposition, fit and diff, events,
    documents and the directory's profile fields. The full record is `GET /cases/{id}`."""
    if actor is None or session is None:
        return fixture_or_501("CP-25", fixture_workspace)
    cases = await list_cases(session, actor.workspace_id)
    summaries = await build_case_summaries(session, actor.workspace_id, cases)
    records = await build_workspace_records(session, actor.workspace_id, cases)
    return WorkspaceOut(cases=summaries, records=records)
