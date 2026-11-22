from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Run, Step
from app.jobs import StepRegistry
from app.jobs.worker import Worker


def make_worker(sm: async_sessionmaker[AsyncSession], reg: StepRegistry, **kw) -> Worker:
    kw.setdefault("lease_seconds", 30)
    kw.setdefault("poll_seconds", 0.05)
    kw.setdefault("retry_base_seconds", 0)
    kw.setdefault("retry_max_seconds", 0)
    return Worker(sm, registry=reg, **kw)


async def states(sm: async_sessionmaker[AsyncSession], run_id) -> dict[str, str]:
    async with sm() as s:
        rows = await s.execute(select(Step.key, Step.state).where(Step.run_id == run_id))
        return dict(rows.all())


async def step(sm: async_sessionmaker[AsyncSession], run_id, key: str) -> Step:
    async with sm() as s:
        return (
            await s.execute(select(Step).where(Step.run_id == run_id, Step.key == key))
        ).scalar_one()


async def run_state(sm: async_sessionmaker[AsyncSession], run_id) -> str:
    async with sm() as s:
        return (await s.get(Run, run_id)).state


class Calls(Counter):
    pass
