"""The records behind `GET /workspace`, for every case at once.

`record_from_detail` defines each field: it cuts a full `GET /cases/{id}` record
(`CaseDetail`) down to what the screens spanning cases read. Fixture mode uses it as is.

`build_workspace_records` computes the same values from the database for a list of
cases in a fixed number of queries (about twenty, however many cases there are), all
on the request's session. It reuses the per-case builders' own pieces (`version_out`,
`event_out`, `profile_section`, `message_status`) on rows read in batches, so the two
cannot drift apart; `tests/api/test_workspace.py` compares them field for field.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.act.pg_repository import _approval, _revision, _send
from app.act.router import _approval_out, _send_out
from app.act.service import message_status
from app.api.cases_sections import CaseContext, event_out, profile_section
from app.api.schemas.assessments import AssessmentVersionOut, FitState
from app.api.schemas.cases import CaseDetail, EventOut
from app.api.schemas.common import NamedUserOut, RunKind, RunState
from app.api.schemas.requests import PriorityReason
from app.api.schemas.workspace import (
    ClaimCountsOut,
    WorkspaceAssessmentOut,
    WorkspaceCaseOut,
    WorkspaceCriterionOut,
    WorkspaceDocumentOut,
    WorkspaceMessageOut,
    WorkspaceOpportunityOut,
    WorkspaceProfileOut,
    WorkspaceRequestItemOut,
    WorkspaceRequestListOut,
    WorkspaceRevisionOut,
    WorkspaceRunOut,
)
from app.db.enums import IdentityStatus
from app.db.models import (
    Approval,
    AssessmentVersion,
    Case,
    Claim,
    ClaimCheck,
    Criterion,
    Document,
    Event,
    Evidence,
    MessageRevision,
    RequestItem,
    RequestList,
    Run,
    SendAttempt,
    Source,
    Step,
    Thesis,
    User,
)
from app.pipelines.evaluate.cases import ACTIVE_RUN_STATES
from app.pipelines.evaluate.present import load_lookups_many, version_out
from app.pipelines.evaluate.snapshot import load_snapshots
from app.settings import get_settings

# Steps still to finish (`StepState.pending`, `StepState.running`).
_UNFINISHED_STEPS = ("pending", "running")
# The profile fields a directory row shows, plus the name a profile needs to exist.
PROFILE_PATHS = (
    "basic_info.name",
    "basic_info.primary_domain",
    "locations.headquarters",
    "locations.country",
    "headcount.total",
)


# --- The definition: a full record, cut down ------------------------------------------


def record_from_detail(d: CaseDetail) -> WorkspaceCaseOut:
    run = d.case.run
    counts = ClaimCountsOut()
    for claim in d.claims:
        setattr(counts, claim.status.value, getattr(counts, claim.status.value) + 1)
    profile = d.profile
    request_list = d.request_list
    message = d.message
    return WorkspaceCaseOut(
        case_id=d.case.id,
        owner=d.case.owner,
        run=WorkspaceRunOut(
            kind=run.kind,
            state=run.state,
            steps=len(run.steps),
            steps_finished=sum(1 for s in run.steps if s.state.value not in _UNFINISHED_STEPS),
        )
        if run
        else None,
        identity_candidates=len(d.identity.candidates),
        claim_counts=counts,
        opportunity=WorkspaceOpportunityOut(
            thesis_id=d.opportunity.thesis_id,
            thesis_text=d.opportunity.thesis_text,
            fit_state=d.opportunity.fit_state,
            fit=d.opportunity.fit,
            assessable_pct=d.opportunity.assessable_pct,
            criterion_results=[
                WorkspaceCriterionOut(
                    criterion_id=r.criterion_id,
                    label=r.label,
                    kind=r.kind,
                    weight=r.weight,
                    state=r.state,
                )
                for r in d.opportunity.criterion_results
            ],
        ),
        assessment=_assessment(d.assessment) if d.assessment else None,
        profile=WorkspaceProfileOut(
            domain=profile.domain.value if profile.domain else None,
            headquarters=profile.headquarters.value if profile.headquarters else None,
            country=profile.country.value if profile.country else None,
            headcount=profile.headcount.value if profile.headcount else None,
            headcount_basis=profile.headcount.estimate_basis if profile.headcount else None,
        )
        if profile
        else None,
        events=d.events,
        documents=[
            WorkspaceDocumentOut(
                id=doc.id,
                filename=doc.filename,
                uploaded_at=doc.uploaded_at,
                uploaded_by_name=doc.uploaded_by_name,
                purged=doc.purged,
                claims_extracted=doc.claims_extracted,
            )
            for doc in d.documents
        ],
        request_list=WorkspaceRequestListOut(
            items=[
                WorkspaceRequestItemOut(document=i.document, priority=i.priority, group=i.group)
                for i in request_list.items
            ],
            email_send_enabled=request_list.email_send_enabled,
            created_at=request_list.created_at,
        )
        if request_list
        else None,
        message=WorkspaceMessageOut(
            status=message.status,
            current_revision=WorkspaceRevisionOut(
                number=message.current_revision.number,
                recipient=message.current_revision.recipient,
                entered_by_user_id=message.current_revision.entered_by_user_id,
                created_at=message.current_revision.created_at,
            ),
            approval=message.approval,
            send=message.send,
        )
        if message
        else None,
    )


def _assessment(a: AssessmentVersionOut) -> WorkspaceAssessmentOut:
    fit = a.judgments.opportunity_fit
    return WorkspaceAssessmentOut(
        id=a.id,
        version=a.version,
        created_at=a.created_at,
        disposition=a.judgments.screening_disposition.disposition,
        fit_state=fit.state,
        fit=fit.fit,
        assessable_pct=fit.assessable_pct,
        diff_from_previous=a.diff_from_previous,
    )


# --- The batch: the same values from the database ------------------------------------


async def build_workspace_records(
    session: AsyncSession, workspace_id: uuid.UUID, cases: list[Case]
) -> list[WorkspaceCaseOut]:
    """One record per case (in the order given), equal to `record_from_detail` of the
    case's `GET /cases/{id}`. `cases` must already be scoped to `workspace_id`."""
    if not cases:
        return []
    ids = [c.id for c in cases]
    ctxs = {c.id: CaseContext(session, workspace_id, c) for c in cases}
    for ctx in ctxs.values():
        ctx._sources = {}

    runs = await _latest_runs(session, workspace_id, ids)
    owners = await _owners(session, cases)
    counts = await _claim_counts(session, ids)
    versions = await _assessments(session, workspace_id, ids)
    opportunities = await _opportunities(session, workspace_id, cases, versions)
    profiles = await _profiles(session, workspace_id, ctxs)
    events = await _events(session, workspace_id, ctxs)
    documents = await _documents(session, ids)
    request_lists, message_lists = await _request_lists(session, ids)
    messages = await _messages(session, message_lists)

    out = []
    for case in cases:
        version = versions.get(case.id)
        out.append(
            WorkspaceCaseOut(
                case_id=str(case.id),
                owner=owners[case.id],
                run=runs.get(case.id),
                identity_candidates=_candidate_count(case),
                claim_counts=counts.get(case.id, ClaimCountsOut()),
                opportunity=opportunities[case.id],
                assessment=_assessment(version) if version else None,
                profile=profiles.get(case.id),
                events=events.get(case.id, []),
                documents=documents.get(case.id, []),
                request_list=request_lists.get(case.id),
                message=messages.get(case.id),
            )
        )
    return out


def _candidate_count(case: Case) -> int:
    """`len(identity_section(...).candidates)`: listed while identity is open, or once a
    pick was recorded."""
    pick = (case.identity_identifiers or {}).get("pick")
    shown = case.identity_status != IdentityStatus.CONFIRMED or pick is not None
    return len(case.identity_candidates or []) if shown else 0


async def _latest_runs(
    session: AsyncSession, workspace_id: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, WorkspaceRunOut]:
    """`CaseOut.run`: an active run first, then the newest (`cases._latest_run`)."""
    total = select(func.count(Step.id)).where(Step.run_id == Run.id).scalar_subquery()
    finished = (
        select(func.count(Step.id))
        .where(Step.run_id == Run.id, Step.state.not_in(_UNFINISHED_STEPS))
        .scalar_subquery()
    )
    latest: dict[uuid.UUID, tuple[Any, ...]] = {}
    for row in (
        await session.execute(
            select(Run.case_id, Run.id, Run.kind, Run.state, Run.created_at, total, finished).where(
                Run.case_id.in_(ids), Run.workspace_id == workspace_id
            )
        )
    ).all():
        case_id, run_id, _kind, state, created_at, _steps, _finished = row
        key = (state in ACTIVE_RUN_STATES, created_at, run_id)
        best = latest.get(case_id)
        if best is None or key > (best[3] in ACTIVE_RUN_STATES, best[4], best[1]):
            latest[case_id] = tuple(row)
    return {
        case_id: WorkspaceRunOut(
            kind=RunKind(kind), state=RunState(state), steps=steps, steps_finished=done
        )
        for case_id, (_, _, kind, state, _, steps, done) in latest.items()
    }


async def _owners(session: AsyncSession, cases: list[Case]) -> dict[uuid.UUID, NamedUserOut]:
    """`CaseOut.owner`: the user who opened the case."""
    user_ids = {c.created_by for c in cases if c.created_by}
    names: dict[uuid.UUID, str] = {}
    if user_ids:
        names = dict(
            (
                await session.execute(
                    select(User.id, User.display_name).where(User.id.in_(user_ids))
                )
            ).all()
        )
    out = {}
    for case in cases:
        found = case.created_by is not None and case.created_by in names
        out[case.id] = NamedUserOut(
            user_id=str(case.created_by) if found else "",
            display_name=names[case.created_by] if found else "Unknown user",  # type: ignore[index]
        )
    return out


async def _claim_counts(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, ClaimCountsOut]:
    """Each claim's status is its newest check's, `not_checked` without one (the ledger)."""
    newest = (
        select(Claim.case_id, Claim.id, ClaimCheck.status)
        .outerjoin(
            ClaimCheck, (ClaimCheck.claim_id == Claim.id) & (ClaimCheck.case_id == Claim.case_id)
        )
        .where(Claim.case_id.in_(ids))
        .ext(distinct_on(Claim.id))
        .order_by(Claim.id, ClaimCheck.created_at.desc().nulls_last(), ClaimCheck.id.desc())
        .subquery()
    )
    out: dict[uuid.UUID, ClaimCountsOut] = {}
    for case_id, status, n in (
        await session.execute(
            select(newest.c.case_id, newest.c.status, func.count()).group_by(
                newest.c.case_id, newest.c.status
            )
        )
    ).all():
        counts = out.setdefault(case_id, ClaimCountsOut())
        key = status or "not_checked"
        setattr(counts, key, getattr(counts, key) + n)
    return out


async def _assessments(
    session: AsyncSession, workspace_id: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, AssessmentVersionOut]:
    """`CaseDetail.assessment`: each case's latest version, presented by `version_out`."""
    rows = list(
        (
            await session.execute(
                select(AssessmentVersion)
                .join(Case, Case.id == AssessmentVersion.case_id)
                .where(Case.workspace_id == workspace_id, AssessmentVersion.case_id.in_(ids))
                .ext(distinct_on(AssessmentVersion.case_id))
                .order_by(AssessmentVersion.case_id, AssessmentVersion.version.desc())
            )
        ).scalars()
    )
    snaps = {s.row.case_id: s for s in await load_snapshots(session, rows)}
    lookups = await load_lookups_many(session, snaps)
    return {case_id: version_out(snap, lookups[case_id]) for case_id, snap in snaps.items()}


async def _opportunities(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    cases: list[Case],
    versions: dict[uuid.UUID, AssessmentVersionOut],
) -> dict[uuid.UUID, WorkspaceOpportunityOut]:
    """`CaseDetail.opportunity` (`memo.detail.opportunity_section`), without its criteria
    definitions and relevance text."""
    thesis_ids = {c.thesis_id for c in cases if c.thesis_id is not None}
    theses: dict[uuid.UUID, Thesis] = {}
    with_criteria: set[uuid.UUID] = set()
    if thesis_ids:
        has_criteria = exists().where(Criterion.thesis_id == Thesis.id)
        for thesis, criteria in (
            await session.execute(
                select(Thesis, has_criteria).where(
                    Thesis.id.in_(thesis_ids), Thesis.workspace_id == workspace_id
                )
            )
        ).all():
            theses[thesis.id] = thesis
            if criteria:
                with_criteria.add(thesis.id)
    out = {}
    for case in cases:
        thesis = theses.get(case.thesis_id) if case.thesis_id else None
        version = versions.get(case.id)
        fit = version.judgments.opportunity_fit if version else None
        if fit is not None:
            state = fit.state
        elif case.identity_status != "confirmed":
            state = FitState.identity_unresolved
        elif thesis is None or thesis.id not in with_criteria:
            state = FitState.awaiting_strategy_criteria
        else:
            state = FitState.unavailable
        out[case.id] = WorkspaceOpportunityOut(
            thesis_id=str(thesis.id) if thesis else None,
            thesis_text=thesis.text if thesis else None,
            fit_state=state,
            fit=fit.fit if fit else None,
            assessable_pct=fit.assessable_pct if fit else 0,
            criterion_results=[
                WorkspaceCriterionOut(
                    criterion_id=r.criterion_id,
                    label=r.label,
                    kind=r.kind,
                    weight=r.weight,
                    state=r.state,
                )
                for r in (fit.criterion_results if fit else [])
            ],
        )
    return out


def _case_source(workspace_id: uuid.UUID, case_id_column: Any) -> Any:
    """Join condition for an evidence row's source, as `CaseContext.sources` scopes it."""
    return (
        (Source.id == Evidence.source_id)
        & (Source.case_id == case_id_column)
        & (Source.workspace_id == workspace_id)
    )


async def _profiles(
    session: AsyncSession, workspace_id: uuid.UUID, ctxs: dict[uuid.UUID, CaseContext]
) -> dict[uuid.UUID, WorkspaceProfileOut]:
    """`CaseDetail.profile`, built by `profile_section` from the evidence of the fields
    shown (the section keeps the latest row per field, in creation order)."""
    confirmed = [cid for cid, ctx in ctxs.items() if ctx.entity_ref is not None]
    if not confirmed:
        return {}
    rows: dict[uuid.UUID, list[Evidence]] = {cid: [] for cid in confirmed}
    for ev, src in (
        await session.execute(
            select(Evidence, Source)
            .join(Source, _case_source(workspace_id, Evidence.case_id))
            .where(Evidence.case_id.in_(confirmed), Evidence.field_path.in_(PROFILE_PATHS))
            .order_by(Evidence.case_id, Evidence.created_at)
        )
    ).all():
        rows[ev.case_id].append(ev)
        ctxs[ev.case_id]._sources[src.id] = src  # type: ignore[index]
    out = {}
    for cid in confirmed:
        ctx = ctxs[cid]
        ctx._evidence = rows[cid]
        profile = await profile_section(ctx)
        ctx._evidence = None
        if profile is None:
            continue
        out[cid] = WorkspaceProfileOut(
            domain=profile.domain.value if profile.domain else None,
            headquarters=profile.headquarters.value if profile.headquarters else None,
            country=profile.country.value if profile.country else None,
            headcount=profile.headcount.value if profile.headcount else None,
            headcount_basis=profile.headcount.estimate_basis if profile.headcount else None,
        )
    return out


async def _events(
    session: AsyncSession, workspace_id: uuid.UUID, ctxs: dict[uuid.UUID, CaseContext]
) -> dict[uuid.UUID, list[EventOut]]:
    """`CaseDetail.events`, newest first, each with its evidence and source."""
    out: dict[uuid.UUID, list[EventOut]] = defaultdict(list)
    for event, ev, src in (
        await session.execute(
            select(Event, Evidence, Source)
            .join(Evidence, Evidence.id == Event.evidence_id)
            .join(Source, _case_source(workspace_id, Event.case_id))
            .where(Event.case_id.in_(list(ctxs)))
            .order_by(Event.case_id, Event.event_date.desc())
        )
    ).all():
        ctx = ctxs[event.case_id]
        ctx._sources[src.id] = src  # type: ignore[index]
        out[event.case_id].append(await event_out(ctx, event, ev))
    return out


async def _documents(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[WorkspaceDocumentOut]]:
    """`CaseDetail.documents` (`memo.records.documents_out`), oldest first."""
    claims = select(func.count(Claim.id)).where(Claim.document_id == Document.id).scalar_subquery()
    docs = (
        await session.execute(
            select(Document, User.display_name, claims)
            .outerjoin(User, User.id == Document.uploaded_by)
            .where(Document.case_id.in_(ids))
            .order_by(Document.case_id, Document.created_at, Document.id)
        )
    ).all()
    out: dict[uuid.UUID, list[WorkspaceDocumentOut]] = defaultdict(list)
    for d, name, extracted in docs:
        out[d.case_id].append(
            WorkspaceDocumentOut(
                id=str(d.id),
                filename=d.filename,
                uploaded_at=d.created_at,
                uploaded_by_name=name,
                purged=d.deleted_at is not None,
                claims_extracted=int(extracted or 0),
            )
        )
    return out


async def _request_lists(
    session: AsyncSession, ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, WorkspaceRequestListOut], dict[uuid.UUID, RequestList]]:
    """`CaseDetail.request_list` (`cases_act.request_list_section`), and the list each
    case's message hangs on (`cases_act._message_list`): the latest list when it has a
    revision, else the latest list that has one."""
    has_revision = exists().where(MessageRevision.request_list_id == RequestList.id)
    latest: dict[uuid.UUID, RequestList] = {}
    message_lists: dict[uuid.UUID, RequestList] = {}
    revised: set[uuid.UUID] = set()
    for rl, with_revision in (
        await session.execute(
            select(RequestList, has_revision)
            .where(RequestList.case_id.in_(ids))
            .order_by(RequestList.case_id, RequestList.created_at.desc(), RequestList.id.desc())
        )
    ).all():
        if with_revision:
            revised.add(rl.id)
            message_lists.setdefault(rl.case_id, rl)  # the latest list with a revision
        if rl.assessment_version_id is not None:
            latest.setdefault(rl.case_id, rl)
    for case_id, rl in latest.items():
        if rl.id in revised:
            message_lists[case_id] = rl
    items: dict[uuid.UUID, list[WorkspaceRequestItemOut]] = defaultdict(list)
    if latest:
        for row in (
            await session.execute(
                select(RequestItem)
                .where(RequestItem.request_list_id.in_([rl.id for rl in latest.values()]))
                .order_by(RequestItem.request_list_id, RequestItem.position)
            )
        ).scalars():
            needed = PriorityReason(row.priority_reason) is PriorityReason.decision_blocker
            items[row.request_list_id].append(
                WorkspaceRequestItemOut(
                    document=row.document_requested,
                    priority=row.priority,
                    group="needed" if needed else "also_helpful",
                )
            )
    enabled = get_settings().email_send_enabled
    lists = {
        case_id: WorkspaceRequestListOut(
            items=items.get(rl.id, []), email_send_enabled=enabled, created_at=rl.created_at
        )
        for case_id, rl in latest.items()
    }
    return lists, message_lists


async def _messages(
    session: AsyncSession, lists: dict[uuid.UUID, RequestList]
) -> dict[uuid.UUID, WorkspaceMessageOut]:
    """`CaseDetail.message` (`ActService.get_state`): the current revision, its approval,
    the latest send, and the status they give."""
    if not lists:
        return {}
    list_ids = [rl.id for rl in lists.values()]
    current: dict[uuid.UUID, tuple[MessageRevision, Approval | None]] = {
        revision.request_list_id: (revision, approval)
        for revision, approval in (
            await session.execute(
                select(MessageRevision, Approval)
                .outerjoin(Approval, Approval.message_revision_id == MessageRevision.id)
                .where(MessageRevision.request_list_id.in_(list_ids))
                .ext(distinct_on(MessageRevision.request_list_id))
                .order_by(
                    MessageRevision.request_list_id,
                    MessageRevision.revision.desc(),
                    Approval.approved_at.desc().nulls_last(),
                    Approval.created_at.desc().nulls_last(),
                )
            )
        ).all()
    }
    sends = {
        s.request_list_id: s
        for s in (
            await session.execute(
                select(SendAttempt)
                .where(SendAttempt.request_list_id.in_(list_ids))
                .ext(distinct_on(SendAttempt.request_list_id))
                .order_by(
                    SendAttempt.request_list_id,
                    SendAttempt.created_at.desc(),
                    SendAttempt.id.desc(),
                )
            )
        ).scalars()
    }
    out = {}
    for case_id, rl in lists.items():
        if rl.id not in current:
            continue
        row, approval_row = current[rl.id]
        revision = _revision(row)
        approval = _approval(approval_row, rl.id) if approval_row else None
        send_row = sends.get(rl.id)
        send = _send(send_row, rl.case_id) if send_row else None
        out[case_id] = WorkspaceMessageOut(
            status=message_status(revision, approval, send),
            current_revision=WorkspaceRevisionOut(
                number=revision.number,
                recipient=revision.recipient,
                entered_by_user_id=revision.entered_by_user_id,
                created_at=revision.created_at,
            ),
            approval=_approval_out(approval) if approval else None,
            send=_send_out(send) if send else None,
        )
    return out
