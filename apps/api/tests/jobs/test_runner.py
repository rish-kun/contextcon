import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import ledger
from app.db.models import Step
from app.jobs import BUDGET_REACHED, BudgetExceeded, StepContext, StepRegistry, StepSpec, create_run
from app.jobs.engine import (
    LeaseLost,
    append_steps,
    claim_step,
    mark_done,
    mark_retry_or_failed,
    reclaim_expired_leases,
    renew_lease,
)
from tests.db.factories import FakeCrustdataApi, tenant
from tests.jobs.helpers import Calls, make_worker, run_state, states, step

pytestmark = pytest.mark.asyncio


async def _run(session: AsyncSession, t, steps, **kw):
    run = await create_run(
        session, workspace_id=t.workspace.id, kind="verify", case_id=t.case.id, steps=steps, **kw
    )
    await session.commit()
    return run


async def test_steps_run_in_dependency_order(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    order: list[str] = []

    @reg.handler("record")
    async def record(ctx: StepContext) -> dict:
        order.append(ctx.key)
        return {"seen": sorted(ctx.dependencies)}

    run = await _run(
        session,
        t,
        [
            StepSpec("evaluate", "record", depends_on=["claims", "profile"]),
            StepSpec("claims", "record", depends_on=["identity"]),
            StepSpec("profile", "record", depends_on=["identity"]),
            StepSpec("identity", "record"),
        ],
    )
    assert await make_worker(sm, reg).drain() == 4
    assert order[0] == "identity" and order[-1] == "evaluate"
    assert (await step(sm, run.id, "evaluate")).output == {"seen": ["claims", "profile"]}
    assert await run_state(sm, run.id) == "done"


async def test_concurrent_workers_never_double_claim(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    calls = Calls()

    @reg.handler("work")
    async def work(ctx: StepContext) -> dict:
        calls[ctx.key] += 1
        await asyncio.sleep(0.01)
        return {}

    run = await _run(session, t, [StepSpec(f"s{i}", "work") for i in range(40)])
    workers = [make_worker(sm, reg, worker_id=f"w{i}") for i in range(8)]
    await asyncio.gather(*(w.drain() for w in workers))
    assert len(calls) == 40 and set(calls.values()) == {1}
    async with sm() as s:
        attempts = await s.execute(select(Step.attempts).where(Step.run_id == run.id))
        assert set(attempts.scalars()) == {1}
    assert await run_state(sm, run.id) == "done"


async def test_skip_locked_claims_distinct_steps(session, sm) -> None:
    t = await tenant(session)
    run = await _run(session, t, [StepSpec("a", "noop"), StepSpec("b", "noop")])
    async with sm() as s1, sm() as s2, sm() as s3:
        got = await asyncio.gather(
            claim_step(s1, "w1", 30), claim_step(s2, "w2", 30), claim_step(s3, "w3", 30)
        )
    claimed = [g for g in got if g is not None]
    assert len(claimed) == 2 and len(set(claimed)) == 2
    assert set((await states(sm, run.id)).values()) == {"running"}


async def _crash_mid_step(sm, run_id, key: str, *, owner: str = "dead-worker") -> None:
    """Leave a step `running` with an expired lease, as a killed worker would."""
    async with sm() as s:
        await s.execute(
            update(Step)
            .where(Step.run_id == run_id, Step.key == key)
            .values(
                state="running",
                attempts=Step.attempts + 1,
                lease_owner=owner,
                lease_until=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1),
            )
        )
        await s.commit()


async def test_expired_lease_is_reclaimed_and_retried(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    seen_attempts: list[int] = []

    @reg.handler("work")
    async def work(ctx: StepContext) -> dict:
        seen_attempts.append(ctx.attempt)
        return {}

    run = await _run(session, t, [StepSpec("a", "work")])
    await _crash_mid_step(sm, run.id, "a")
    assert await make_worker(sm, reg).drain() == 1
    assert seen_attempts == [2]
    assert (await states(sm, run.id)) == {"a": "done"}


async def test_reclaim_happens_while_the_worker_keeps_running(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    done = asyncio.Event()

    @reg.handler("work")
    async def work(ctx: StepContext) -> dict:
        done.set()
        return {}

    worker = make_worker(sm, reg)
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop, purge=False))
    try:
        await asyncio.sleep(0.2)  # worker idle, well past boot
        run = await _run(session, t, [StepSpec("a", "work")])
        await _crash_mid_step(sm, run.id, "a")
        await asyncio.wait_for(done.wait(), timeout=5)
    finally:
        stop.set()
        await loop
    assert (await states(sm, run.id)) == {"a": "done"}


async def test_expired_lease_out_of_attempts_fails_and_propagates(session, sm) -> None:
    t = await tenant(session)
    run = await _run(
        session, t, [StepSpec("a", "noop", max_attempts=1), StepSpec("b", "noop", depends_on=["a"])]
    )
    await _crash_mid_step(sm, run.id, "a")
    await make_worker(sm, StepRegistry()).reclaim()
    assert await states(sm, run.id) == {"a": "failed", "b": "failed"}
    assert "dependency failed: a" in (await step(sm, run.id, "b")).error
    assert await run_state(sm, run.id) == "failed"


async def test_worker_that_lost_its_lease_cannot_complete(session, sm) -> None:
    t = await tenant(session)
    run = await _run(session, t, [StepSpec("a", "noop")])
    async with sm() as s:
        old = await claim_step(s, "slow-worker", 30)
    await _crash_mid_step(sm, run.id, "a", owner="slow-worker")  # lease expires
    async with sm() as s:
        await reclaim_expired_leases(s)
    async with sm() as s:
        new = await claim_step(s, "new-worker", 30)
    assert new.id == old.id and new.token != old.token
    async with sm() as s:
        with pytest.raises(LeaseLost):
            await mark_done(s, old.id, old.token, {"stale": True})
    async with sm() as s:
        assert not await renew_lease(s, old.id, old.token, 30)
    async with sm() as s:
        assert (
            await mark_retry_or_failed(s, old.id, old.token, "x", retry_base=0, retry_max=0) is None
        )
    assert (await step(sm, run.id, "a")).lease_owner == "new-worker"


async def test_expired_lease_cannot_complete_even_before_reclaim(session, sm) -> None:
    """Same token, but the lease ran out: no renewal, completion or failure."""
    t = await tenant(session)
    run = await _run(session, t, [StepSpec("a", "noop")])
    async with sm() as s:
        claim = await claim_step(s, "w", 30)
    async with sm() as s:
        await s.execute(
            update(Step)
            .where(Step.id == claim.id)
            .values(lease_until=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1))
        )
        await s.commit()
    async with sm() as s:
        assert not await renew_lease(s, claim.id, claim.token, 30)
    async with sm() as s:
        with pytest.raises(LeaseLost):
            await mark_done(s, claim.id, claim.token, {})
    async with sm() as s:
        assert (
            await mark_retry_or_failed(s, claim.id, claim.token, "x", retry_base=0, retry_max=0)
            is None
        )
    assert (await step(sm, run.id, "a")).state == "running"  # left for reclaim


async def test_expired_worker_cannot_start_a_new_paid_call(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    api = FakeCrustdataApi()
    raised: list[type] = []

    @reg.handler("identify")
    async def identify(ctx: StepContext) -> dict:
        # Simulate the lease running out mid-handler (e.g. a long stall).
        async with ctx.sessionmaker() as s:
            await s.execute(
                update(Step)
                .where(Step.id == ctx.step_id)
                .values(lease_until=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1))
            )
            await s.commit()
        client = api.client(recorder=ctx.recorder, cache=ctx.cache)
        try:
            await client.identify_company(domains=["example-logistics.test"])
        except LeaseLost:
            raised.append(LeaseLost)
            raise
        return {}

    run = await _run(session, t, [StepSpec("identity", "identify")])
    assert await make_worker(sm, reg).run_once()
    assert raised == [LeaseLost]
    assert api.http_calls == 0
    async with sm() as db:
        totals = await ledger.case_totals(db, t.workspace.id, t.case.id)
    assert totals.calls == 0 and totals.unknown_calls == 0
    # The step was not completed by the expired worker; it is left for reclaim.
    assert (await step(sm, run.id, "identity")).state == "running"


async def test_heartbeat_keeps_long_steps_leased(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("slow")
    async def slow(ctx: StepContext) -> dict:
        await asyncio.sleep(1.5)
        return {}

    run = await _run(session, t, [StepSpec("a", "slow")])
    worker = make_worker(sm, reg, lease_seconds=0.6, heartbeat_seconds=0.15)
    rival = make_worker(sm, reg, worker_id="rival")
    task = asyncio.create_task(worker.drain())
    await asyncio.sleep(1.0)  # longer than one lease
    assert await rival.drain() == 0  # nothing to reclaim: the lease was renewed
    await task
    s = await step(sm, run.id, "a")
    assert (s.state, s.attempts) == ("done", 1)


async def test_errors_retry_then_fail(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    calls = Calls()

    @reg.handler("flaky")
    async def flaky(ctx: StepContext) -> dict:
        calls[ctx.key] += 1
        if ctx.key == "always" or ctx.attempt < 2:
            raise RuntimeError("upstream 503")
        return {"ok": True}

    run = await _run(
        session, t, [StepSpec("once", "flaky"), StepSpec("always", "flaky", max_attempts=3)]
    )
    await make_worker(sm, reg).drain()
    assert calls == {"once": 2, "always": 3}
    st = await states(sm, run.id)
    assert st == {"once": "done", "always": "failed"}
    assert (await step(sm, run.id, "always")).error == "RuntimeError"


async def test_backoff_delays_the_retry(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("boom")
    async def boom(ctx: StepContext) -> dict:
        raise RuntimeError("x")

    run = await _run(session, t, [StepSpec("a", "boom")])
    worker = make_worker(sm, reg, retry_base_seconds=30, retry_max_seconds=60)
    assert await worker.drain() == 1  # retry is scheduled 30 s out, not run now
    s = await step(sm, run.id, "a")
    assert s.state == "pending" and s.next_attempt_at is not None


async def test_unknown_handler_fails_without_retry(session, sm) -> None:
    t = await tenant(session)
    run = await _run(session, t, [StepSpec("a", "does.not.exist")])
    await make_worker(sm, StepRegistry()).drain()
    s = await step(sm, run.id, "a")
    assert (s.state, s.attempts) == ("failed", 1)


async def test_budget_exhaustion_skips_remaining_steps(session, sm) -> None:
    t = await tenant(session, credit_budget=5)
    reg = StepRegistry()
    ran: list[str] = []

    @reg.handler("spend")
    async def spend(ctx: StepContext) -> dict:
        ran.append(ctx.key)
        async with ctx.sessionmaker() as s:
            await ledger.record_cost(s, ctx.cost, provider="crustdata", endpoint="/e", credits=3)
            await s.commit()
        return {}

    @reg.handler("evaluate")
    async def evaluate(ctx: StepContext) -> dict:
        ran.append(ctx.key)
        return {k: v["state"] for k, v in ctx.dependencies.items()}

    checks = [f"check{i}" for i in range(4)]
    run = await _run(
        session,
        t,
        [StepSpec(k, "spend") for k in checks]
        + [
            StepSpec(
                "evaluate",
                "evaluate",
                depends_on=checks,
                uses_budget=False,
                tolerate_failed_deps=True,
            )
        ],
    )
    assert run.budget_credits == Decimal(5)
    await make_worker(sm, reg).drain()
    st = await states(sm, run.id)
    assert ran[:2] == ["check0", "check1"]  # 3 + 3 credits > 5: the rest are skipped
    assert [st[k] for k in checks] == ["done", "done", "skipped_budget", "skipped_budget"]
    assert (await step(sm, run.id, "check2")).skip_reason == BUDGET_REACHED
    assert st["evaluate"] == "done"  # free step still runs, sees what was skipped
    assert (await step(sm, run.id, "evaluate")).output["check3"] == "skipped_budget"
    assert await run_state(sm, run.id) == "done"


async def test_budget_comes_from_settings_and_is_per_case(session, sm, monkeypatch) -> None:
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "case_credit_budget", 4)
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("spend")
    async def spend(ctx: StepContext) -> dict:
        await ctx.require_budget(3)
        async with ctx.sessionmaker() as s:
            await ledger.record_cost(s, ctx.cost, provider="crustdata", endpoint="/e", credits=3)
            await s.commit()
        return {}

    first = await _run(session, t, [StepSpec("a", "spend")])
    await make_worker(sm, reg).drain()
    second = await _run(
        session, t, [StepSpec("b", "spend"), StepSpec("c", "noop", depends_on=["b"])]
    )
    assert first.budget_credits == second.budget_credits == Decimal(4)
    await make_worker(sm, reg).drain()
    # 1 credit left for the case: the 3-credit estimate does not fit.
    assert await states(sm, second.id) == {"b": "skipped_budget", "c": "skipped_budget"}


async def test_handler_budget_exceeded_marks_only_that_step(session, sm) -> None:
    t = await tenant(session, credit_budget=10)
    reg = StepRegistry()

    @reg.handler("big")
    async def big(ctx: StepContext) -> dict:
        raise BudgetExceeded()

    run = await _run(session, t, [StepSpec("big", "big"), StepSpec("small", "noop")])
    await make_worker(sm, reg).drain()
    assert await states(sm, run.id) == {"big": "skipped_budget", "small": "done"}


async def test_idempotent_resume_does_not_repeat_a_paid_call(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()
    api = FakeCrustdataApi(credits="0.2")
    crash = {"armed": True}

    @reg.handler("identify")
    async def identify(ctx: StepContext) -> dict:
        client = api.client(recorder=ctx.recorder, cache=ctx.cache)
        results, record = await client.identify_company(domains=["example-logistics.test"])
        if crash["armed"]:
            crash["armed"] = False
            raise ConnectionResetError("worker died after the paid call")
        ctx.result = f"{len(results)} match"
        return {"from_cache": record.from_cache}

    run = await _run(session, t, [StepSpec("identity", "identify", label="Confirm identity")])
    await make_worker(sm, reg).drain()
    s = await step(sm, run.id, "identity")
    assert (s.state, s.attempts, s.output) == ("done", 2, {"from_cache": True})
    assert s.result == "1 match" and s.label == "Confirm identity"
    assert api.http_calls == 1
    async with sm() as db:
        totals = await ledger.case_totals(db, t.workspace.id, t.case.id)
    assert (totals.calls, totals.credits) == (1, Decimal("0.2"))
    # A done step is never run again.
    assert await make_worker(sm, reg).drain() == 0


async def test_handler_writes_roll_back_on_failure(session, sm) -> None:
    from app.db.models import Claim

    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("write_then_fail")
    async def write_then_fail(ctx: StepContext) -> dict:
        ctx.session.add(
            Claim(
                case_id=ctx.run.case_id,
                original_text=f"try {ctx.attempt}",
                origin="typed",
                category="other",
            )
        )
        await ctx.session.flush()
        if ctx.attempt == 1:
            raise RuntimeError("fail after writing")
        return {}

    await _run(session, t, [StepSpec("a", "write_then_fail")])
    await make_worker(sm, reg).drain()
    async with sm() as db:
        from sqlalchemy import select

        texts = (await db.execute(select(Claim.original_text))).scalars().all()
    assert texts == ["try 2"]


async def test_fan_out_with_append_steps(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("intake")
    async def intake(ctx: StepContext) -> dict:
        specs = [StepSpec(f"check:{i}", "noop") for i in range(3)]
        specs.append(StepSpec("evaluate", "noop", depends_on=[s.key for s in specs]))
        await ctx.append_steps(specs)
        await ctx.append_steps(specs)  # idempotent
        return {"claims": 3}

    run = await _run(session, t, [StepSpec("intake", "intake")])
    await make_worker(sm, reg).drain()
    st = await states(sm, run.id)
    assert len(st) == 5 and set(st.values()) == {"done"}


async def test_resume_requeues_failed_and_skipped_steps(session, sm) -> None:
    from app.jobs.engine import resume_run

    t = await tenant(session)
    reg = StepRegistry()
    fail = {"on": True}

    @reg.handler("maybe")
    async def maybe(ctx: StepContext) -> dict:
        if fail["on"]:
            raise RuntimeError("down")
        return {}

    run = await _run(
        session,
        t,
        [StepSpec("a", "maybe", max_attempts=1), StepSpec("b", "noop", depends_on=["a"])],
    )
    await make_worker(sm, reg).drain()
    assert await run_state(sm, run.id) == "failed"
    fail["on"] = False
    async with sm() as db:
        assert await resume_run(db, run.id) == 2
        await db.commit()
    await make_worker(sm, reg).drain()
    assert await states(sm, run.id) == {"a": "done", "b": "done"}
    assert await run_state(sm, run.id) == "done"


async def test_dependencies_must_exist(session) -> None:
    t = await tenant(session)
    with pytest.raises(ValueError):
        await _run(session, t, [StepSpec("a", "noop", depends_on=["nope"])])


async def _wait_for_lock_wait(sm, task: asyncio.Task, timeout: float = 10.0) -> bool:
    """True once some backend waits for a row lock; False if `task` finished first."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if task.done():
            return False
        async with sm() as s:
            waiting = await s.scalar(
                text(
                    "SELECT count(*) FROM pg_locks WHERE NOT granted"
                    " AND locktype IN ('transactionid', 'tuple')"
                )
            )
        if waiting:
            return True
        await asyncio.sleep(0.05)
    raise AssertionError("neither waited nor finished")


async def test_run_is_not_closed_while_steps_are_being_appended(session, sm) -> None:
    """A worker finishing the last step while a handler appends steps must wait for the
    append to commit, see the new step pending and leave the run open."""
    t = await tenant(session)
    run = await _run(session, t, [StepSpec("a", "noop")])
    async with sm() as s:
        claim = await claim_step(s, "w1", 30)
    assert claim is not None

    appender = sm()
    await append_steps(appender, run.id, [StepSpec("b", "noop", depends_on=["a"])])

    async def finish_a() -> None:
        async with sm() as s:
            await mark_done(s, claim.id, claim.token, {"ok": True})
            await s.commit()

    finishing = asyncio.create_task(finish_a())
    try:
        assert await _wait_for_lock_wait(sm, finishing), "closing the run did not wait"
        await appender.commit()
        await finishing
    finally:
        await appender.close()
    assert await states(sm, run.id) == {"a": "done", "b": "pending"}
    assert await run_state(sm, run.id) == "running"
    async with sm() as s:
        nxt = await claim_step(s, "w2", 30)
    assert nxt is not None and (await step(sm, run.id, "b")).id == nxt.id


async def test_concurrent_appends_and_completions_never_strand_a_step(session, sm) -> None:
    """Many appends racing many completions: every run ends with no pending step left
    behind a closed run."""
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("grow")
    async def grow(ctx: StepContext) -> dict:
        n = int(ctx.input.get("n", 0))
        if n < 3:
            await ctx.append_steps(
                [StepSpec(f"{ctx.key}.{i}", "grow", input={"n": n + 1}) for i in range(2)]
            )
        return {}

    run = await _run(session, t, [StepSpec("root", "grow")])
    workers = [make_worker(sm, reg) for _ in range(4)]
    await asyncio.gather(*(w.drain() for w in workers))
    final = await states(sm, run.id)
    assert len(final) == 15 and set(final.values()) == {"done"}
    assert await run_state(sm, run.id) == "done"
