"""The step worker. Runs inside the API (FastAPI lifespan) or standalone:

uv run python -m app.jobs.worker [--concurrency N] [--drain]
"""

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import socket
import uuid
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.adapters import DbCache, DbCallRecorder
from app.db.enums import StepState
from app.db.models import Run, Step
from app.jobs.config import JobSettings, get_job_settings
from app.jobs.engine import (
    BudgetExceeded,
    LeaseLost,
    RunInfo,
    StepClaim,
    StepContext,
    budget_remaining,
    claim_step,
    cost_context,
    dependency_outputs,
    mark_done,
    mark_retry_or_failed,
    mark_skipped_budget,
    public_error,
    reclaim_expired_leases,
    renew_lease,
    skip_remaining_budgeted,
)
from app.jobs.purge import ObjectDeleter, default_object_deleter, purge_expired
from app.jobs.registry import StepRegistry
from app.jobs.registry import registry as default_registry

log = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        registry: StepRegistry | None = None,
        settings: JobSettings | None = None,
        worker_id: str | None = None,
        lease_seconds: float | None = None,
        heartbeat_seconds: float | None = None,
        poll_seconds: float | None = None,
        retry_base_seconds: float | None = None,
        retry_max_seconds: float | None = None,
        concurrency: int | None = None,
        object_deleter: ObjectDeleter | None = None,
        purge_interval_seconds: float | None = None,
        shutdown_grace_seconds: float = 5.0,
    ) -> None:
        cfg = settings or get_job_settings()
        self.sessionmaker = sessionmaker
        self.registry = registry or default_registry
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.lease_seconds = lease_seconds or cfg.worker_lease_seconds
        self.heartbeat_seconds = heartbeat_seconds or self.lease_seconds / 3
        self.poll_seconds = poll_seconds or cfg.worker_poll_seconds
        self.retry_base = (
            cfg.worker_retry_base_seconds if retry_base_seconds is None else retry_base_seconds
        )
        self.retry_max = (
            cfg.worker_retry_max_seconds if retry_max_seconds is None else retry_max_seconds
        )
        self.concurrency = concurrency or cfg.worker_concurrency
        self.object_deleter = object_deleter
        self.purge_interval = purge_interval_seconds or cfg.purge_interval_seconds
        self.shutdown_grace = shutdown_grace_seconds

    # -- one unit of work ------------------------------------------------------

    async def reclaim(self) -> list[uuid.UUID]:
        async with self.sessionmaker() as session:
            return await reclaim_expired_leases(session)

    async def run_once(self) -> bool:
        """Reclaim expired leases, then claim and execute one step. True if it ran one."""
        await self.reclaim()
        async with self.sessionmaker() as session:
            claim = await claim_step(session, self.worker_id, self.lease_seconds)
        if claim is None:
            return False
        await self.execute(claim)
        return True

    async def drain(self, max_steps: int = 10_000) -> int:
        """Run steps until none is ready. For tests and `--drain`."""
        count = 0
        while count < max_steps and await self.run_once():
            count += 1
        return count

    async def execute(self, claim: StepClaim) -> None:
        step_id, token = claim.id, claim.token
        async with self.sessionmaker() as session:
            step = await session.get(Step, step_id)
            assert step is not None
            run_row = await session.get(Run, step.run_id)
            assert run_row is not None
            run = RunInfo.of(run_row)
            handler_name, key, attempt = step.handler, step.key, step.attempts
            step_input, depends_on = dict(step.input or {}), list(step.depends_on or [])
            uses_budget = step.uses_budget
            handler = self.registry.get(handler_name)
            if handler is None:
                await session.rollback()
                await self._fail(claim, f"no handler registered for {handler_name!r}", False)
                return

            if uses_budget:
                remaining = await budget_remaining(session, run)
                if remaining is not None and remaining <= 0:
                    await session.rollback()
                    await self._skip_for_budget(claim, run.id, remaining)
                    return

            cost = cost_context(run, step_id)
            ctx = StepContext(
                run=run,
                step_id=step_id,
                key=key,
                input=step_input,
                attempt=attempt,
                session=session,
                sessionmaker=self.sessionmaker,
                dependencies=await dependency_outputs(session, run.id, depends_on),
                cost=cost,
                recorder=DbCallRecorder(self.sessionmaker, cost, lease_token=token)
                if cost
                else None,
                # Workspace scope, for public lookups. LLM clients take the case-scoped,
                # expiring view (`ctx.cache.confidential()`) unless told the prompt is
                # public.
                cache=DbCache(self.sessionmaker, cost) if cost else None,
                lease_token=token,
            )

            task = asyncio.create_task(handler(ctx))
            lease_lost = asyncio.Event()
            heartbeat = asyncio.create_task(self._heartbeat(claim, task, lease_lost))
            try:
                output = await task
                if ctx.logs:
                    output = {**(output or {}), "_log": ctx.logs}
                await mark_done(session, step_id, token, output, ctx.result)
                await session.commit()
            except BudgetExceeded as exc:
                await session.rollback()
                async with self.sessionmaker() as s:
                    remaining = await budget_remaining(s, run)
                await self._skip_for_budget(claim, run.id, remaining, exc.reason)
            except LeaseLost:
                # From mark_done, or from the recorder refusing a new paid dispatch.
                await session.rollback()
                log.warning("step %s: lease lost before completion; result discarded", step_id)
            except asyncio.CancelledError:
                await session.rollback()
                if lease_lost.is_set():
                    log.warning("step %s: lease lost mid-run; handler cancelled", step_id)
                    return
                await asyncio.shield(self._release(claim))
                raise
            except Exception as exc:  # noqa: BLE001 - any handler error is retried
                await session.rollback()
                log.exception("step %s (%s) failed", step_id, handler_name)
                await self._fail(claim, public_error(exc), True)
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat

    async def _heartbeat(
        self, claim: StepClaim, task: asyncio.Task, lease_lost: asyncio.Event
    ) -> None:
        step_id = claim.id
        while not task.done():
            await asyncio.sleep(self.heartbeat_seconds)
            if task.done():
                return
            try:
                async with self.sessionmaker() as session:
                    held = await renew_lease(session, step_id, claim.token, self.lease_seconds)
            except Exception:  # noqa: BLE001 - a transient DB error must not kill the step
                log.exception("step %s: lease renewal failed", step_id)
                continue
            if not held:
                lease_lost.set()
                task.cancel()
                return

    async def _fail(self, claim: StepClaim, error: str, retryable: bool) -> None:
        async with self.sessionmaker() as session:
            await mark_retry_or_failed(
                session,
                claim.id,
                claim.token,
                error,
                retry_base=self.retry_base,
                retry_max=self.retry_max,
                retryable=retryable,
            )

    async def _skip_for_budget(
        self,
        claim: StepClaim,
        run_id: uuid.UUID,
        remaining: Decimal | None,
        reason: str | None = None,
    ) -> None:
        async with self.sessionmaker() as session:
            if reason:
                await mark_skipped_budget(session, claim.id, claim.token, reason)
            else:
                await mark_skipped_budget(session, claim.id, claim.token)
        if remaining is not None and remaining <= 0:
            async with self.sessionmaker() as session:
                await skip_remaining_budgeted(session, run_id)
                await session.commit()

    async def _release(self, claim: StepClaim) -> None:
        """Shutdown mid-step: hand the step straight back instead of waiting for the
        lease to expire."""
        step_id = claim.id
        try:
            async with self.sessionmaker() as session:
                await session.execute(
                    update(Step)
                    .where(
                        Step.id == step_id,
                        Step.lease_token == claim.token,
                        Step.state == StepState.RUNNING,
                    )
                    .values(
                        state=StepState.PENDING,
                        lease_owner=None,
                        lease_token=None,
                        lease_until=None,
                        # An interrupted attempt is not a failed one.
                        attempts=func.greatest(Step.attempts - 1, 0),
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            log.exception("step %s: could not release on shutdown", step_id)

    # -- loops -------------------------------------------------------------------

    async def _loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                did_work = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the worker alive through DB blips
                log.exception("worker loop error")
                did_work = False
            if not did_work:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)

    async def _purge_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                report = await purge_expired(self.sessionmaker, self.object_deleter)
                if report.total:
                    log.info("purge: %s", report)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("purge failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.purge_interval)

    async def run(self, stop: asyncio.Event, *, purge: bool = True) -> None:
        log.info("worker %s starting (%d loops)", self.worker_id, self.concurrency)
        tasks = [asyncio.create_task(self._loop(stop)) for _ in range(self.concurrency)]
        if purge:
            tasks.append(asyncio.create_task(self._purge_loop(stop)))
        try:
            await stop.wait()
            # Let in-flight steps finish; loops exit once their current step is done.
            await asyncio.wait(tasks, timeout=self.shutdown_grace)
        finally:
            for t in tasks:
                t.cancel()  # still running after the grace period: release and stop
            await asyncio.gather(*tasks, return_exceptions=True)
            log.info("worker %s stopped", self.worker_id)


async def _main(args: argparse.Namespace) -> None:
    from app.db.session import dispose_engine, get_sessionmaker
    from app.jobs.registry import load_handlers

    load_handlers()
    worker = Worker(
        get_sessionmaker(), concurrency=args.concurrency, object_deleter=default_object_deleter()
    )
    try:
        if args.drain:
            ran = await worker.drain()
            log.info("drained %d steps", ran)
            return
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        await worker.run(stop)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="DealProof step worker")
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--drain", action="store_true", help="run ready steps, then exit")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
