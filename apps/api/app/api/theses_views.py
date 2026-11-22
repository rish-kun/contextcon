"""Database rows → the Discover contract (`ThesisOut`, `ThesisSummary`)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.common import EntityAttachment, EvidenceOut, SourceClass, SourceRef
from app.api.schemas.theses import (
    CriterionOut,
    CriterionResultOut,
    ShortlistCardOut,
    ShortlistItemOut,
    ThesisOut,
    ThesisStatus,
    ThesisSummary,
)
from app.db import repo
from app.db.models import Candidate, Evidence, Source, Thesis
from app.jobs import events
from app.pipelines.discover import criteria as crit
from app.pipelines.discover.service import latest_discovery_run, run_for

FIT_UNAVAILABLE = "No criterion could be assessed from the available data, so fit is unavailable."

_STATUS = {
    "pending": ThesisStatus.searching,
    "running": ThesisStatus.searching,
    "done": ThesisStatus.ready,
    "failed": ThesisStatus.failed,
}


def source_class(value: str) -> SourceClass:
    try:
        return SourceClass(value)
    except ValueError:
        return SourceClass.data_provider


def source_ref(row: Source) -> SourceRef:
    return SourceRef(
        source_id=str(row.id),
        provider=row.provider,
        label=row.title or row.provider,
        url_or_endpoint=row.endpoint_or_url,
        retrieved_at=row.retrieved_at,
        source_class=source_class(row.source_class),
    )


def criterion_out(row: Any) -> CriterionOut:
    return CriterionOut(
        id=str(row.id),
        position=row.position,
        label=row.label,
        kind=row.kind,
        dimension=row.dimension,
        operator=row.operator,
        value=row.value,
        crustdata_filter=row.crustdata_filter,
        assessed_from_evidence=row.crustdata_filter is None,
        edited=bool(row.edited),
    )


async def _evidence(session: AsyncSession, ids: set[str]) -> dict[str, tuple[Evidence, Source]]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Evidence, Source)
            .join(Source, Source.id == Evidence.source_id)
            .where(Evidence.id.in_([uuid.UUID(i) for i in ids]))
        )
    ).all()
    return {str(e.id): (e, s) for e, s in rows}


async def shortlist_out(
    session: AsyncSession, thesis: Thesis, discovery_run_id: uuid.UUID
) -> list[ShortlistItemOut]:
    candidates = list(
        (
            await session.execute(
                select(Candidate)
                .where(Candidate.discovery_run_id == discovery_run_id)
                .options(selectinload(Candidate.criterion_results))
            )
        ).scalars()
    )
    candidates.sort(key=lambda c: (c.excluded, c.rank or 10**6, c.name.casefold()))
    labels = {str(c.id): c for c in thesis.criteria}
    wanted = {e for c in candidates for r in c.criterion_results for e in r.evidence_ids or []}
    evidence = await _evidence(session, wanted)
    out: list[ShortlistItemOut] = []
    for c in candidates:
        results = []
        for r in sorted(
            c.criterion_results,
            key=lambda r: (
                labels[str(r.criterion_id)].position if str(r.criterion_id) in labels else 10**6
            ),
        ):
            row = labels.get(str(r.criterion_id))
            if row is None:
                continue
            ev = []
            for eid in r.evidence_ids or []:
                if eid not in evidence:
                    continue
                e, s = evidence[eid]
                ev.append(
                    EvidenceOut(
                        evidence_id=eid,
                        source=source_ref(s),
                        field_path=e.field_path,
                        value=e.value,
                        as_of=e.as_of,
                        attached_to=EntityAttachment(
                            entity_name=c.name,
                            matched_on=["crustdata_company_id"],
                            identity_confidence=e.identity_confidence,
                        ),
                    )
                )
            results.append(
                CriterionResultOut(
                    criterion_id=str(r.criterion_id),
                    label=row.label,
                    kind=row.kind,
                    weight=crit.policy_weight(row.kind),
                    state=r.result,
                    reason=r.reason,
                    evidence=ev,
                )
            )
        out.append(
            ShortlistItemOut(
                id=str(c.id),
                rank=c.rank,
                crustdata_company_id=int(c.crustdata_company_id or 0),
                name=c.name,
                domain=c.domain,
                fit=c.fit,
                fit_unavailable_reason=FIT_UNAVAILABLE if c.fit is None else None,
                assessable_pct=c.assessable_pct,
                excluded=c.excluded,
                exclusion_reason=c.exclusion_reason,
                criterion_results=results,
                card=ShortlistCardOut.model_validate(c.card),
            )
        )
    return out


async def thesis_out(session: AsyncSession, workspace_id: uuid.UUID, thesis: Thesis) -> ThesisOut:
    dr = await latest_discovery_run(session, thesis.id)
    run = await run_for(session, dr.id) if dr is not None else None
    status = ThesisStatus.failed if thesis.status == "failed" else ThesisStatus.draft
    run_out = None
    shortlist: list[ShortlistItemOut] = []
    if run is not None and dr is not None:
        status = _STATUS.get(run.state, ThesisStatus.searching)
        run_out = await events.load_run_out(session, workspace_id, run.id)
        shortlist = await shortlist_out(session, thesis, dr.id)
    return ThesisOut(
        id=str(thesis.id),
        text=thesis.text,
        status=status,
        created_at=thesis.created_at,
        criteria=[criterion_out(c) for c in thesis.criteria],
        run=run_out,
        shortlist=shortlist,
    )


async def load_thesis_out(
    session: AsyncSession, workspace_id: uuid.UUID, thesis_id: uuid.UUID
) -> ThesisOut:
    thesis = await repo.get_thesis(session, workspace_id, thesis_id)
    return await thesis_out(session, workspace_id, thesis)


async def list_thesis_summaries(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[ThesisSummary]:
    theses = list(
        (
            await session.execute(
                repo.scoped(Thesis, workspace_id)
                .options(selectinload(Thesis.criteria))
                .order_by(Thesis.created_at.desc())
            )
        ).scalars()
    )
    out: list[ThesisSummary] = []
    for t in theses:
        dr = await latest_discovery_run(session, t.id)
        run = await run_for(session, dr.id) if dr is not None else None
        count = 0
        if run is not None and dr is not None:
            count = (
                await session.scalar(
                    select(func.count())
                    .select_from(Candidate)
                    .where(Candidate.discovery_run_id == dr.id, Candidate.excluded.is_(False))
                )
            ) or 0
        status = ThesisStatus.failed if t.status == "failed" else ThesisStatus.draft
        if run is not None:
            status = _STATUS.get(run.state, ThesisStatus.searching)
        out.append(
            ThesisSummary(
                id=str(t.id),
                text=t.text,
                status=status,
                created_at=t.created_at,
                criteria_count=len(t.criteria),
                shortlist_count=count,
                latest_run_id=str(run.id) if run is not None else None,
            )
        )
    return out
