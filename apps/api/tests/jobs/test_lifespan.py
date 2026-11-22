import asyncio

import pytest
from fastapi import FastAPI

from app.db import session as db_session
from app.jobs import StepSpec, create_run
from app.jobs.config import get_job_settings
from app.jobs.lifespan import jobs_lifespan
from tests.db.factories import tenant
from tests.jobs.helpers import run_state

pytestmark = pytest.mark.asyncio


@pytest.fixture
def job_env(monkeypatch):
    def configure(**env: str) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_job_settings.cache_clear()

    yield configure
    get_job_settings.cache_clear()


async def test_in_process_worker_runs_steps(session, sm, db_url, job_env) -> None:
    job_env(WORKER_IN_PROCESS="true", WORKER_POLL_SECONDS="0.05")
    t = await tenant(session)
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("a", "noop")],
    )
    await session.commit()
    db_session.init_engine(db_url)
    app = FastAPI()
    async with jobs_lifespan(app):
        assert app.state.worker is not None
        for _ in range(100):
            if await run_state(sm, run.id) == "done":
                break
            await asyncio.sleep(0.05)
    assert await run_state(sm, run.id) == "done"
    assert db_session._engine is None  # disposed on shutdown


async def test_flag_disables_in_process_worker(db_url, job_env) -> None:
    job_env(WORKER_IN_PROCESS="false")
    db_session.init_engine(db_url)
    app = FastAPI()
    async with jobs_lifespan(app):
        assert not hasattr(app.state, "worker")
