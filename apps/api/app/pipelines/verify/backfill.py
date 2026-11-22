"""Backfill: verify runs that finished without assessing the case get their tail.

Before verify runs ended with `evaluate` → `request_list` (see `tail.py`), a case could
finish verifying and never get an assessment version or a request list. For every case
whose latest verify run is finished, has no assessment version, and has no run still
working, this appends the closing tail to that run (which reopens it for the worker).

Idempotent: a case it fixed has a pending tail (skipped) and then an assessment
(skipped). A run whose evaluate already failed twice is left for a person to resume.
One instance at a time (a transaction-scoped advisory lock), so API instances starting
together do not enqueue twice.

    uv run python -m app.pipelines.verify.backfill        # management command
    (also run once in the background on API start; see `app.jobs.lifespan`)
"""

import asyncio
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.db.enums import RunKind, RunState
from app.db.models import AssessmentVersion, Run, Step
from app.pipelines.evaluate.service import HANDLER as EVALUATE_HANDLER
from app.pipelines.verify.tail import ensure_assessment_tail

log = logging.getLogger(__name__)

LOCK_KEY = 0x0DEA_1B0F  # pg advisory lock id for this job
MAX_FAILED_EVALUATES = 2
_ACTIVE = (RunState.PENDING, RunState.RUNNING)
_FINISHED = (RunState.DONE, RunState.FAILED)


async def backfill_assessment_tails(session: AsyncSession) -> list[uuid.UUID]:
    """Append the tail where it is missing. Returns the runs it reopened. Commits."""
    if not await session.scalar(select(func.pg_try_advisory_xact_lock(LOCK_KEY))):
        await session.rollback()
        return []
    other = aliased(Run)
    newest = (
        select(Run.case_id, func.max(Run.created_at).label("created_at"))
        .where(Run.kind == RunKind.VERIFY, Run.case_id.is_not(None))
        .group_by(Run.case_id)
        .subquery()
    )
    candidates = (
        await session.execute(
            select(Run)
            .join(
                newest,
                (newest.c.case_id == Run.case_id) & (newest.c.created_at == Run.created_at),
            )
            .where(
                Run.kind == RunKind.VERIFY,
                Run.state.in_(_FINISHED),
                ~select(AssessmentVersion.id)
                .where(AssessmentVersion.case_id == Run.case_id)
                .exists(),
                ~select(other.id)
                .where(other.case_id == Run.case_id, other.state.in_(_ACTIVE))
                .exists(),
            )
            .order_by(Run.created_at)
        )
    ).scalars()
    reopened: list[uuid.UUID] = []
    for run in list(candidates):
        failed = await session.scalar(
            select(func.count())
            .select_from(Step)
            .where(
                Step.run_id == run.id,
                Step.handler == EVALUATE_HANDLER,
                Step.state == "failed",
            )
        )
        if (failed or 0) >= MAX_FAILED_EVALUATES:
            log.warning("backfill: run %s already failed to assess twice; skipped", run.id)
            continue
        if await ensure_assessment_tail(session, run_id=run.id):
            reopened.append(run.id)
    await session.commit()
    if reopened:
        log.info("backfill: queued the assessment tail on %d verify runs", len(reopened))
    return reopened


async def run_backfill(sessionmaker: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    """The API-start entry point: never raises (a failed backfill must not stop the API)."""
    try:
        async with sessionmaker() as session:
            return await backfill_assessment_tails(session)
    except Exception:  # noqa: BLE001
        log.exception("backfill: could not queue assessment tails")
        return []


def main() -> None:
    from app.db.session import get_sessionmaker
    from app.jobs.registry import load_handlers

    logging.basicConfig(level=logging.INFO)
    load_handlers()
    reopened = asyncio.run(backfill_assessment_tails_cli(get_sessionmaker()))
    print(f"queued the assessment tail on {len(reopened)} verify run(s)")
    for run_id in reopened:
        print(f"  {run_id}")


async def backfill_assessment_tails_cli(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> list[uuid.UUID]:
    from app.db.session import dispose_engine

    try:
        async with sessionmaker() as session:
            return await backfill_assessment_tails(session)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    main()
