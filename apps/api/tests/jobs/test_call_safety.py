"""Regression tests for paid-call safety: confidential cache scope, per-dispatch
accounting, crash reconciliation, lock-serialised misses, atomic budgets, owner
validation and error sanitising."""

import asyncio
import json
import uuid
from decimal import Decimal

import httpx2
import pytest
from anthropic import AsyncAnthropic
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.clients import CrustdataClient, LLMClient, SlidingWindowRateLimiter
from app.clients.base import CallRecord
from app.db import ledger, repo
from app.db.adapters import DbCache, DbCallRecorder
from app.db.ledger import CostContext
from app.db.models import ApiCache, CallAttempt, CostEntry, Document, Run, Step
from app.jobs import StepContext, StepRegistry, StepSpec, create_run
from app.jobs.events import load_run_out
from tests.db.factories import IDENTIFY_BODY, days, discovery_run, tenant
from tests.jobs.helpers import make_worker, states

pytestmark = pytest.mark.asyncio


class Crash(BaseException):
    """A worker dying mid-request (not an Exception, so nothing catches it)."""


class Api:
    """A real CrustdataClient over a scripted, optionally slow, mock transport."""

    def __init__(self, *script, credits: str = "0.2", delay: float = 0.0) -> None:
        self.script = list(script)
        self.credits = credits
        self.delay = delay
        self.http_calls = 0

    def client(self, recorder, cache) -> CrustdataClient:  # type: ignore[no-untyped-def]
        async def handle(request: httpx2.Request) -> httpx2.Response:
            self.http_calls += 1
            n = self.http_calls
            if self.delay:
                await asyncio.sleep(self.delay)
            item = self.script.pop(0) if self.script else None
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, httpx2.Response):
                return item
            body = IDENTIFY_BODY
            if request.url.path == "/company/enrich":
                body = [{"matches": [{"company_data": {"crustdata_company_id": 1}}]}]
            return httpx2.Response(
                200, json=body, headers={"x-credits-used": self.credits, "x-request-id": f"r{n}"}
            )

        async def no_sleep(_: float) -> None:
            return None

        return CrustdataClient(
            "test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
            recorder=recorder,
            cache=cache,
            rate_limiter=SlidingWindowRateLimiter({}),
            sleep=no_sleep,
            max_retries=2,
        )


def llm(recorder, cache, calls: list) -> LLMClient:  # type: ignore[no-untyped-def]
    def handle(request: httpx2.Request) -> httpx2.Response:
        calls.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": "Claims: 250 staff"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            headers={"request-id": "req_llm"},
        )

    sdk = AsyncAnthropic(
        api_key="k",
        base_url="https://anthropic.test",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    return LLMClient(client=sdk, recorder=recorder, cache=cache)


async def step_ctx(session, t, key: str = "a") -> CostContext:  # type: ignore[no-untyped-def]
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec(key, "noop")],
    )
    await session.commit()
    step_id = (await session.execute(select(Step.id).where(Step.run_id == run.id))).scalar_one()
    return CostContext(t.workspace.id, case_id=t.case.id, run_id=run.id, step_id=step_id)


async def attempts(sm, **where):  # type: ignore[no-untyped-def]
    async with sm() as s:
        stmt = select(CallAttempt).order_by(CallAttempt.created_at)
        for k, v in where.items():
            stmt = stmt.where(getattr(CallAttempt, k) == v)
        return list((await s.execute(stmt)).scalars())


# --- 1. Confidential cache scope ---------------------------------------------------


async def test_confidential_llm_reply_is_not_replayed_to_another_case(session, sm) -> None:
    t = await tenant(session)
    other = await repo.create_case(session, t.workspace.id, company_name="other (fixture)")
    await session.commit()
    calls: list = []
    ctx_a = CostContext(t.workspace.id, case_id=t.case.id)
    ctx_b = CostContext(t.workspace.id, case_id=other.id)
    # What the worker hands a step: a workspace-scoped cache.
    a = llm(DbCallRecorder(sm, ctx_a), DbCache(sm, ctx_a), calls)
    b = llm(DbCallRecorder(sm, ctx_b), DbCache(sm, ctx_b), calls)

    await a.draft_text("Extract claims.", "deck text: 250 staff")
    _, again = await a.draft_text("Extract claims.", "deck text: 250 staff")
    assert again.status == "cache_hit" and len(calls) == 1
    _, record = await b.draft_text("Extract claims.", "deck text: 250 staff")
    assert record.status == "succeeded" and len(calls) == 2  # case B paid; no replay

    async with sm() as s:
        rows = list((await s.execute(select(ApiCache))).scalars())
    assert {r.case_id for r in rows} == {t.case.id, other.id}
    assert all(r.confidential and r.delete_after is not None for r in rows)
    assert all(r.cache_key.startswith("case:") for r in rows)


async def test_public_llm_requests_opt_in_to_the_workspace_cache(session, sm) -> None:
    t = await tenant(session)
    other = await repo.create_case(session, t.workspace.id, company_name="other (fixture)")
    await session.commit()
    calls: list = []
    ctx_a = CostContext(t.workspace.id, case_id=t.case.id)
    ctx_b = CostContext(t.workspace.id, case_id=other.id)
    await llm(DbCallRecorder(sm, ctx_a), DbCache(sm, ctx_a), calls).draft_text(
        "Summarise.", "public filing text", public=True
    )
    _, record = await llm(DbCallRecorder(sm, ctx_b), DbCache(sm, ctx_b), calls).draft_text(
        "Summarise.", "public filing text", public=True
    )
    assert record.status == "cache_hit" and len(calls) == 1


async def test_expired_cache_entries_are_never_served(session, sm) -> None:
    t = await tenant(session)
    ctx = CostContext(t.workspace.id, case_id=t.case.id)
    cache = DbCache(sm, ctx).confidential()
    await cache.set("k", {"v": 1})
    assert await cache.get("k") == {"v": 1}
    async with sm() as s:
        await s.execute(update(ApiCache).values(delete_after=days(-1)))
        await s.commit()
    assert await cache.get("k") is None  # rejected on read, before any purge


async def test_confidential_cache_never_outlives_the_case_documents(session, sm) -> None:
    t = await tenant(session)
    session.add(
        Document(
            case_id=t.case.id,
            filename="deck.pdf",
            mime="application/pdf",
            gcs_path="cases/x/deck.pdf",
            delete_after=days(3),
        )
    )
    await session.commit()
    cache = DbCache(sm, CostContext(t.workspace.id, case_id=t.case.id)).confidential()
    await cache.set("k", {"v": 1})
    async with sm() as s:
        row = (await s.execute(select(ApiCache))).scalar_one()
    assert row.delete_after <= days(3.01)


# --- 2. Per-dispatch accounting ----------------------------------------------------


async def test_each_dispatch_gets_its_own_attempt_and_ledger_row(session, sm) -> None:
    t = await tenant(session)
    ctx = await step_ctx(session, t)
    api = Api(httpx2.Response(503, headers={"x-credits-used": "0.1", "x-request-id": "r-503"}))
    await api.client(DbCallRecorder(sm, ctx), DbCache(sm, ctx)).identify_company(
        domains=["example-logistics.test"]
    )
    rows = await attempts(sm)
    assert [(r.dispatch_index, r.status, r.provider_request_id) for r in rows] == [
        (0, "failed", "r-503"),
        (1, "succeeded", "r2"),
    ]
    assert len({r.operation_key for r in rows}) == 1 and rows[0].operation_key
    async with sm() as s:
        totals = await ledger.case_totals(s, t.workspace.id, t.case.id)
    assert totals.calls == 2 and totals.credits == Decimal("0.3") and totals.unknown_calls == 0


async def test_unknown_dispatch_keeps_the_known_credit_subtotal(session, sm) -> None:
    t = await tenant(session)
    ctx = await step_ctx(session, t)
    api = Api(
        httpx2.Response(500, headers={"x-credits-used": "0.1"}),
        httpx2.ReadTimeout("slow"),
    )
    with pytest.raises(Exception):  # noqa: B017 - CrustdataError
        await api.client(DbCallRecorder(sm, ctx), DbCache(sm, ctx)).identify_company(
            domains=["example-logistics.test"]
        )
    assert api.http_calls == 2  # not retried after the ambiguous timeout
    async with sm() as s:
        totals = await ledger.case_totals(s, t.workspace.id, t.case.id)
    assert totals.credits == Decimal("0.1")
    assert totals.unknown_calls == 1
    async with sm() as s:
        entries = list(
            (await s.execute(select(CostEntry).order_by(CostEntry.created_at))).scalars()
        )
    assert [(e.credits, e.unknown) for e in entries] == [(Decimal("0.1"), False), (0, True)]


async def test_provider_error_text_is_never_stored(session, sm) -> None:
    t = await tenant(session)
    ctx = CostContext(t.workspace.id, case_id=t.case.id)
    record = CallRecord(
        provider="crustdata", endpoint="/x", params_hash="h", cache_key="k", status="failed"
    )
    record.error = "HTTP 400: founder jane@acme.test not found"
    await DbCallRecorder(sm, ctx)(record)
    (row,) = await attempts(sm)
    assert row.error == "other"


# --- 3. Crash safety ---------------------------------------------------------------


async def test_crashed_attempt_is_reconciled_as_unknown_on_resume(session, sm) -> None:
    t = await tenant(session)
    ctx = await step_ctx(session, t)
    api = Api(Crash())
    with pytest.raises(Crash):
        await api.client(DbCallRecorder(sm, ctx), DbCache(sm, ctx)).identify_company(
            domains=["example-logistics.test"]
        )
    (left,) = await attempts(sm)
    assert left.status == "started"
    async with sm() as s:
        totals = await ledger.case_totals(s, t.workspace.id, t.case.id)
    assert totals.unknown_calls == 1  # unresolved counts as unknown cost
    run_out = await load_run_out(session, t.workspace.id, ctx.run_id)
    assert run_out.cost.unknown_cost_calls == 1

    # The resumed step (new recorder, same step) computes the same operation key.
    await api.client(DbCallRecorder(sm, ctx), DbCache(sm, ctx)).identify_company(
        domains=["example-logistics.test"]
    )
    rows = await attempts(sm)
    assert [r.status for r in rows] == ["unknown", "succeeded"]
    assert rows[0].operation_key == rows[1].operation_key
    async with sm() as s:
        totals = await ledger.case_totals(s, t.workspace.id, t.case.id)
    assert totals.unknown_calls == 1 and totals.credits == Decimal("0.2")


async def test_resume_does_not_repay_when_the_cache_already_has_the_answer(session, sm) -> None:
    t = await tenant(session)
    ctx1 = await step_ctx(session, t, "one")
    ctx2 = await step_ctx(session, t, "two")
    api = Api(Crash())
    with pytest.raises(Crash):
        await api.client(DbCallRecorder(sm, ctx1), DbCache(sm, ctx1)).identify_company(
            domains=["example-logistics.test"]
        )
    # Another step pays for the same public lookup and caches it.
    await api.client(DbCallRecorder(sm, ctx2), DbCache(sm, ctx2)).identify_company(
        domains=["example-logistics.test"]
    )
    _, record = await api.client(DbCallRecorder(sm, ctx1), DbCache(sm, ctx1)).identify_company(
        domains=["example-logistics.test"]
    )
    assert record.from_cache and api.http_calls == 2
    statuses = sorted(r.status for r in await attempts(sm))
    assert statuses == ["cache_hit", "succeeded", "unknown"]


async def test_cache_write_and_final_usage_commit_together(session, sm, monkeypatch) -> None:
    t = await tenant(session)
    ctx = await step_ctx(session, t)

    def broken(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("cache insert failed")

    cache = DbCache(sm, ctx)
    monkeypatch.setattr(cache, "insert_statement", broken)
    with pytest.raises(RuntimeError):
        await (
            Api()
            .client(DbCallRecorder(sm, ctx), cache)
            .identify_company(domains=["example-logistics.test"])
        )
    (row,) = await attempts(sm)
    assert row.status == "started"  # neither the usage nor the cache entry landed
    async with sm() as s:
        assert (await s.execute(select(CostEntry))).first() is None
        assert (await s.execute(select(ApiCache))).first() is None


async def test_concurrent_misses_on_one_key_pay_once(session, sm) -> None:
    t = await tenant(session)
    ctx1 = await step_ctx(session, t, "one")
    ctx2 = await step_ctx(session, t, "two")
    api = Api(delay=0.3)
    results = await asyncio.gather(
        api.client(DbCallRecorder(sm, ctx1), DbCache(sm, ctx1)).identify_company(
            domains=["example-logistics.test"]
        ),
        api.client(DbCallRecorder(sm, ctx2), DbCache(sm, ctx2)).identify_company(
            domains=["example-logistics.test"]
        ),
    )
    assert api.http_calls == 1
    assert sorted(r[1].status for r in results) == ["cache_hit", "succeeded"]


# --- 5. Atomic budget --------------------------------------------------------------


async def test_concurrent_steps_cannot_overspend_the_case_budget(session, sm) -> None:
    t = await tenant(session, credit_budget=5)
    reg = StepRegistry()
    api = Api(credits="2", delay=0.2)

    @reg.handler("enrich")
    async def enrich(ctx: StepContext) -> dict:
        # Each step passes the (non-atomic) pre-check: 5 credits look free to all four.
        await ctx.require_budget(2)
        await api.client(ctx.recorder, ctx.cache).enrich_company(int(ctx.input["id"]))
        return {}

    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec(f"s{i}", "enrich", input={"id": i}) for i in range(4)],
    )
    await session.commit()
    workers = [make_worker(sm, reg) for _ in range(4)]
    await asyncio.gather(*(w.run_once() for w in workers))
    assert api.http_calls == 2  # 2 + 2 reserved; a third 2-credit dispatch would exceed 5
    async with sm() as s:
        totals = await ledger.case_totals(s, t.workspace.id, t.case.id)
    assert totals.credits == Decimal(4)
    assert sorted((await states(sm, run.id)).values()) == [
        "done",
        "done",
        "skipped_budget",
        "skipped_budget",
    ]


async def test_unknown_cost_holds_its_reservation(session, sm) -> None:
    t = await tenant(session, credit_budget=3)
    ctx = await step_ctx(session, t)
    api = Api(httpx2.ReadTimeout("slow"))
    with pytest.raises(Exception):  # noqa: B017
        await api.client(DbCallRecorder(sm, ctx), None).enrich_company(1)
    async with sm() as s:
        used = await ledger.budget_used(s, ctx)
    assert used == Decimal(2)  # the 2-credit estimate, not zero


# --- 6. Owner validation -----------------------------------------------------------


async def test_create_run_rejects_owners_from_another_workspace(session) -> None:
    mine = await tenant(session, "mine")
    theirs = await tenant(session, "theirs")
    their_dr = await discovery_run(session, theirs)
    for owner in ({"case_id": theirs.case.id}, {"discovery_run_id": their_dr.id}):
        with pytest.raises(LookupError):
            await create_run(
                session,
                workspace_id=mine.workspace.id,
                kind="verify",
                steps=[StepSpec("a", "noop")],
                budget_credits=10,  # an explicit budget must not skip the check
                **owner,
            )
        await session.rollback()


async def test_database_rejects_a_cross_workspace_owner(session) -> None:
    mine = await tenant(session, "mine")
    theirs = await tenant(session, "theirs")
    my_ws, their_case = mine.workspace.id, theirs.case.id
    session.add(Run(workspace_id=my_ws, kind="verify", case_id=their_case))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    session.add(CostEntry(workspace_id=my_ws, case_id=their_case, provider="c", endpoint="/x"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_run_serializer_is_scoped_to_the_workspace(session) -> None:
    mine = await tenant(session, "mine")
    theirs = await tenant(session, "theirs")
    run = await create_run(
        session,
        workspace_id=theirs.workspace.id,
        kind="verify",
        case_id=theirs.case.id,
        steps=[StepSpec("a", "noop")],
    )
    await session.commit()
    with pytest.raises(repo.NotFound):
        await load_run_out(session, mine.workspace.id, run.id)
    assert (await load_run_out(session, theirs.workspace.id, run.id)).subject


async def test_unknown_owner_ids_are_rejected(session) -> None:
    t = await tenant(session)
    with pytest.raises(LookupError):
        await create_run(
            session,
            workspace_id=t.workspace.id,
            kind="verify",
            investor_run_id=uuid.uuid4(),
            steps=[StepSpec("a", "noop")],
        )
