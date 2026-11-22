"""Start an investor search and read it back in the API contract's shape."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import SourceClass, SourceRef
from app.api.schemas.investors import (
    ComparableRoundOut,
    FundingCompatibility,
    InvestorEntryOut,
    InvestorSearchIn,
    InvestorSearchOut,
    InvestorSearchSummary,
)
from app.api.schemas.theses import ThesisStatus
from app.db import repo
from app.db.enums import RunKind, RunState
from app.db.models import InvestorEntry, InvestorRun, Run, Source
from app.jobs import create_run
from app.jobs.events import load_run_out
from app.pipelines.investors.steps import step_specs

PROFILE_KEYS = ("sector", "location", "stage", "size", "funding_sought")


async def start_investor_search(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    profile: InvestorSearchIn,
    *,
    created_by: uuid.UUID | None = None,
    budget_credits: Decimal | float | None = None,
    search_limit: int | None = None,
    enrich_limit: int | None = None,
) -> tuple[InvestorRun, Run]:
    """Insert the investor run and its job run (budget `INVESTOR_CREDIT_BUDGET` unless
    given). Commits, so the worker can pick it up."""
    row = InvestorRun(
        workspace_id=workspace_id,
        created_by=created_by,
        profile=profile.model_dump(mode="json"),
        status="searching",
    )
    session.add(row)
    await session.flush()
    run = await create_run(
        session,
        workspace_id=workspace_id,
        kind=RunKind.INVESTOR_DISCOVER,
        investor_run_id=row.id,
        budget_credits=budget_credits,
        created_by=created_by,
        steps=step_specs(search_limit=search_limit, enrich_limit=enrich_limit),
    )
    await session.commit()
    return row, run


def _status(run: Run | None) -> ThesisStatus:
    if run is None:
        return ThesisStatus.draft
    if run.state == RunState.DONE:
        return ThesisStatus.ready
    if run.state == RunState.FAILED:
        return ThesisStatus.failed
    return ThesisStatus.searching


async def _latest_run(session: AsyncSession, investor_run_id: uuid.UUID) -> Run | None:
    return (
        await session.execute(
            select(Run)
            .where(Run.investor_run_id == investor_run_id)
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _profile_in(profile: dict[str, Any]) -> InvestorSearchIn:
    return InvestorSearchIn.model_validate({k: profile.get(k) or "" for k in PROFILE_KEYS})


def _source_ref(src: Source) -> SourceRef:
    return SourceRef(
        source_id=str(src.id),
        provider=src.provider,
        label="Crustdata funding record",
        url_or_endpoint=src.endpoint_or_url,
        retrieved_at=src.retrieved_at,
        source_class=SourceClass(src.source_class),
    )


async def load_investor_search(
    session: AsyncSession, workspace_id: uuid.UUID, investor_run_id: uuid.UUID
) -> InvestorSearchOut:
    """Raises `repo.NotFound` for an unknown id or another workspace's search."""
    row = await repo.get_investor_run(session, workspace_id, investor_run_id)
    run = await _latest_run(session, row.id)
    search: dict[str, Any] = (row.profile or {}).get("search") or {}
    extras: dict[str, Any] = search.get("entries") or {}
    entries = list(
        (
            await session.execute(
                select(InvestorEntry)
                .where(InvestorEntry.investor_run_id == row.id)
                .order_by(InvestorEntry.rank, InvestorEntry.investor_key)
            )
        ).scalars()
    )
    source_ids = {
        uuid.UUID(r["source_id"])
        for e in entries
        for r in e.comparable_rounds
        if r.get("source_id")
    }
    sources = (
        {
            s.id: s
            for s in (
                await session.execute(
                    select(Source).where(
                        Source.id.in_(source_ids), Source.workspace_id == workspace_id
                    )
                )
            ).scalars()
        }
        if source_ids
        else {}
    )
    scope_note = search.get("scope_note")
    out_entries: list[InvestorEntryOut] = []
    for e in entries:
        rounds = []
        for r in e.comparable_rounds:
            src = sources.get(uuid.UUID(r["source_id"])) if r.get("source_id") else None
            if src is None:
                continue  # a round without its source is never shown
            rounds.append(
                ComparableRoundOut(
                    company_id=r["company_id"],
                    company_name=r["company_name"],
                    round_type=r.get("round_type"),
                    date=dt.date.fromisoformat(r["date"]),
                    amount_usd=r.get("amount_usd"),
                    source=_source_ref(src),
                    evidence_id=r.get("evidence_id"),
                )
            )
        extra = extras.get(e.investor_key) or {}
        out_entries.append(
            InvestorEntryOut(
                id=str(e.id),
                rank=e.rank or 0,
                investor_name=e.investor_name,
                investor_key=e.investor_key,
                investor_uuid=e.investor_uuid,
                score=e.score,
                comparable_rounds=rounds,
                latest_sector_investment_found=e.last_sector_investment,
                latest_sector_investment_scope=scope_note,
                why=e.why,
                compatibility=FundingCompatibility(extra.get("compatibility", "unknown")),
                funding_kind_compatibility=extra.get("compatibility_text")
                or "compatibility unknown",
                unknowns=list(e.unknowns or []),
                possible_duplicate_of=e.possible_duplicate_of,
                possible_duplicates=list(extra.get("possible_duplicates") or []),
            )
        )
    searched_at = search.get("searched_at")
    return InvestorSearchOut(
        id=str(row.id),
        profile=_profile_in(row.profile or {}),
        status=_status(run),
        created_at=row.created_at,
        searched_at=dt.datetime.fromisoformat(searched_at) if searched_at else None,
        scope_note=scope_note,
        comparables_considered=int(search.get("comparables_considered") or 0),
        funding_kind_sought=search.get("funding_kind_sought"),
        rounds_read=int(search.get("rounds_read") or 0),
        rounds_excluded=int(search.get("rounds_excluded") or 0),
        run=await load_run_out(session, workspace_id, run.id) if run else None,
        entries=out_entries,
    )


async def list_investor_searches(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[InvestorSearchSummary]:
    counts = (
        select(InvestorEntry.investor_run_id, func.count().label("n"))
        .group_by(InvestorEntry.investor_run_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(InvestorRun, counts.c.n)
            .outerjoin(counts, counts.c.investor_run_id == InvestorRun.id)
            .where(InvestorRun.workspace_id == workspace_id)
            .order_by(InvestorRun.created_at.desc())
        )
    ).all()
    out = []
    for row, n in rows:
        profile = _profile_in(row.profile or {})
        out.append(
            InvestorSearchSummary(
                id=str(row.id),
                sector=profile.sector,
                location=profile.location,
                stage=profile.stage,
                status=_status(await _latest_run(session, row.id)),
                created_at=row.created_at,
                entries_count=int(n or 0),
            )
        )
    return out
