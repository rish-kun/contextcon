"""Discover operations behind the `/theses` routes.

- `create_thesis`: extract criteria from the thesis (LLM, quote-checked) and store the
  thesis with editable criteria. The extraction cost is charged to a draft discovery
  run, which the first search then uses (costs never go to a case).
- `replace_criteria`: save the user's edits (kept ids stay, new rows are `edited`).
- `start_search`: freeze the criteria into the discovery run and enqueue the run with
  the discover credit budget (`DISCOVER_CREDIT_BUDGET`, default 100).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import repo
from app.db.adapters import DbCache, DbCallRecorder
from app.db.enums import RunKind, RunState
from app.db.ledger import CostContext
from app.db.models import Criterion, DiscoveryRun, Run, Thesis
from app.extraction.criteria import CRUSTDATA_FIELDS, extract_criteria
from app.jobs import create_run
from app.jobs.config import get_job_settings
from app.pipelines.discover import criteria as crit
from app.pipelines.discover.clients import factories
from app.pipelines.discover.steps import step_specs

DRAFT = "draft"

LlmFactory = Callable[..., Any]


class SearchInProgress(RuntimeError):
    """Criteria cannot change while a search on them is running."""


class InvalidCriteria(ValueError):
    pass


async def latest_discovery_run(session: AsyncSession, thesis_id: uuid.UUID) -> DiscoveryRun | None:
    return (
        await session.execute(
            select(DiscoveryRun)
            .where(DiscoveryRun.thesis_id == thesis_id)
            .order_by(DiscoveryRun.created_at.desc(), DiscoveryRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def run_for(session: AsyncSession, discovery_run_id: uuid.UUID) -> Run | None:
    return (
        await session.execute(
            select(Run)
            .where(Run.discovery_run_id == discovery_run_id)
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_thesis(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    text: str,
    *,
    created_by: uuid.UUID | None = None,
    llm_factory: LlmFactory | None = None,
) -> Thesis:
    """Insert the thesis and its extracted criteria. Commits."""
    thesis = Thesis(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        created_by=created_by,
        text=text.strip(),
        status=DRAFT,
    )
    session.add(thesis)
    await session.flush()
    draft = DiscoveryRun(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        thesis_id=thesis.id,
        created_by=created_by,
        status=DRAFT,
    )
    session.add(draft)
    # The extraction's ledger rows reference the draft run, so it must exist first.
    await session.commit()

    cost = CostContext(workspace_id=workspace_id, discovery_run_id=draft.id)
    make = llm_factory or factories.llm
    llm = make(recorder=DbCallRecorder(sessionmaker, cost), cache=DbCache(sessionmaker, cost))
    try:
        extraction = await extract_criteria(llm, thesis.text)
    except Exception:
        thesis.status = "failed"
        await session.commit()
        raise
    finally:
        close = getattr(llm, "aclose", None)
        if close is not None:
            await close()

    for position, c in enumerate(extraction.criteria):
        session.add(
            Criterion(
                thesis_id=thesis.id, position=position, edited=False, **crit.from_extraction(c)
            )
        )
    draft.criteria_snapshot = {
        "activity_query": extraction.activity_query,
        "prompt_version": extraction.prompt_version,
        "dropped": [d.model_dump() for d in extraction.dropped],
    }
    await session.commit()
    return thesis


MAX_CRITERIA = 20
MAX_VALUES = 25


def _criterion_values(item: Any) -> dict[str, Any]:
    kind = getattr(item.kind, "value", item.kind)
    dimension = getattr(item.dimension, "value", item.dimension)
    operator = getattr(item.operator, "value", item.operator)
    filt = item.crustdata_filter
    field_name = None
    if filt:
        field_name = filt.get("field")
        if field_name not in CRUSTDATA_FIELDS:
            raise InvalidCriteria(f"unknown Crustdata field {field_name!r}")
        if dimension not in CRUSTDATA_FIELDS[field_name]:
            raise InvalidCriteria(f"{field_name} cannot test a {dimension} criterion")
    if isinstance(item.value, list) and len(item.value) > MAX_VALUES:
        raise InvalidCriteria(f"'{item.label}': at most {MAX_VALUES} values")
    if operator == "between" and not (isinstance(item.value, list) and len(item.value) == 2):
        raise InvalidCriteria(f"'{item.label}': between needs [low, high]")
    return {
        "label": item.label.strip(),
        "kind": kind,
        "dimension": dimension,
        "operator": operator,
        "value": item.value,
        "crustdata_filter": crit.make_filter(field_name, operator, item.value),
        "weight": float(crit.policy_weight(kind)),
    }


def _same(row: Criterion, values: dict[str, Any]) -> bool:
    return all(getattr(row, k) == v for k, v in values.items())


async def replace_criteria(
    session: AsyncSession, workspace_id: uuid.UUID, thesis_id: uuid.UUID, items: Sequence[Any]
) -> Thesis:
    """Replace the thesis's criteria with `items`. Commits.

    Items with a known `id` update that row (marked `edited` if anything changed);
    items without one are added as `edited`; rows not listed are deleted.
    """
    if len(items) > MAX_CRITERIA:
        raise InvalidCriteria(f"at most {MAX_CRITERIA} criteria")
    thesis = await repo.get_thesis(session, workspace_id, thesis_id)
    dr = await latest_discovery_run(session, thesis.id)
    if dr is not None:
        run = await run_for(session, dr.id)
        if run is not None and run.state in (RunState.PENDING, RunState.RUNNING):
            raise SearchInProgress("a search is running on these criteria")
    current = {str(c.id): c for c in thesis.criteria}
    keep: set[str] = set()
    for position, item in enumerate(items):
        values = _criterion_values(item)
        row = current.get(item.id or "")
        if row is not None and item.id not in keep:
            changed = not _same(row, values)
            for k, v in values.items():
                setattr(row, k, v)
            row.position = position
            row.edited = row.edited or changed
            keep.add(item.id)
        else:
            session.add(Criterion(thesis_id=thesis.id, position=position, edited=True, **values))
    for cid, row in current.items():
        if cid not in keep:
            await session.delete(row)
    await session.commit()
    session.expire(thesis)
    return await repo.get_thesis(session, workspace_id, thesis_id)


async def start_search(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    thesis_id: uuid.UUID,
    *,
    created_by: uuid.UUID | None = None,
) -> Run:
    """Freeze the criteria and enqueue a discover run. Commits."""
    thesis = await repo.get_thesis(session, workspace_id, thesis_id)
    if not thesis.criteria:
        raise InvalidCriteria("the thesis has no criteria to search with")
    latest = await latest_discovery_run(session, thesis.id)
    previous_snapshot = (latest.criteria_snapshot if latest else None) or {}
    activity = (
        previous_snapshot.get("activity_query") if isinstance(previous_snapshot, dict) else None
    )
    if latest is not None:
        existing = await run_for(session, latest.id)
        if existing is not None and existing.state in (RunState.PENDING, RunState.RUNNING):
            raise SearchInProgress("a search for this thesis is already running")
    if latest is not None and latest.status == DRAFT and await run_for(session, latest.id) is None:
        dr = latest  # the draft that paid for the extraction
    else:
        dr = DiscoveryRun(
            id=uuid.uuid4(), workspace_id=workspace_id, thesis_id=thesis.id, created_by=created_by
        )
        session.add(dr)
    dr.status = "pending"
    dr.criteria_snapshot = {
        **(previous_snapshot if isinstance(previous_snapshot, dict) else {}),
        "activity_query": activity or thesis.text,
        "criteria": [crit.snapshot_row(c) for c in thesis.criteria],
    }
    thesis.status = "searching"
    await session.flush()
    run = await create_run(
        session,
        workspace_id=workspace_id,
        kind=RunKind.DISCOVER,
        steps=step_specs(dr.id),
        discovery_run_id=dr.id,
        budget_credits=get_job_settings().discover_credit_budget,
        created_by=created_by,
    )
    await session.commit()
    return run
