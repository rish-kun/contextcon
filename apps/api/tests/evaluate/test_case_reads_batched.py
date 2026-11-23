"""Read paths that used to scale with the data: `GET /cases` reads each summary field for
every case at once, and `GET /cases/{id}` reads on one connection."""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.api import cases_sections
from app.api.cases_sections import build_case_summaries, build_case_summary
from app.db import repo
from app.jobs import create_run
from app.pipelines import evaluate
from app.pipelines.act.request_list import build_request_list_for_case
from app.pipelines.evaluate import flip as flip_service
from tests.evaluate.builders import TODAY, api_client, confirmed_world

pytestmark = pytest.mark.asyncio


async def _world_with_cases(session, extra: int = 2):
    """An assessed, analysed case plus `extra` bare cases (one with a pending run)."""
    w = await confirmed_world(session)
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    for i in range(extra):
        case = await repo.create_case(
            session, w.t.workspace.id, company_name=f"Bare {i} (fixture)", created_by=w.t.user.id
        )
        if i == 0:
            await create_run(
                session, workspace_id=w.t.workspace.id, kind="verify", case_id=case.id, steps=[]
            )
    await session.commit()
    return w


async def _summaries(sm, workspace_id):
    async with sm() as s:
        cases = await repo.list_cases(s, workspace_id)
        one_by_one = [(await build_case_summary(s, workspace_id, c)).model_dump() for c in cases]
    async with sm() as s:
        cases = await repo.list_cases(s, workspace_id)
        batched = [c.model_dump() for c in await build_case_summaries(s, workspace_id, cases)]
    return one_by_one, batched


async def test_batched_list_matches_the_per_case_builders(sm, session) -> None:
    w = await _world_with_cases(session)
    one_by_one, batched = await _summaries(sm, w.t.workspace.id)
    assert batched == one_by_one
    assessed = next(r for r in batched if r["id"] == str(w.t.case.id))
    assert assessed["claim_count"] == 1 and assessed["decision_flip"] is not None
    assert {r["status"] for r in batched} >= {"assessed", "verifying"}


async def test_a_batch_that_returns_nothing_falls_back_per_case(sm, session, monkeypatch) -> None:
    w = await _world_with_cases(session)

    async def nothing(session, workspace_id, ctxs):
        return {}

    for key in list(cases_sections.CASE_SUMMARY_BATCHES):
        monkeypatch.setitem(cases_sections.CASE_SUMMARY_BATCHES, key, nothing)
    one_by_one, batched = await _summaries(sm, w.t.workspace.id)
    assert batched == one_by_one


async def test_list_queries_do_not_grow_with_the_number_of_cases(sm, session) -> None:
    w = await confirmed_world(session)
    engine = sm.kw["bind"].sync_engine
    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    async def list_queries() -> int:
        statements.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            async with api_client(sm, w.t.workspace.id) as client:
                res = await client.get("/cases")
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert res.status_code == 200
        return len(statements)

    one = await list_queries()
    for i in range(4):
        await repo.create_case(session, w.t.workspace.id, company_name=f"More {i} (fixture)")
    await session.commit()
    assert await list_queries() == one


async def test_case_detail_reads_on_one_connection(sm, session) -> None:
    """The message section reads through the request's session, not four sessions."""
    w = await confirmed_world(session)
    await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    await session.commit()
    await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()

    pool = sm.kw["bind"].sync_engine.pool
    checkouts: list[object] = []

    def checked_out(*args):
        checkouts.append(args)

    event.listen(pool, "checkout", checked_out)
    try:
        async with api_client(sm, w.t.workspace.id) as client:
            res = await client.get(f"/cases/{w.t.case.id}")
    finally:
        event.remove(pool, "checkout", checked_out)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["message"] is not None and body["message"]["status"] == "draft"
    assert body["request_list"] is not None and body["request_list"]["items"]
    assert len(checkouts) == 1
