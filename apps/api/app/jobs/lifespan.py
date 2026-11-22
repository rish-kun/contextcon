"""FastAPI lifespan that runs the step worker in-process (`WORKER_IN_PROCESS=true`)."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.db.session import database_configured, dispose_engine, get_sessionmaker
from app.jobs.config import get_job_settings
from app.jobs.purge import ObjectDeleter, default_object_deleter

log = logging.getLogger(__name__)

SHUTDOWN_GRACE_SECONDS = 10.0


@contextlib.asynccontextmanager
async def jobs_lifespan(
    app: FastAPI, *, object_deleter: ObjectDeleter | None = None
) -> AsyncIterator[None]:
    cfg = get_job_settings()
    stop = asyncio.Event()
    task: asyncio.Task | None = None
    if cfg.worker_in_process and database_configured():
        from app.jobs.registry import load_handlers
        from app.jobs.worker import Worker

        load_handlers()
        deleter = (
            object_deleter or getattr(app.state, "object_deleter", None) or default_object_deleter()
        )
        worker = Worker(get_sessionmaker(), settings=cfg, object_deleter=deleter)
        task = asyncio.create_task(worker.run(stop), name="dealproof-worker")
        app.state.worker = worker
    elif cfg.worker_in_process:
        log.warning("DATABASE_URL is not set; in-process worker not started")
    backfill: asyncio.Task | None = None
    if database_configured():
        # Verify runs that finished before they ended in an assessment get their tail
        # (idempotent, one instance at a time). In the background: start-up never waits.
        from app.pipelines.verify.backfill import run_backfill

        backfill = asyncio.create_task(run_backfill(get_sessionmaker()), name="dealproof-backfill")
    try:
        yield
    finally:
        stop.set()
        if backfill is not None and not backfill.done():
            backfill.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await backfill
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=SHUTDOWN_GRACE_SECONDS)
            except TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await dispose_engine()
