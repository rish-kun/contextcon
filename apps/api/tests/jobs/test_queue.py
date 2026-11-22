"""`GET /runs`: the workspace's job queue (`app.jobs.queue`)."""

import asyncio
from decimal import Decimal

import pytest

from app.api.schemas.runs import RunQueueStatus
from app.db.models import CostEntry
from app.jobs import StepContext, StepRegistry, StepSpec, create_run, queue
from tests.db.factories import discovery_run, tenant
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


async def test_queue_lists_active_and_recent_runs_with_step_credits(session, sm) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    reg = StepRegistry()
    gate = asyncio.Event()

    @reg.handler("paid")
    async def paid(ctx: StepContext) -> dict:
        async with ctx.sessionmaker() as s:
            s.add(
                CostEntry(
                    workspace_id=ctx.run.workspace_id,
                    case_id=ctx.run.case_id,
                    discovery_run_id=ctx.run.discovery_run_id,
                    run_id=ctx.run.id,
                    step_id=ctx.step_id,
                    provider="crustdata",
                    endpoint="/screener/companysearch",
                    credits=Decimal(ctx.input["credits"]),
                )
            )
            await s.commit()
        return {}

    @reg.handler("wait")
    async def wait(ctx: StepContext) -> dict:
        await gate.wait()
        return {}

    dr = await discovery_run(session, a)
    finished = await create_run(
        session,
        workspace_id=a.workspace.id,
        kind="discover",
        discovery_run_id=dr.id,
        steps=[StepSpec("search", "paid", input={"credits": "5"}, label="Search")],
    )
    await session.commit()
    await make_worker(sm, reg).drain()
    working = await create_run(
        session,
        workspace_id=a.workspace.id,
        kind="verify",
        case_id=a.case.id,
        steps=[
            StepSpec("identity", "paid", input={"credits": "4"}, label="Confirm identity"),
            StepSpec("profile", "paid", input={"credits": "3"}, depends_on=["identity"]),
            StepSpec("checks", "wait", depends_on=["profile"], label="Check the claims"),
            StepSpec("evaluate", "noop", depends_on=["checks"], uses_budget=False),
        ],
    )
    await session.commit()
    worker = asyncio.create_task(make_worker(sm, reg).drain())
    try:
        for _ in range(100):  # until the paid steps are done and `checks` is running
            async with sm() as s:
                active = await queue.list_run_queue(s, a.workspace.id)
            if active.items and active.items[0].steps_done == 2:
                break
            await asyncio.sleep(0.05)

        [item] = active.items
        assert active.active_count == 1
        assert item.id == str(working.id) and item.state == "running"
        assert item.owner is not None and item.owner.kind == "case"
        assert item.owner.id == str(a.case.id) and item.owner.label == "a target (fixture)"
        assert (item.steps_done, item.steps_total) == (2, 4)
        assert item.current_step == "Check the claims"
        assert item.credits.settled == 7  # 4 + 3, what the step rows show
        assert item.started_at is not None and item.budget_credits > 0

        other = await create_run(  # queued behind the busy worker
            session,
            workspace_id=b.workspace.id,
            kind="verify",
            case_id=b.case.id,
            steps=[StepSpec("identity", "wait")],
        )
        await session.commit()
        async with sm() as s:
            recent = await queue.list_run_queue(s, a.workspace.id, status=RunQueueStatus.recent)
            limited = await queue.list_run_queue(
                s, a.workspace.id, status=RunQueueStatus.recent, limit=1
            )
            theirs = await queue.list_run_queue(s, b.workspace.id)
        ids = [i.id for i in recent.items]
        assert set(ids) == {str(working.id), str(finished.id)}  # never another workspace's
        done = next(i for i in recent.items if i.id == str(finished.id))
        assert done.state == "done" and done.current_step is None
        assert done.owner is not None and done.owner.kind == "thesis"
        assert done.owner.label == "fixture thesis" and done.credits.settled == 5
        assert len(limited.items) == 1 and limited.active_count == 1
        assert [i.id for i in theirs.items] == [str(other.id)]
    finally:
        gate.set()
        await worker
