"""Public read-only showcase: only flagged rows, no session, scrubbed, rate-limited."""

import httpx2 as httpx
import pytest

from app.api import showcase
from app.db.models import Run
from app.main import create_app
from app.pipelines import evaluate
from app.pipelines.memo import drafting
from tests.evaluate.builders import TODAY, confirmed_world

pytestmark = pytest.mark.asyncio


@pytest.fixture
def public_client(sm, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    monkeypatch.setattr(showcase, "get_sessionmaker", lambda: sm)
    monkeypatch.setattr(showcase, "LIMITER", showcase.PublicRateLimiter())
    app = create_app()  # no auth overrides: these routes must work without a session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _world(session):
    w = await confirmed_world(session)
    await evaluate.evaluate_case(
        session, w.t.workspace.id, w.t.case.id, today=TODAY, enrich=drafting.build_memo_document
    )
    run = Run(workspace_id=w.t.workspace.id, kind="verify", state="done", case_id=w.t.case.id)
    session.add(run)
    await session.commit()
    return w, run


async def test_nothing_is_public_until_a_case_is_flagged(sm, session, public_client) -> None:
    w, run = await _world(session)
    async with public_client as client:
        index = (await client.get("/public/showcase")).json()
        assert index["case_id"] is None and index["run_ids"] == []
        assert (await client.get("/public/showcase/case")).status_code == 404
        assert (await client.get("/public/showcase/discovery")).status_code == 404
        assert (await client.get("/public/showcase/investors")).status_code == 404
        assert (await client.get(f"/public/showcase/runs/{run.id}")).status_code == 404
        # the signed-in routes still need a session
        assert (await client.get(f"/cases/{w.t.case.id}")).status_code == 401


async def test_flagged_case_is_served_without_a_session(sm, session, public_client) -> None:
    w, run = await _world(session)
    w.t.case.is_showcase = True
    w.t.case.company_name = "Example Logistics (fixture)"
    other = Run(workspace_id=w.t.workspace.id, kind="discover", state="done")
    session.add(other)
    await session.commit()
    async with public_client as client:
        index = (await client.get("/public/showcase")).json()
        assert index["case_id"] == str(w.t.case.id)
        assert index["run_ids"] == [str(run.id)]
        res = await client.get("/public/showcase/case")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["case"]["id"] == str(w.t.case.id)
        assert body["case"]["owner"]["user_id"] == ""  # internal user id blanked
        assert [c["original_text"] for c in body["claims"]] == ["We have 250 employees"]
        versions = (await client.get("/public/showcase/case/assessments")).json()
        assert [v["version"] for v in versions] == [1]
        assert (await client.get(f"/public/showcase/runs/{run.id}")).status_code == 200
        assert (await client.get(f"/public/showcase/runs/{run.id}/activity")).status_code == 200
        # a run that is not the showcase's is never served
        assert (await client.get(f"/public/showcase/runs/{other.id}")).status_code == 404
        assert (await client.get("/public/showcase/runs/not-a-uuid")).status_code == 404
        # read-only: no write methods exist on the public prefix
        assert (await client.post("/public/showcase/case")).status_code == 405


def test_scrub_removes_contact_details_and_user_ids() -> None:
    out = showcase.scrub(
        {
            "owner": {"user_id": "u-1", "display_name": "Asha Rao"},
            "current_revision": {
                "recipient": "cfo@example.test",
                "entered_by_user_id": "u-2",
                "body": "Write to sales@example.test or call +91 98450 12345.",
            },
            "as_of": "2026-11-22",
            "retrieved_at": "2026-11-22T11:18:48.430862Z",
            "redaction_counts": {"email": 2},
        }
    )
    assert out["owner"] == {"user_id": "", "display_name": "Asha Rao"}
    rev = out["current_revision"]
    assert rev["recipient"] == "" and rev["entered_by_user_id"] == ""
    assert "example.test" not in rev["body"] and "98450" not in rev["body"]
    assert out["as_of"] == "2026-11-22"
    assert out["retrieved_at"] == "2026-11-22T11:18:48.430862Z"
    assert out["redaction_counts"] == {"email": 2}


def test_rate_limiter_per_client_and_global() -> None:
    lim = showcase.PublicRateLimiter(per_client=2, total=3, window=60)
    assert lim.allow("1.1.1.1", now=0) and lim.allow("1.1.1.1", now=1)
    assert not lim.allow("1.1.1.1", now=2)  # per-client limit
    assert lim.allow(None, now=3)  # shared address: global ceiling only
    assert not lim.allow("2.2.2.2", now=4)  # global ceiling reached
    assert lim.allow("1.1.1.1", now=61)  # the window slides


async def test_rate_limit_answers_429(sm, session, public_client, monkeypatch) -> None:
    monkeypatch.setattr(showcase, "LIMITER", showcase.PublicRateLimiter(per_client=1, total=1))
    async with public_client as client:
        assert (await client.get("/public/showcase")).status_code == 200
        res = await client.get("/public/showcase")
        assert res.status_code == 429 and res.headers["retry-after"] == "60"
