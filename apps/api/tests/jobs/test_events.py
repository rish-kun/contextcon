import asyncio
import json

import httpx2 as httpx
import pytest
from fastapi import FastAPI

from app.db.session import get_session
from app.jobs import StepContext, StepRegistry, StepSpec, create_run
from app.jobs import events as events_module
from app.jobs.events import router, sessionmaker_dep
from tests.db.factories import tenant
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


def _app(sm) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def session_override():
        async with sm() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[sessionmaker_dep] = lambda: sm
    return app


def _client(sm) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(sm)), base_url="http://t")


def _parse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


async def test_get_run_is_workspace_scoped(session, sm) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    run = await create_run(
        session,
        workspace_id=a.workspace.id,
        kind="verify",
        case_id=a.case.id,
        steps=[StepSpec("identity", "noop")],
    )
    await session.commit()
    async with _client(sm) as client:
        ok = await client.get(f"/runs/{run.id}", headers={"x-workspace-id": str(a.workspace.id)})
        other = await client.get(f"/runs/{run.id}", headers={"x-workspace-id": str(b.workspace.id)})
        anon = await client.get(f"/runs/{run.id}")
    assert ok.status_code == 200
    body = ok.json()
    assert body["state"] == "pending" and [s["key"] for s in body["steps"]] == ["identity"]
    assert other.status_code == 404
    assert anon.status_code == 401


async def test_sse_streams_step_changes_until_the_run_ends(session, sm, monkeypatch) -> None:
    monkeypatch.setattr(events_module, "POLL_SECONDS", 0.05)
    t = await tenant(session, credit_budget=0)
    reg = StepRegistry()
    gate = asyncio.Event()

    @reg.handler("wait")
    async def wait(ctx: StepContext) -> dict:
        await gate.wait()
        return {}

    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("profile", "wait", uses_budget=False), StepSpec("funding", "noop")],
    )
    await session.commit()
    headers = {"x-workspace-id": str(t.workspace.id)}
    worker = make_worker(sm, reg)

    async def drive() -> None:
        await asyncio.sleep(0.2)
        work = asyncio.create_task(worker.drain())
        await asyncio.sleep(0.2)
        gate.set()
        await work

    async with _client(sm) as client:
        driver = asyncio.create_task(drive())
        resp = await asyncio.wait_for(client.get(f"/runs/{run.id}/events", headers=headers), 10)
        await driver
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse(resp.text)
    assert events[0][0] == "run" and events[0][1]["state"] == "pending"
    assert events[-1][0] == "run" and events[-1][1]["state"] == "done"
    step_events = [(d["key"], d["state"]) for e, d in events if e == "step"]
    assert ("profile", "running") in step_events and ("profile", "done") in step_events
    funding = [d for e, d in events if e == "step" and d["key"] == "funding"]
    assert funding[-1]["state"] == "skipped_budget"
    assert funding[-1]["not_checked_reason"] == "Not checked: budget reached"


async def test_sse_404_for_other_workspace(session, sm) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    run = await create_run(
        session,
        workspace_id=a.workspace.id,
        kind="verify",
        case_id=a.case.id,
        steps=[StepSpec("s", "noop")],
    )
    await session.commit()
    async with _client(sm) as client:
        resp = await client.get(
            f"/runs/{run.id}/events", headers={"x-workspace-id": str(b.workspace.id)}
        )
    assert resp.status_code == 404


async def test_resume_endpoint(session, sm) -> None:
    t = await tenant(session, credit_budget=0)
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("s", "noop")],
    )
    await session.commit()
    await make_worker(sm, StepRegistry()).drain()
    headers = {"x-workspace-id": str(t.workspace.id)}
    async with _client(sm) as client:
        before = (await client.get(f"/runs/{run.id}", headers=headers)).json()
        after = (await client.post(f"/runs/{run.id}/resume", headers=headers)).json()
    assert before["steps"][0]["state"] == "skipped_budget"
    assert after["state"] == "running" and after["steps"][0]["state"] == "pending"
