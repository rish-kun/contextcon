"""Run status and SSE, wired the way `app/api/runs.py` will call them once auth
supplies the workspace (here a test-only dependency stands in for auth)."""

import asyncio
import json
import uuid

import httpx2 as httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.db import repo
from app.jobs import StepContext, StepRegistry, StepSpec, create_run, events
from tests.db.factories import tenant
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


def _app(sm, workspace_id: uuid.UUID) -> FastAPI:
    app = FastAPI()

    ws = workspace_id  # stands in for the workspace the auth dependency resolves

    @app.get("/runs/{run_id}")
    async def get_run(run_id: uuid.UUID):
        async with sm() as session:
            try:
                return await events.load_run_out(session, ws, run_id)
            except repo.NotFound:
                raise HTTPException(404) from None

    @app.get("/runs/{run_id}/events")
    async def stream(run_id: uuid.UUID, request: Request):
        await get_run(run_id)  # 404 before the stream starts
        return StreamingResponse(
            events.run_event_stream(sm, ws, run_id, is_disconnected=request.is_disconnected),
            media_type="text/event-stream",
        )

    @app.post("/runs/{run_id}/resume")
    async def resume(run_id: uuid.UUID):
        async with sm() as session:
            return await events.resume_run_out(session, ws, run_id)

    return app


def _client(sm, workspace_id) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=_app(sm, workspace_id))
    return httpx.AsyncClient(transport=transport, base_url="http://t")


def _parse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


async def test_run_out_matches_contract_and_is_workspace_scoped(session, sm) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    run = await create_run(
        session,
        workspace_id=a.workspace.id,
        kind="verify",
        case_id=a.case.id,
        steps=[StepSpec("verify.identity", "noop", label="Confirm identity")],
    )
    await session.commit()
    async with _client(sm, a.workspace.id) as client:
        ok = await client.get(f"/runs/{run.id}")
    async with _client(sm, b.workspace.id) as client:
        other = await client.get(f"/runs/{run.id}")
    assert ok.status_code == 200
    body = ok.json()
    assert body["state"] == "pending" and body["subject"] == "a target (fixture)"
    assert body["budget_credits"] == 150
    assert body["steps"][0]["label"] == "Confirm identity"
    assert body["steps"][0]["cost"]["crustdata_credits"] == 0
    assert other.status_code == 404


async def test_sse_streams_step_changes_until_the_run_ends(session, sm, monkeypatch) -> None:
    monkeypatch.setattr(events, "POLL_SECONDS", 0.05)
    t = await tenant(session, credit_budget=0)
    reg = StepRegistry()
    gate = asyncio.Event()

    @reg.handler("wait")
    async def wait(ctx: StepContext) -> dict:
        await ctx.set_detail("Reading the registry record")
        await gate.wait()
        ctx.result = "Profile built"
        return {}

    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[
            StepSpec("profile", "wait", uses_budget=False),
            StepSpec("funding", "noop", label="Check: funding"),
        ],
    )
    await session.commit()
    worker = make_worker(sm, reg)

    async def drive() -> None:
        await asyncio.sleep(0.2)
        work = asyncio.create_task(worker.drain())
        await asyncio.sleep(0.3)
        gate.set()
        await work

    async with _client(sm, t.workspace.id) as client:
        driver = asyncio.create_task(drive())
        resp = await asyncio.wait_for(client.get(f"/runs/{run.id}/events"), 10)
        await driver
    assert resp.headers["content-type"].startswith("text/event-stream")
    evts = _parse(resp.text)
    assert evts[0][0] == "run" and evts[0][1]["state"] == "pending" and evts[0][1]["steps"] == []
    assert evts[-1] == ("end", {})
    assert evts[-2][0] == "run" and evts[-2][1]["state"] == "done"
    profile = [d for e, d in evts if e == "step" and d["key"] == "profile"]
    assert [p["state"] for p in profile][0] == "pending"
    assert any(p["detail"] == "Reading the registry record" for p in profile)
    assert profile[-1]["state"] == "done" and profile[-1]["result"] == "Profile built"
    funding = [d for e, d in evts if e == "step" and d["key"] == "funding"]
    assert funding[-1]["state"] == "skipped_budget"
    assert funding[-1]["result"] == "Not checked: budget reached"
    assert evts[-2][1]["checks_not_run"] == 1


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
    async with _client(sm, b.workspace.id) as client:
        resp = await client.get(f"/runs/{run.id}/events")
    assert resp.status_code == 404


async def test_resume_requeues_skipped_steps(session, sm) -> None:
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
    async with _client(sm, t.workspace.id) as client:
        before = (await client.get(f"/runs/{run.id}")).json()
        after = (await client.post(f"/runs/{run.id}/resume")).json()
    assert before["steps"][0]["state"] == "skipped_budget" and before["checks_not_run"] == 1
    assert after["state"] == "running" and after["steps"][0]["state"] == "pending"
    assert after["resumed_at"] is not None


async def test_step_errors_are_sanitised(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("boom")
    async def boom(ctx: StepContext) -> dict:
        raise RuntimeError("GET https://api.example.test/x?api_key=sk-123 failed token=abc")

    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("s", "boom", max_attempts=1)],
    )
    await session.commit()
    await make_worker(sm, reg).drain()
    async with _client(sm, t.workspace.id) as client:
        error = (await client.get(f"/runs/{run.id}")).json()["steps"][0]["error"]
    assert error == "RuntimeError"  # the message (URL, key) stays in the server log


async def test_sse_run_header_spend_keeps_up_with_the_steps(session, sm, monkeypatch) -> None:
    """Regression: the run event used to be re-sent only on a state change, so a live
    header read "0 of 60 credits" while finished steps already showed 7 cr."""
    from decimal import Decimal

    from app.db.models import CostEntry

    monkeypatch.setattr(events, "POLL_SECONDS", 0.05)
    t = await tenant(session)
    reg = StepRegistry()
    gate = asyncio.Event()

    @reg.handler("paid")
    async def paid(ctx: StepContext) -> dict:
        async with ctx.sessionmaker() as s:  # settled spend, visible before the step ends
            s.add(
                CostEntry(
                    workspace_id=ctx.run.workspace_id,
                    case_id=ctx.run.case_id,
                    run_id=ctx.run.id,
                    step_id=ctx.step_id,
                    provider="crustdata",
                    endpoint="/screener/companysearch",
                    credits=Decimal(ctx.input["credits"]),
                )
            )
            await s.commit()
        return {}

    opened = asyncio.Event()

    @reg.handler("open")
    async def open_(ctx: StepContext) -> dict:
        await opened.wait()
        return {}

    @reg.handler("wait")
    async def wait(ctx: StepContext) -> dict:
        await gate.wait()
        return {}

    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[
            StepSpec("plan", "open", uses_budget=False),
            StepSpec("search", "paid", input={"credits": "4"}, depends_on=["plan"]),
            StepSpec("enrich", "paid", input={"credits": "3"}, depends_on=["search"]),
            StepSpec("rank", "wait", depends_on=["enrich"], uses_budget=False),
        ],
    )
    await session.commit()
    worker = make_worker(sm, reg)

    async def drive() -> None:
        work = asyncio.create_task(worker.drain())
        await asyncio.sleep(0.4)  # the stream has seen the run running at 0 credits
        opened.set()
        await asyncio.sleep(0.6)
        gate.set()
        await work

    async with _client(sm, t.workspace.id) as client:
        driver = asyncio.create_task(drive())
        resp = await asyncio.wait_for(client.get(f"/runs/{run.id}/events"), 10)
        await driver
        final = (await client.get(f"/runs/{run.id}")).json()
    evts = _parse(resp.text)
    running = [d for e, d in evts if e == "run" and d["state"] == "running"]
    assert any(d["cost"]["crustdata_credits"] == 7 for d in running), running
    steps = {d["key"]: d for e, d in evts if e == "step"}
    assert sum(s["cost"]["crustdata_credits"] for s in steps.values()) == 7
    assert evts[-2][1]["cost"]["crustdata_credits"] == 7
    assert final["cost"]["crustdata_credits"] == sum(
        s["cost"]["crustdata_credits"] for s in final["steps"]
    )
    assert final["reserved_credits"] == 0


async def test_sse_reconnect_to_a_finished_run_ends_after_the_backlog(session, sm) -> None:
    """A reconnect to a finished run gets the finished run first, then the backlog. The
    client must not close on that first snapshot: `event: end` comes after every
    activity, as the very last frame."""
    from app.jobs import activity as act

    t = await tenant(session)
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("only", "noop", uses_budget=False)],
    )
    await session.commit()
    reg = StepRegistry()
    await make_worker(sm, reg).drain()
    em = act.ActivityEmitter(sm, workspace_id=t.workspace.id, run_id=run.id)
    seqs = await em.write([act.envelope(act.Kind.STATUS, act.Label(f"s{i}")) for i in range(3)])
    assert seqs == [1, 2, 3]

    frames = [f async for f in events.run_event_stream(sm, t.workspace.id, run.id, after=1)]
    evts = _parse("".join(frames))
    assert evts[0][0] == "run" and evts[0][1]["state"] == "done"
    kinds = [e for e, _ in evts]
    assert [d["seq"] for e, d in evts if e == "activity"] == [2, 3]
    assert kinds.index("activity") > 0  # the finished snapshot came before the backlog
    assert evts[-1] == ("end", {})
    assert kinds.count("end") == 1
    assert max(i for i, k in enumerate(kinds) if k == "activity") < kinds.index("end")
