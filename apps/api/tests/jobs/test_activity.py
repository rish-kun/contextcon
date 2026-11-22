"""The live activity stream: the emitter, the client hooks, ordering, fencing, status
throttling, resume, cleaning and the run summary."""

import asyncio
import json
import uuid
from datetime import timedelta

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.api.schemas.runs import ActivityOut
from app.clients import CrustdataClient, LLMClient, SlidingWindowRateLimiter
from app.clients.activity import activity_topic
from app.clients.crustdata import CrustdataError
from app.db.ledger import CostContext, record_cost
from app.db.models import RunActivity, Step
from app.jobs import StepContext, StepRegistry, StepSpec, create_run
from app.jobs import activity as act
from app.jobs.events import load_activity_page
from tests.db.factories import discovery_run, tenant
from tests.jobs.helpers import make_worker, states

pytestmark = pytest.mark.asyncio

SECRET = "Project Falcon anchor client Zentrix pays 4.2 crore"

RESPONSES = {
    "/company/search": {
        "companies": [
            {
                "crustdata_company_id": 11,
                "basic_info": {"name": "Alpha Freight (fixture)", "primary_domain": "alpha.test"},
                "locations": {"headquarters": "Pune, India"},
            },
            {"crustdata_company_id": 12, "basic_info": {"name": "Beta Cold Chain (fixture)"}},
        ],
        "total_count": 48,
    },
    "/company/enrich": [
        {
            "matches": [
                {
                    "company_data": {
                        "crustdata_company_id": 11,
                        "updated_at": "2026-11-01T00:00:00Z",
                        "basic_info": {"name": "Alpha Freight (fixture)"},
                        "headcount": {"total": 140, "timeseries": [{"date": "2026-01-01"}]},
                        "funding": {
                            "investors": ["Kite (fixture)"],
                            "milestones": [{"round_type": "series_a", "date": "2025-03-14"}],
                        },
                    }
                }
            ]
        }
    ],
    "/person/search": {
        "profiles": [
            {
                "basic_profile": {"name": "Asha Rao", "current_title": "Founder & CEO"},
                "experience": {"employment_details": {"current": [{"crustdata_company_id": 11}]}},
            },
            {"basic_profile": {"name": "Ravi Iyer", "current_title": "CFO"}},
        ],
    },
    "/job/search": {"job_listings": [{"job_details": {"title": "Warehouse lead"}}]},
    "/web/search/live": {
        "results": [
            {"url": "https://www.news.test/a?utm_source=x", "title": "Alpha", "source": "news"},
            {"url": "https://registry.test/rec/1", "title": "Record", "source": "web"},
        ]
    },
    "/web/enrich/live": [
        {
            "success": True,
            "url": "https://www.news.test/a?utm_source=x&id=7",
            "title": "Alpha Freight opens a Pune hub",
            "content": "<p>Alpha Freight opened a hub.</p>",
        },
        {"success": False, "url": None},
    ],
}
CREDITS = {
    "/company/search": "0.6",
    "/company/enrich": "2",
    "/person/search": "0.26",
    "/job/search": "0.03",
    "/web/search/live": "1",
    "/web/enrich/live": "1",
}


def crustdata(recorder, cache, fail: set[str] = frozenset()) -> CrustdataClient:  # type: ignore[no-untyped-def]
    def handle(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path in fail:
            return httpx2.Response(400, json={"error": {"type": "bad_request", "message": SECRET}})
        return httpx2.Response(200, json=RESPONSES[path], headers={"x-credits-used": CREDITS[path]})

    async def no_sleep(_: float) -> None:
        return None

    return CrustdataClient(
        "test-key",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        recorder=recorder,
        cache=cache,
        rate_limiter=SlidingWindowRateLimiter({}),
        sleep=no_sleep,
    )


class Headcount(BaseModel):
    employees: int | None


def llm(recorder, cache, prompts: list) -> LLMClient:  # type: ignore[no-untyped-def]
    def handle(request: httpx2.Request) -> httpx2.Response:
        prompts.append(request.content.decode())
        return httpx2.Response(
            200,
            json={
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": json.dumps({"employees": 250})}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 900, "output_tokens": 12},
            },
            headers={"request-id": "req_llm"},
        )

    sdk = AsyncAnthropic(
        api_key="k",
        base_url="https://anthropic.test",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    return LLMClient(client=sdk, recorder=recorder, cache=cache)


async def payloads(sm, run_id) -> list[dict]:  # type: ignore[no-untyped-def]
    async with sm() as s:
        rows = await s.execute(
            select(RunActivity.payload)
            .where(RunActivity.run_id == run_id)
            .order_by(RunActivity.seq)
        )
        out = list(rows.scalars())
    for p in out:
        ActivityOut.model_validate(p)  # every stored event fits the contract
    return out


async def run_one(session, sm, t, handler, *, kind="verify", case=True):  # type: ignore[no-untyped-def]
    reg = StepRegistry()
    reg.register("work", handler)
    owner = (
        {"case_id": t.case.id}
        if case
        else {"discovery_run_id": (await discovery_run(session, t)).id}
    )
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind=kind,
        steps=[StepSpec("work", "work")],
        **owner,
    )
    await session.commit()
    await make_worker(sm, reg).drain()
    assert await states(sm, run.id) == {"work": "done"}
    return run


async def test_client_hooks_emit_calls_sources_and_model_reads(session, sm) -> None:
    t = await tenant(session, "acme")
    prompts: list[str] = []

    async def work(ctx: StepContext) -> dict:
        client = crustdata(ctx.recorder, ctx.cache, fail={"/job/search"})
        await client.search_companies(
            query="warehousing software India",
            filters={"field": "locations.country", "type": "=", "value": "IND"},
        )
        await client.enrich_company([11])
        await client.search_company_leadership(11, title_keywords=("founder", "cfo"))
        with pytest.raises(CrustdataError):
            await client.search_jobs(11)
        await client.web_search('"Alpha Freight" Pune facility')
        with activity_topic(ref={"type": "claim", "id": "c-1"}, source_class="news"):
            await client.fetch_pages(
                ["https://www.news.test/a?utm_source=x&id=7", "https://gone.test/x"]
            )
        model = llm(ctx.recorder, ctx.cache, prompts)
        with activity_topic(category="team_size", reading="document"):
            await model.extract_structured("Extract.", f"Deck says: {SECRET}", Headcount)
        return {}

    run = await run_one(session, sm, t, work)
    assert SECRET in prompts[0]  # the model saw the text; the stream never does
    events = await payloads(sm, run.id)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert [(e["kind"], (e["call"] or {}).get("endpoint")) for e in events] == [
        ("call", "company_search"),
        ("call", "company_enrich"),
        ("source", None),
        ("call", "person_search"),
        ("call", "job_search"),
        ("call", "web_search"),
        ("call", "web_fetch"),
        ("source", None),
        ("source", None),
        ("model", "messages"),
    ]
    search, enrich, record, people, jobs, web, fetch, page, failed, model = events

    # Fixed counts keys per endpoint (§2.4).
    assert search["counts"] == {"returned": 2, "new": 2, "total_available": 48}
    assert search["label"] == "Company search · 2 companies"
    assert search["detail"] is None  # a case run: never the query or the filters
    assert search["highlights"] == [
        "Alpha Freight (fixture) · Pune, India",
        "Beta Cold Chain (fixture)",
    ]
    assert enrich["counts"] == {
        "requested": 1, "returned": 1, "with_funding": 1, "funding_rounds": 1,
        "with_investors": 1, "with_headcount_series": 1, "with_web_traffic": 0,
    }  # fmt: skip
    assert enrich["highlights"] == ["Alpha Freight (fixture) · Series A · 2025-03"]
    assert enrich["call"]["credits"] == 2 and enrich["call"]["credits_total"] == pytest.approx(2.6)
    assert record["source"]["type"] == "crustdata_record"
    assert record["source"]["as_of"] == "2026-11-01"
    assert record["label"] == "Read the company record"  # case run: no name before identity
    assert people["counts"] == {"returned": 2, "current_leadership": 1}
    assert "Asha" not in json.dumps(events) and "Ravi" not in json.dumps(events)
    assert jobs["call"]["ok"] is False and jobs["call"]["error"] == "bad_request"
    assert jobs["label"] == "Job search did not return"
    assert web["counts"] == {"hits": 2, "news_hits": 1}
    assert fetch["counts"] == {"requested": 2, "read": 1, "failed": 1}

    # One source per page, tracking parameters stripped, the claim it was read for.
    assert page["label"] == "Read news.test"
    assert page["source"] == {
        "type": "web_page", "domain": "news.test", "url": "https://www.news.test/a?id=7",
        "title": "Alpha Freight opens a Pune hub", "source_class": "news", "as_of": None,
        "state": "read", "reason": None,
    }  # fmt: skip
    assert page["ref"] == {"type": "claim", "id": "c-1"}
    assert page["progress"] == {"done": 1, "total": 2}
    assert (failed["label"], failed["source"]["state"]) == ("Could not read gone.test", "failed")

    # The model event: counts and cost only, never the prompt or the reply.
    assert model["label"] == "Read the uploaded document for team size"
    assert model["call"]["provider"] == "anthropic" and model["call"]["usd"] > 0
    assert model["call"]["usd_total"] == pytest.approx(model["call"]["usd"])
    stored = json.dumps(events)
    for word in ("Falcon", "Zentrix", "crore", "250", "warehousing software", "IND"):
        assert word not in stored, word


async def test_discover_runs_name_the_users_filters(session, sm) -> None:
    t = await tenant(session, "acme")

    async def work(ctx: StepContext) -> dict:
        client = crustdata(ctx.recorder, ctx.cache)
        await client.search_companies(
            filters={"op": "and", "conditions": [
                {"field": "locations.country", "type": "=", "value": "India"},
                {"field": "taxonomy.categories", "type": "in", "value": ["warehousing"]},
            ]},
        )  # fmt: skip
        await client.search_companies(filters={"field": "x", "type": "=", "value": "India"})
        await client.enrich_company([11])
        return {}

    run = await run_one(session, sm, t, work, kind="discover", case=False)
    first, second, enrich, record = await payloads(sm, run.id)
    assert first["detail"] == "India · warehousing"
    assert second["counts"]["new"] == 0  # both companies were seen in the first pass
    assert record["label"] == "Read the record of Alpha Freight (fixture)"


async def test_cache_hits_are_marked(session, sm) -> None:
    t = await tenant(session, "acme")

    async def work(ctx: StepContext) -> dict:
        client = crustdata(ctx.recorder, ctx.cache)
        await client.web_search("Alpha Freight")
        await client.web_search("Alpha Freight")
        return {}

    run = await run_one(session, sm, t, work)
    first, second = await payloads(sm, run.id)
    assert first["call"]["from_cache"] is False and first["call"]["credits"] == 1
    assert second["call"]["from_cache"] is True and second["call"]["credits"] == 0
    assert second["call"]["credits_total"] == 1


async def test_set_detail_emits_status_at_most_once_a_second(session, sm, monkeypatch) -> None:
    monkeypatch.setattr(act, "STATUS_INTERVAL", 0.3)
    t = await tenant(session, "acme")

    async def work(ctx: StepContext) -> dict:
        await ctx.set_detail("Searching news about the company...")
        await ctx.set_detail("Reading 1 article")  # dropped: superseded within the window
        await ctx.set_detail("Reading 2 articles")  # the latest: sent when the window ends
        await asyncio.sleep(0.7)
        await ctx.activity.status(act.render("status.checking", category="funding"))
        await ctx.activity.status("Never sent")  # still waiting when the step ends
        return {}

    run = await run_one(session, sm, t, work)
    events = await payloads(sm, run.id)
    assert [(e["kind"], e["label"]) for e in events] == [
        ("status", "Searching news about the company"),
        ("status", "Reading 2 articles"),
        ("status", "Checking: funding"),
    ]
    assert events[0]["step_key"] == "work" and events[0]["detail"] is None


async def test_seq_is_gapless_and_ordered_across_concurrent_steps(session, sm) -> None:
    t = await tenant(session, "acme")
    reg = StepRegistry()
    gate = asyncio.Event()
    started = 0

    @reg.handler("chatty")
    async def chatty(ctx: StepContext) -> dict:
        nonlocal started
        started += 1
        if started == 2:
            gate.set()
        await gate.wait()
        await asyncio.gather(
            *(ctx.activity.notice(act.NoticeCode.SOURCE_LIMIT, n=i, total=99) for i in range(15))
        )
        return {}

    run = await create_run(
        session, workspace_id=t.workspace.id, kind="verify", case_id=t.case.id,
        steps=[StepSpec("a", "chatty"), StepSpec("b", "chatty")],
    )  # fmt: skip
    await session.commit()
    stop = asyncio.Event()
    task = asyncio.create_task(make_worker(sm, reg, concurrency=2).run(stop, purge=False))
    for _ in range(200):
        if set((await states(sm, run.id)).values()) == {"done"}:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await task
    events = await payloads(sm, run.id)
    assert [e["seq"] for e in events] == list(range(1, 31))
    assert sorted(e["step_key"] for e in events) == ["a"] * 15 + ["b"] * 15


async def test_a_lost_lease_writes_nothing(session, sm) -> None:
    t = await tenant(session, "acme")
    run = await create_run(
        session, workspace_id=t.workspace.id, kind="verify", case_id=t.case.id,
        steps=[StepSpec("a", "noop")],
    )  # fmt: skip
    await session.commit()
    step_id = (await session.execute(select(Step.id).where(Step.run_id == run.id))).scalar_one()
    token = uuid.uuid4()
    await session.execute(
        update(Step).where(Step.id == step_id).values(state="running", lease_token=token)
    )
    await session.commit()

    def emitter(lease_token):  # type: ignore[no-untyped-def]
        return act.ActivityEmitter(
            sm, workspace_id=t.workspace.id, run_id=run.id, step_id=step_id, step_key="a",
            lease_token=lease_token,
        )  # fmt: skip

    note = act.envelope(act.Kind.NOTICE, act.Label("x"), code=act.NoticeCode.STEP_RESUMED)
    assert await emitter(token).write([note]) == []  # no unexpired lease
    await session.execute(
        update(Step).where(Step.id == step_id).values(lease_until=func.now() + timedelta(hours=1))
    )
    await session.commit()
    assert await emitter(uuid.uuid4()).write([dict(note)]) == []  # another claim's token
    assert await emitter(token).write([dict(note)]) == [1]


async def test_a_resumed_step_says_so_and_replays_from_the_cache(session, sm) -> None:
    t = await tenant(session, "acme")
    reg = StepRegistry()
    tries = 0

    @reg.handler("flaky")
    async def flaky(ctx: StepContext) -> dict:
        nonlocal tries
        tries += 1
        await crustdata(ctx.recorder, ctx.cache).web_search("Alpha Freight")
        if tries == 1:
            raise RuntimeError("boom")
        return {}

    run = await create_run(
        session, workspace_id=t.workspace.id, kind="verify", case_id=t.case.id,
        steps=[StepSpec("a", "flaky")],
    )  # fmt: skip
    await session.commit()
    await make_worker(sm, reg).drain()
    events = await payloads(sm, run.id)
    assert [(e["kind"], e["code"]) for e in events] == [
        ("call", None),
        ("notice", "step_resumed"),
        ("call", None),
    ]
    assert events[2]["call"]["from_cache"] is True


def test_urls_titles_and_labels_are_sanitised() -> None:
    assert act.clean_url("https://news.test/a?utm_source=x&fbclid=1&id=7#top") == (
        "https://news.test/a?id=7"
    )
    assert act.clean_url("https://news.test/a?access_token=abc") is None
    assert act.clean_url("https://news.test/a?x=" + "A" * 40) is None
    assert act.clean_url("https://user:pw@news.test/a") is None
    assert act.clean_url("javascript:alert(1)") is None
    assert act.clean_domain("https://WWW.News.Test/a") == "news.test"
    assert act.clean_domain("not a domain") is None
    assert act.clean_title("Write to ceo@alpha.test now") == "Write to [redacted:email] now"
    assert len(act.clean_title("x" * 400)) == act.TITLE_MAX
    assert act.free_status("Reading 3 articles...") == "Reading 3 articles"
    with pytest.raises(ValueError):
        act.render("status.checking", category="We raised from Project Falcon")
    with pytest.raises(TypeError):
        act.envelope(act.Kind.STATUS, "a plain string")  # type: ignore[arg-type]
    seller = act.source_ref("seller_document", title="Seller document · PDF", url="https://x.test")
    assert seller["url"] is None and seller["domain"] is None


async def test_activity_page_summary_and_workspace_scope(session, sm) -> None:
    t = await tenant(session, "acme")
    other = await tenant(session, "other")
    run = await create_run(
        session, workspace_id=t.workspace.id, kind="verify", case_id=t.case.id, steps=[]
    )
    await session.commit()
    em = act.ActivityEmitter(sm, workspace_id=t.workspace.id, run_id=run.id, case_run=True)
    call = {
        "provider": "crustdata", "endpoint": "company_enrich", "ok": True, "error": None,
        "from_cache": False, "attempts": 1, "duration_ms": 10, "credits": 2, "usd": None,
        "credits_total": 0, "usd_total": 0,
    }  # fmt: skip
    E, L = act.envelope, act.Label
    read = act.source_ref("web_page", url="https://a.test/1")
    await em.write(
        [
            E(act.Kind.CALL, L("c"), call=call, counts={"requested": 5, "returned": 4}),
            E(act.Kind.SOURCE, L("s"), source=read),
            E(act.Kind.SOURCE, L("s"), source={**read, "domain": "b.test"}),
            E(act.Kind.SOURCE, L("s"), source={**read, "state": "failed"}),
            E(act.Kind.FINDING, L("f"), subject=act.Subject.COMPANY,
              items=[{"id": "1", "stage": "found", "name": "A"},
                     {"id": "2", "stage": "found", "name": "B"}]),
            E(act.Kind.FINDING, L("f"), subject=act.Subject.COMPANY,
              items=[{"id": "1", "stage": "scored", "name": "A", "fit": 80}]),
            E(act.Kind.FINDING, L("f"), subject=act.Subject.CLAIM,
              items=[{"id": "c1", "stage": "checking", "category": "funding"}]),
            E(act.Kind.FINDING, L("f"), subject=act.Subject.CLAIM,
              items=[{"id": "c1", "stage": "settled", "category": "funding",
                      "status": "supported"}]),
            E(act.Kind.FINDING, L("f"), subject=act.Subject.ROUND,
              items=[{"id": "r1", "stage": "found", "round": "Seed",
                      "investors": [{"key": "k1", "name": "Kite"}, {"key": "k2", "name": "Ash"}]}]),
        ]
    )  # fmt: skip
    ctx = CostContext(t.workspace.id, case_id=t.case.id, run_id=run.id)
    await record_cost(session, ctx, provider="crustdata", endpoint="/x", credits=3.5)
    await record_cost(session, ctx, provider="anthropic", endpoint="/y", usd=0.002)
    await session.commit()
    async with sm() as s:
        page = await load_activity_page(s, t.workspace.id, run.id, after=0, limit=4)
        assert [a.seq for a in page.items] == [1, 2, 3, 4] and page.next_after == 4
        rest = await load_activity_page(s, t.workspace.id, run.id, after=4)
        assert [a.seq for a in rest.items] == [5, 6, 7, 8, 9] and rest.next_after is None
        from app.db import repo

        with pytest.raises(repo.NotFound):
            await load_activity_page(s, other.workspace.id, run.id)
    summary = page.summary
    assert summary.by_kind == {"call": 1, "source": 3, "finding": 5}
    assert summary.crustdata_calls == 1 and summary.records_returned == 4
    assert (summary.sources_read, summary.sources_failed, summary.domains) == (2, 1, 2)
    assert summary.companies_found == 2
    assert summary.claims_settled == 1
    assert summary.investors_found == 2
    assert summary.credits == 3.5 and summary.llm_usd == pytest.approx(0.002)
    assert summary.last_seq == 9 and summary.elapsed_seconds >= 0
