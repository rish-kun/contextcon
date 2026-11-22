"""`GET /runs/{id}/activity` and the `activity` events of `GET /runs/{id}/events`, on
the real app with a signed-in session."""

import datetime as dt
import json

import pytest

from app.auth.sessions import SESSION_COOKIE, create_session
from app.jobs import StepContext, StepRegistry, StepSpec, create_run
from app.jobs import activity as act
from tests.auth.conftest import _auth_env, app, client_for  # noqa: F401
from tests.db.factories import tenant
from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


async def _signed_in(db, name: str):  # type: ignore[no-untyped-def]
    t = await tenant(db, name)
    token, _ = await create_session(db, t.user, ttl=dt.timedelta(hours=1))
    await db.commit()
    return t, token


def _blocks(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        if lines[0].startswith(":"):
            out.append({"comment": lines[0][1:].strip()})
            continue
        fields = dict(line.split(": ", 1) for line in lines)
        out.append({**fields, "data": json.loads(fields["data"])})
    return out


async def _finished_run(db, maker, t, n: int = 5):  # type: ignore[no-untyped-def]
    reg = StepRegistry()

    @reg.handler("work")
    async def work(ctx: StepContext) -> dict:
        for i in range(n):
            await ctx.activity.notice(act.NoticeCode.SOURCE_LIMIT, n=i, total=n)
        return {}

    run = await create_run(
        db,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("verify.registry", "work")],
    )
    await db.commit()
    await make_worker(maker, reg).drain()
    return run


async def test_activity_routes_are_workspace_scoped(app, session, sm) -> None:  # noqa: F811
    t, token = await _signed_in(session, "acme")
    _, other_token = await _signed_in(session, "other")
    run = await _finished_run(session, sm, t)
    path = f"/runs/{run.id}"
    async with client_for(app) as anonymous:
        assert (await anonymous.get(f"{path}/activity")).status_code == 401
        assert (await anonymous.get(f"{path}/events")).status_code == 401
    async with client_for(app, cookies={SESSION_COOKIE: other_token}) as other:
        assert (await other.get(f"{path}/activity")).status_code == 404
        assert (await other.get(f"{path}/events")).status_code == 404
    async with client_for(app, cookies={SESSION_COOKIE: token}) as c:
        page = (await c.get(f"{path}/activity")).json()
        assert [a["seq"] for a in page["items"]] == [1, 2, 3, 4, 5]
        assert page["items"][0]["step_key"] == "verify.registry"
        assert page["items"][0]["kind"] == "notice" and page["items"][0]["code"] == "source_limit"
        assert page["next_after"] is None and page["summary"]["last_seq"] == 5
        tail = (await c.get(f"{path}/activity", params={"after": 3, "limit": 1})).json()
        assert [a["seq"] for a in tail["items"]] == [4] and tail["next_after"] == 4
        assert (await c.get("/runs/not-a-uuid/activity")).status_code == 404


async def test_sse_sends_the_backlog_then_live_and_resumes(app, session, sm) -> None:  # noqa: F811
    t, token = await _signed_in(session, "acme")
    run = await _finished_run(session, sm, t)
    path = f"/runs/{run.id}/events"
    async with client_for(app, cookies={SESSION_COOKIE: token}) as c:
        full = _blocks((await c.get(path)).text)
        resumed = _blocks((await c.get(path, headers={"Last-Event-ID": "3"})).text)
        after = _blocks((await c.get(path, params={"after": 4})).text)

    kinds = [b.get("event") or b["comment"] for b in full]
    assert kinds == ["run", "step", *["activity"] * 5, "live", "run"]
    activity = [b for b in full if b.get("event") == "activity"]
    assert [b["id"] for b in activity] == ["1", "2", "3", "4", "5"]
    assert [b["data"]["seq"] for b in activity] == [1, 2, 3, 4, 5]
    assert full[-1]["data"]["state"] == "done"
    assert [b["data"]["seq"] for b in resumed if b.get("event") == "activity"] == [4, 5]
    assert [b["data"]["seq"] for b in after if b.get("event") == "activity"] == [5]
