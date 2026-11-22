from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import ledger
from app.db.adapters import DbCache, DbCallRecorder
from app.db.enums import CallStatus
from app.db.ledger import CostContext
from app.db.models import CallAttempt, CostEntry
from app.jobs import StepSpec, create_run
from tests.db.factories import days, discovery_run, tenant

pytestmark = pytest.mark.asyncio


class FakeCrustdata:
    """Stands in for app.clients: checks the cache, records the attempt, pays, caches."""

    def __init__(self) -> None:
        self.calls = 0

    async def enrich(self, company_id: str, *, cache: DbCache, recorder: DbCallRecorder) -> dict:
        key = f"crustdata:/company/enrich:{company_id}"
        hit = await cache.get(key)
        if hit is not None:
            return hit
        attempt = {
            "provider": "crustdata",
            "endpoint": "/company/enrich",
            "request_hash": key,
            "request": {"ids": [company_id]},
        }
        await recorder.before(attempt)
        self.calls += 1
        response = {"id": company_id, "headcount": 120}
        await recorder.after(attempt, {"credits_used": 2, "status_code": 200})
        await cache.set(key, response, provider="crustdata", endpoint="/company/enrich")
        return response


def adapters(sm: async_sessionmaker[AsyncSession], ctx: CostContext) -> dict:
    return {"cache": DbCache(sm, ctx), "recorder": DbCallRecorder(sm, ctx)}


async def test_case_reusing_discovery_data_is_not_double_counted(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    dr = await discovery_run(session, t)
    disc_run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="discover",
        discovery_run_id=dr.id,
        steps=[StepSpec("enrich", "noop")],
    )
    await session.commit()
    api = FakeCrustdata()

    disc_ctx = CostContext(t.workspace.id, discovery_run_id=dr.id, run_id=disc_run.id)
    await api.enrich("42", **adapters(sm, disc_ctx))
    case_ctx = CostContext(t.workspace.id, case_id=t.case.id)
    await api.enrich("42", **adapters(sm, case_ctx))
    await api.enrich("42", **adapters(sm, case_ctx))

    assert api.calls == 1
    disc = await ledger.discovery_run_totals(session, t.workspace.id, dr.id)
    case = await ledger.case_totals(session, t.workspace.id, t.case.id)
    total = await ledger.workspace_totals(session, t.workspace.id)
    assert disc.credits == Decimal("2")
    assert case.credits == Decimal("0")
    assert case.cached_calls == 2
    assert case.shared_from_run_ids == [disc_run.id]
    assert total.credits == Decimal("2")


async def test_replay_within_the_same_owner_records_nothing(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    ctx = CostContext(t.workspace.id, case_id=t.case.id)
    api = FakeCrustdata()
    await api.enrich("7", **adapters(sm, ctx))
    await api.enrich("7", **adapters(sm, ctx))
    totals = await ledger.case_totals(session, t.workspace.id, t.case.id)
    assert (api.calls, totals.calls, totals.credits) == (1, 1, Decimal("2"))


async def test_unknown_cost_is_flagged_and_tokens_and_usd_summed(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    rec = DbCallRecorder(sm, CostContext(t.workspace.id, case_id=t.case.id))
    llm = {"provider": "anthropic", "endpoint": "messages"}
    await rec("before", llm)
    await rec("after", llm, {"input_tokens": 1000, "output_tokens": 200, "usd": "0.0002"})
    web = {"provider": "crustdata", "endpoint": "/web/search/live"}
    await rec(web)
    await rec(web, {"unknown": True})
    totals = await ledger.case_totals(session, t.workspace.id, t.case.id)
    assert totals.input_tokens == 1000 and totals.output_tokens == 200
    assert totals.usd == Decimal("0.0002")
    assert totals.unknown_calls == 1 and totals.is_lower_bound


async def test_attempt_is_persisted_before_the_call(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    rec = DbCallRecorder(sm, CostContext(t.workspace.id, case_id=t.case.id))
    attempt_id = await rec.before({"provider": "crustdata", "endpoint": "/company/identify"})
    # The process "crashes" here: no after(). The attempt is already committed.
    row = await session.get(CallAttempt, attempt_id)
    assert row is not None and row.status == CallStatus.STARTED
    assert (await session.execute(select(CostEntry))).first() is None


async def test_cost_context_needs_exactly_one_owner(session: AsyncSession) -> None:
    t = await tenant(session)
    with pytest.raises(ValueError):
        CostContext(t.workspace.id)
    dr = await discovery_run(session, t)
    with pytest.raises(ValueError):
        CostContext(t.workspace.id, case_id=t.case.id, discovery_run_id=dr.id)
    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO cost_entries (id, workspace_id, case_id, discovery_run_id, provider,"
                " endpoint, credits, input_tokens, output_tokens, usd, unknown, cached)"
                " VALUES (gen_random_uuid(), :ws, :case, :dr, 'x', 'y', 1, 0, 0, 0, false, false)"
            ),
            {"ws": t.workspace.id, "case": t.case.id, "dr": dr.id},
        )


async def test_confidential_cache_is_scoped_to_its_case(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    from app.db import repo

    other = await repo.create_case(session, t.workspace.id, company_name="other (fixture)")
    await session.commit()
    mine = DbCache(
        sm, CostContext(t.workspace.id, case_id=t.case.id), confidential=True, delete_after=days(30)
    )
    theirs = DbCache(
        sm, CostContext(t.workspace.id, case_id=other.id), confidential=True, delete_after=days(30)
    )
    public = DbCache(sm, CostContext(t.workspace.id, case_id=other.id))
    await mine.set("llm:claims:deck-hash", {"claims": ["250 staff"]})
    assert await mine.get("llm:claims:deck-hash") == {"claims": ["250 staff"]}
    assert await theirs.get("llm:claims:deck-hash") is None
    assert await public.get("llm:claims:deck-hash") is None
    with pytest.raises(ValueError):
        DbCache(sm, CostContext(t.workspace.id, case_id=t.case.id), confidential=True)
