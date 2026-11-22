"""Policy refresh: cases assessed under an older policy are re-assessed under the current one.

For every case whose latest assessment version was made under a different
`POLICY_VERSION`, and that has no run still working, this queues an evaluate run
(evaluate → decision flip) whose trigger names the policy change
(`policy.POLICY_CHANGES`), so the new version's diff carries the reason, for example
"policy fix: country code normalisation".

Idempotent: a refreshed case has a pending run (skipped) and then a version under the
current policy (skipped). One instance at a time (transaction-scoped advisory lock).

    uv run python -m app.pipelines.evaluate.refresh       # management command
    (also run once in the background on API start; see `app.jobs.lifespan`)
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import RunState
from app.db.models import AssessmentVersion, Case, Run
from app.pipelines.evaluate.cases import queue_evaluation
from app.rules import policy

log = logging.getLogger(__name__)

LOCK_KEY = 0x0DEA_1B10
_ACTIVE = (RunState.PENDING, RunState.RUNNING)
TRIGGER_MAX = 64


def refresh_reason(from_version: str | None) -> str:
    """The changes since `from_version`, newest last, within the trigger's 64 chars."""
    changes = [
        reason
        for version, reason in sorted(policy.POLICY_CHANGES.items())
        if from_version is None or version > from_version
    ]
    text = "; ".join(dict.fromkeys(changes)) or f"policy update {policy.POLICY_VERSION}"
    return text[:TRIGGER_MAX]


async def refresh_outdated_assessments(session: AsyncSession) -> list[uuid.UUID]:
    """Queue a re-assessment for each outdated case. Returns the case ids. Commits."""
    if not await session.scalar(select(func.pg_try_advisory_xact_lock(LOCK_KEY))):
        await session.rollback()
        return []
    newest = (
        select(AssessmentVersion.case_id, func.max(AssessmentVersion.version).label("version"))
        .group_by(AssessmentVersion.case_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Case, AssessmentVersion.policy_version)
            .join(AssessmentVersion, AssessmentVersion.case_id == Case.id)
            .join(
                newest,
                (newest.c.case_id == AssessmentVersion.case_id)
                & (newest.c.version == AssessmentVersion.version),
            )
            .where(
                AssessmentVersion.policy_version != policy.POLICY_VERSION,
                ~select(Run.id).where(Run.case_id == Case.id, Run.state.in_(_ACTIVE)).exists(),
            )
            .order_by(Case.created_at)
        )
    ).all()
    queued: list[uuid.UUID] = []
    for case, version in rows:
        await queue_evaluation(session, case, trigger=refresh_reason(version))
        queued.append(case.id)
    await session.commit()
    if queued:
        log.info("policy refresh: queued re-assessment of %d case(s)", len(queued))
    return queued


async def run_refresh(sessionmaker: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    """The API-start entry point: never raises."""
    try:
        async with sessionmaker() as session:
            return await refresh_outdated_assessments(session)
    except Exception:  # noqa: BLE001
        log.exception("policy refresh: could not queue re-assessments")
        return []


def main() -> None:
    from app.db.session import dispose_engine, get_sessionmaker
    from app.jobs.registry import load_handlers

    logging.basicConfig(level=logging.INFO)
    load_handlers()

    async def _run() -> list[uuid.UUID]:
        try:
            return await run_refresh(get_sessionmaker())
        finally:
            await dispose_engine()

    queued = asyncio.run(_run())
    print(f"queued re-assessment of {len(queued)} case(s)")


if __name__ == "__main__":
    main()
