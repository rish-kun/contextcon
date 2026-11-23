"""Profile `GET /cases`, `GET /runs?status=recent` and `GET /cases/{id}` on a seeded
local Postgres: statement count and wall time, with and without an emulated network
round trip per statement (Neon from the API's region is ~40-60 ms).

    uv run python -m tests.jobs.profile_lists [n_cases] [rtt_ms]
"""

from __future__ import annotations

import asyncio
import sys
import time

from sqlalchemy import event

from app.api.schemas.runs import RunQueueStatus
from app.db.session import make_engine, make_sessionmaker
from app.jobs import queue
from tests.db import pg
from tests.evaluate.builders import api_client
from tests.jobs.list_seed import seed


async def main(url: str, n_cases: int, rtt_ms: float) -> None:
    if True:
        engine = make_engine(url)
        sm = make_sessionmaker(engine)
        async with sm() as s:
            seeded = await seed(s, n_cases)
        state = {"n": 0, "delay": 0.0}

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def _count(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
            state["n"] += 1
            if state.get("log"):
                print("   SQL:", " ".join(statement.split())[:230])
            if state["delay"]:
                time.sleep(state["delay"])

        ws = seeded.t.workspace.id

        async def cases(client):
            r = await client.get("/cases")
            assert r.status_code == 200, r.text
            return len(r.json())

        async def detail(client):
            r = await client.get(f"/cases/{seeded.case_ids[0]}")
            assert r.status_code == 200, r.text
            return 1

        async def runs(_client):
            async with sm() as s:
                out = await queue.list_run_queue(s, ws, status=RunQueueStatus.recent, limit=20)
            return len(out.items)

        async with api_client(sm, ws) as client:
            if "--log" in sys.argv:
                for name, fn in (("cases", cases), ("runs", runs), ("detail", detail)):
                    if name in sys.argv:
                        await fn(client)
                        state["log"] = True
                        await fn(client)
                        state["log"] = False
                return
            for delay in (0.0, rtt_ms / 1000):
                state["delay"] = delay
                for name, fn in (("cases", cases), ("runs", runs), ("detail", detail)):
                    await fn(client)  # warm
                    state["n"] = 0
                    t0 = time.perf_counter()
                    rows = await fn(client)
                    ms = (time.perf_counter() - t0) * 1000
                    print(
                        f"rtt={delay * 1000:>4.0f}ms {name:<7} rows={rows:<3} "
                        f"statements={state['n']:<4} {ms:8.1f} ms"
                    )
        await engine.dispose()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    rtt = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
    with pg.server_url() as admin, pg.fresh_database(admin) as db:
        pg.migrate(db)
        asyncio.run(main(db, n, rtt))
