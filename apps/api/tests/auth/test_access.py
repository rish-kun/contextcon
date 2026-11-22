"""Workspace scoping through auth: runs endpoints, case access, and named approvals."""

import json
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.auth.deps import AuthorizedCaseId, CurrentUser, WorkspaceId
from app.db.enums import RunState, StepState
from app.db.models import Run, Step
from app.jobs import StepSpec, create_run, events
from tests.auth.conftest import client_for
from tests.auth.helpers import account, login

pytestmark = pytest.mark.asyncio


async def _run(session, acct, *, state: RunState | None = None) -> Run:
    run = await create_run(
        session,
        workspace_id=acct.workspace.id,
        kind="verify",
        case_id=acct.case.id,
        steps=[StepSpec("verify.identity", "noop", label="Confirm identity")],
    )
    await session.commit()
    if state is not None:
        await session.execute(update(Run).where(Run.id == run.id).values(state=state))
        await session.commit()
    return run


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


async def test_runs_endpoints_need_a_session(client, session) -> None:
    a = await account(session, "asha")
    run = await _run(session, a)
    for method, path in [
        ("GET", f"/runs/{run.id}"),
        ("GET", f"/runs/{run.id}/events"),
        ("POST", f"/runs/{run.id}/resume"),
    ]:
        response = await client.request(method, path)
        assert response.status_code == 401, path
        assert response.headers["content-type"].startswith("application/json")


async def test_run_status_and_events_for_own_workspace(client, session, monkeypatch) -> None:
    monkeypatch.setattr(events, "POLL_SECONDS", 0.01)
    a = await account(session, "asha")
    run = await _run(session, a, state=RunState.DONE)
    await login(client, a.email)

    status = await client.get(f"/runs/{run.id}")
    assert status.status_code == 200
    assert status.json()["case_id"] == str(a.case.id)
    assert status.json()["steps"][0]["label"] == "Confirm identity"

    stream = await client.get(f"/runs/{run.id}/events")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    evts = _events(stream.text)
    assert (
        evts[0][0] == "run"
        and evts[-1] == ("end", {})
        and evts[-2][0] == "run"
        and evts[-2][1]["state"] == "done"
    )
    assert [e for e, _ in evts].count("step") == 1


async def test_resume_requeues_failed_steps(client, session) -> None:
    a = await account(session, "asha")
    run = await _run(session, a, state=RunState.FAILED)
    await session.execute(
        update(Step).where(Step.run_id == run.id).values(state=StepState.FAILED, error="boom")
    )
    await session.commit()
    await login(client, a.email)
    response = await client.post(f"/runs/{run.id}/resume")
    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "running"
    assert body["steps"][0]["state"] == "pending"


async def test_cross_workspace_access_denied(app, session) -> None:
    a = await account(session, "asha")
    b = await account(session, "bilal")
    theirs = await _run(session, b, state=RunState.FAILED)
    async with client_for(app) as client:
        await login(client, a.email)
        for method, path in [
            ("GET", f"/runs/{theirs.id}"),
            ("GET", f"/runs/{theirs.id}/events"),
            ("POST", f"/runs/{theirs.id}/resume"),
            ("GET", f"/runs/{uuid.uuid4()}"),
            ("GET", "/runs/not-a-uuid"),
        ]:
            response = await client.request(method, path)
            assert response.status_code == 404, path
            assert response.headers["content-type"].startswith("application/json")
        # Act routes on the other workspace's case are 404 too, before anything is created.
        response = await client.post(
            f"/cases/{b.case.id}/messages",
            json={"subject": "s", "body": "b", "recipient": "seller@target.example"},
        )
        assert response.status_code == 404
        assert (await client.get(f"/cases/{b.case.id}/messages/send-summary")).status_code == 404
    # The resume attempt changed nothing.
    await session.refresh(theirs)
    assert theirs.state == RunState.FAILED


async def test_act_approval_records_the_signed_in_user(app, session) -> None:
    a = await account(session, "asha")
    approver = await account(session, "aarav")
    # A second named user in Asha's workspace approves what Asha drafted.
    approver.user.workspace_id = a.workspace.id
    await session.commit()
    base = f"/cases/{a.case.id}/messages"

    async with client_for(app) as drafter:
        await login(drafter, a.email)
        created = await drafter.post(
            base, json={"subject": "Documents", "body": "Please share", "recipient": "s@t.example"}
        )
        assert created.status_code == 201, created.text
        message = created.json()
        assert message["current_revision"]["entered_by_user_id"] == str(a.user.id)

    async with client_for(app) as checker:
        await login(checker, approver.email)
        approved = await checker.post(
            f"{base}/{message['id']}/approve",
            json={"revision_id": message["current_revision"]["id"]},
        )
    assert approved.status_code == 200, approved.text
    approval = approved.json()["approval"]
    assert approval["approver_user_id"] == str(approver.user.id)
    assert approval["approver_display_name"] == "Aarav Analyst"


async def test_dependencies_for_other_routes(app, session) -> None:
    """The dependencies other routers import: user, workspace and case authorisation."""
    a = await account(session, "asha")
    b = await account(session, "bilal")
    probe = FastAPI()

    @probe.get("/cases/{case_id}/probe")
    async def handler(case_id: AuthorizedCaseId, user: CurrentUser, ws: WorkspaceId) -> dict:
        return {"case": str(case_id), "user": str(user.id), "ws": str(ws)}

    async with client_for(probe) as client:
        assert (await client.get(f"/cases/{a.case.id}/probe")).status_code == 401
        async with client_for(app) as signer:  # sign in through the real app
            await login(signer, a.email)
            client.cookies.update(dict(signer.cookies))
        ok = await client.get(f"/cases/{a.case.id}/probe")
        assert ok.status_code == 200
        assert ok.json() == {
            "case": str(a.case.id),
            "user": str(a.user.id),
            "ws": str(a.workspace.id),
        }
        assert (await client.get(f"/cases/{b.case.id}/probe")).status_code == 404
        assert (await client.get("/cases/nope/probe")).status_code == 404
