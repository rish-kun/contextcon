"""A Discover run's live activity: calls, then candidates found, dropped, enriched,
scored and explained, all keyed by the candidate row id."""

import pytest
from sqlalchemy import select

from app.api.schemas.runs import ActivityOut
from app.db.models import Candidate, RunActivity
from app.jobs import activity as act
from tests.pipelines import discover_fakes as fakes
from tests.pipelines.test_discover import _run

pytestmark = pytest.mark.asyncio


async def test_discover_streams_its_candidates(session, sm, monkeypatch) -> None:
    monkeypatch.setattr(act, "STATUS_INTERVAL", 0.0)
    fake = fakes.FakeCrustdata(fakes.make_world(fillers=10))
    _, _, run = await _run(session, sm, fake)
    async with sm() as s:
        events = list(
            (
                await s.execute(
                    select(RunActivity.payload)
                    .where(RunActivity.run_id == run.id)
                    .order_by(RunActivity.seq)
                )
            ).scalars()
        )
        cands = {
            str(c.id): c
            for c in (
                await s.execute(
                    select(Candidate).where(Candidate.discovery_run_id == run.discovery_run_id)
                )
            ).scalars()
        }
    for e in events:
        ActivityOut.model_validate(e)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))

    calls = [e["call"]["endpoint"] for e in events if e["kind"] == "call"]
    assert calls[0] == "company_search" and "company_enrich" in calls
    search = next(e for e in events if e["kind"] == "call")
    assert search["detail"]  # the user's own filters, in words (not a case run)
    assert set(search["counts"]) <= {"returned", "new", "total_available"}

    company = [e for e in events if e["kind"] == "finding" and e["subject"] == "company"]
    stages = [e["items"][0]["stage"] for e in company]
    order = ["found", "dropped", "enriched", "scored", "explained"]
    assert [s for s in order if s in stages] == order
    # Stages arrive in pipeline order.
    firsts = [stages.index(s) for s in order]
    assert firsts == sorted(firsts)

    # Every item id is a candidate row the client can join with the shortlist.
    scored = [i for e in company for i in e["items"] if i["stage"] == "scored"]
    assert scored and all(i["id"] in cands for i in scored)
    assert {i["rank"] for i in scored} == {c.rank for c in cands.values() if c.rank}
    dropped = [i for e in company for i in e["items"] if i["stage"] == "dropped"]
    assert any(i["reason"].startswith("Duplicate of") for i in dropped)
    assert any(i["reason"].startswith("Failed must-have") for i in dropped)
    enriched = [i for e in company for i in e["items"] if i["stage"] == "enriched"]
    assert enriched and all(set(i["marks"]) == {"funding", "headcount", "hiring"} for i in enriched)
    last = [e["counts"] for e in company if e["counts"]][-1]
    assert last["found"] >= last["in_play"] >= 0 and last["scored"] == len(scored)
