from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.base import CallRecord
from app.db import ledger
from app.db.adapters import DbCache, DbCallRecorder
from app.db.enums import CallStatus
from app.db.ledger import CostContext
from app.db.models import CallAttempt, CostEntry
from app.jobs import StepSpec, create_run
from tests.db.factories import FakeCrustdataApi, days, discovery_run, tenant

pytestmark = pytest.mark.asyncio


async def identify(api: FakeCrustdataApi, sm, ctx: CostContext):  # type: ignore[no-untyped-def]
    client = api.client(recorder=DbCallRecorder(sm, ctx), cache=DbCache(sm, ctx))
    results, record = await client.identify_company(domains=["example-logistics.test"])
    return results, record


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
    api = FakeCrustdataApi(credits="0.2")

    disc_ctx = CostContext(t.workspace.id, discovery_run_id=dr.id, run_id=disc_run.id)
    await identify(api, sm, disc_ctx)
    case_ctx = CostContext(t.workspace.id, case_id=t.case.id)
    _, record = await identify(api, sm, case_ctx)
    await identify(api, sm, case_ctx)

    assert api.http_calls == 1 and record.status == "cache_hit"
    disc = await ledger.discovery_run_totals(session, t.workspace.id, dr.id)
    case = await ledger.case_totals(session, t.workspace.id, t.case.id)
    total = await ledger.workspace_totals(session, t.workspace.id)
    assert disc.credits == Decimal("0.2")
    assert case.credits == Decimal("0")
    assert case.cached_calls == 2
    assert case.shared_from_run_ids == [disc_run.id]
    assert total.credits == Decimal("0.2")
    statuses = (await session.execute(select(CallAttempt.status))).scalars().all()
    assert sorted(statuses) == ["cache_hit", "cache_hit", "succeeded"]


async def test_cache_is_not_shared_across_workspaces(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    api = FakeCrustdataApi()
    await identify(api, sm, CostContext(a.workspace.id, case_id=a.case.id))
    await identify(api, sm, CostContext(b.workspace.id, case_id=b.case.id))
    assert api.http_calls == 2
    totals = await ledger.case_totals(session, b.workspace.id, b.case.id)
    assert totals.shared_from_run_ids == [] and totals.credits == Decimal("0.2")


async def test_replay_within_the_same_owner_records_nothing(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    ctx = CostContext(t.workspace.id, case_id=t.case.id)
    api = FakeCrustdataApi()
    await identify(api, sm, ctx)
    await identify(api, sm, ctx)
    totals = await ledger.case_totals(session, t.workspace.id, t.case.id)
    assert (api.http_calls, totals.calls, totals.credits) == (1, 1, Decimal("0.2"))


async def test_unknown_cost_is_flagged_and_tokens_and_usd_summed(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    rec = DbCallRecorder(sm, CostContext(t.workspace.id, case_id=t.case.id))
    llm = CallRecord(provider="anthropic", endpoint="messages", params_hash="p", cache_key="k1")
    await rec(llm)
    llm.status, llm.input_tokens, llm.output_tokens = "succeeded", 1000, 200
    llm.cost_usd, llm.usage_known = 0.0002, True
    await rec(llm)
    await rec(llm)  # a repeated final report is not counted twice
    api = FakeCrustdataApi(credits=None)  # no X-Credits-Used header: cost unknown
    await identify(api, sm, CostContext(t.workspace.id, case_id=t.case.id))
    totals = await ledger.case_totals(session, t.workspace.id, t.case.id)
    assert totals.calls == 2
    assert totals.input_tokens == 1000 and totals.output_tokens == 200
    assert totals.usd == Decimal("0.0002")
    assert totals.unknown_calls == 1 and totals.is_lower_bound


async def test_attempt_is_persisted_before_the_call(
    session: AsyncSession, sm: async_sessionmaker[AsyncSession]
) -> None:
    t = await tenant(session)
    rec = DbCallRecorder(sm, CostContext(t.workspace.id, case_id=t.case.id))
    started = CallRecord(
        provider="crustdata", endpoint="/company/identify", params_hash="p", cache_key="k"
    )
    await rec(started)
    # The process "crashes" here: no final report. The attempt is already committed.
    row = (
        await session.execute(select(CallAttempt).where(CallAttempt.call_id == started.call_id))
    ).scalar_one()
    assert row.status == CallStatus.STARTED
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
    dr = await discovery_run(session, t)
    with pytest.raises(ValueError):
        DbCache(sm, CostContext(t.workspace.id, discovery_run_id=dr.id), confidential=True)
    assert DbCache(sm, CostContext(t.workspace.id, discovery_run_id=dr.id)).confidential() is None
