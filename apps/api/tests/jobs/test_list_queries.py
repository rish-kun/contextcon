"""`GET /cases` and `GET /runs` cost a fixed number of queries, however many rows they
show. Each statement is a network round trip to Neon (~50 ms from the API's region),
so a per-row query turns a 20-row page into seconds."""

from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.api.schemas.runs import RunQueueStatus
from app.jobs import queue
from tests.evaluate.builders import api_client
from tests.jobs.list_seed import seed

pytestmark = pytest.mark.asyncio


@contextmanager
def counting(sm):
    engine = sm.kw["bind"].sync_engine
    seen: list[str] = []

    def count(conn, cursor, statement, *args) -> None:  # noqa: ANN001
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", count)


async def _counts(sm, workspace_id) -> tuple[int, int, int, int]:
    async with api_client(sm, workspace_id) as client:
        with counting(sm) as cases_sql:
            cases = (await client.get("/cases")).json()
    with counting(sm) as runs_sql:
        async with sm() as s:
            runs = await queue.list_run_queue(s, workspace_id, status=RunQueueStatus.recent)
    return len(cases), len(cases_sql), len(runs.items), len(runs_sql)


async def test_list_queries_do_not_grow_with_rows(session, sm) -> None:
    small = await seed(session, 2)
    n_cases, cases_sql, n_runs, runs_sql = await _counts(sm, small.t.workspace.id)
    assert (n_cases, n_runs) == (2, 5)

    big = await seed(session, 6)
    more_cases, more_cases_sql, more_runs, more_runs_sql = await _counts(sm, big.t.workspace.id)
    assert (more_cases, more_runs) == (6, 13)
    assert more_cases_sql == cases_sql <= 10
    assert more_runs_sql == runs_sql <= 8


async def test_list_rows_match_the_single_row_builders(session, sm) -> None:
    """The batched rows equal what the per-row builders give for the same data."""
    from app.api.cases_sections import CaseContext, case_status
    from app.db import ledger, repo
    from app.jobs.events import load_run_out

    seeded = await seed(session, 5)
    ws = seeded.t.workspace.id
    async with api_client(sm, ws) as client:
        rows = {r["id"]: r for r in (await client.get("/cases")).json()}
    async with sm() as s:
        for case in await repo.list_cases(s, ws):
            row = rows[str(case.id)]
            totals = await ledger.case_totals(s, ws, case.id)
            assert row["cost"]["crustdata_credits"] == float(totals.credits)
            assert row["cost"]["unknown_cost_calls"] == totals.unknown_calls
            assert row["status"] == await case_status(CaseContext(s, ws, case))
        recent = await queue.list_run_queue(s, ws, status=RunQueueStatus.recent, limit=50)
        for item in recent.items:
            single = queue.queue_item(await load_run_out(s, ws, item.id))
            assert item.credits == single.credits
            assert (item.steps_done, item.steps_total) == (single.steps_done, single.steps_total)
            assert item.owner == single.owner and item.llm_usd == single.llm_usd
    flips = [r["decision_flip"] for r in rows.values()]
    assert any(f is not None for f in flips) and any(f is None for f in flips)
