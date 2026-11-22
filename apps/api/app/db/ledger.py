"""Cost ledger: who paid for what, without counting any spend twice.

Each `cost_entries` row is charged to exactly one owner: a case, a discovery run or an
investor run (`CostContext` carries that owner). When one owner reuses a cached
response another run paid for, the reuse is recorded with zero cost and a
`shared_from_run_id` link, so a case page can say "data shared from discovery run X"
while workspace totals add up each credit once.
"""

import uuid
from dataclasses import dataclass, field, replace
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Case, CostEntry


@dataclass(frozen=True)
class CostContext:
    """Who a call is charged to, plus the run/step it happened in."""

    workspace_id: uuid.UUID
    case_id: uuid.UUID | None = None
    discovery_run_id: uuid.UUID | None = None
    investor_run_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    step_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        owners = [self.case_id, self.discovery_run_id, self.investor_run_id]
        if sum(o is not None for o in owners) != 1:
            raise ValueError(
                "CostContext needs exactly one owner: case_id, discovery_run_id or investor_run_id"
            )

    @property
    def owner(self) -> tuple[str, uuid.UUID]:
        if self.case_id is not None:
            return ("case", self.case_id)
        if self.discovery_run_id is not None:
            return ("discovery_run", self.discovery_run_id)
        assert self.investor_run_id is not None
        return ("investor_run", self.investor_run_id)

    def for_step(self, run_id: uuid.UUID, step_id: uuid.UUID | None) -> "CostContext":
        return replace(self, run_id=run_id, step_id=step_id)


def _dec(value: object) -> Decimal:
    if value is None:
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


async def record_cost(
    session: AsyncSession,
    ctx: CostContext,
    *,
    provider: str,
    endpoint: str,
    credits: Decimal | float | int | None = 0,
    input_tokens: int | None = 0,
    output_tokens: int | None = 0,
    usd: Decimal | float | int | None = 0,
    unknown: bool = False,
    cached: bool = False,
    call_attempt_id: uuid.UUID | None = None,
    shared_from_run_id: uuid.UUID | None = None,
) -> CostEntry:
    entry = CostEntry(
        workspace_id=ctx.workspace_id,
        case_id=ctx.case_id,
        discovery_run_id=ctx.discovery_run_id,
        investor_run_id=ctx.investor_run_id,
        run_id=ctx.run_id,
        step_id=ctx.step_id,
        call_attempt_id=call_attempt_id,
        provider=provider,
        endpoint=endpoint,
        credits=_dec(credits),
        input_tokens=input_tokens or 0,
        output_tokens=output_tokens or 0,
        usd=_dec(usd),
        unknown=unknown,
        cached=cached,
        shared_from_run_id=shared_from_run_id,
    )
    session.add(entry)
    await session.flush()
    return entry


@dataclass
class CostTotals:
    credits: Decimal = Decimal(0)
    usd: Decimal = Decimal(0)
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cached_calls: int = 0
    # Calls whose cost the provider did not report; totals are then a lower bound.
    unknown_calls: int = 0
    shared_from_run_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def is_lower_bound(self) -> bool:
        return self.unknown_calls > 0


async def _totals(session: AsyncSession, stmt_filter: Select) -> CostTotals:
    stmt = stmt_filter.with_only_columns(
        func.coalesce(func.sum(CostEntry.credits), 0),
        func.coalesce(func.sum(CostEntry.usd), 0),
        func.coalesce(func.sum(CostEntry.input_tokens), 0),
        func.coalesce(func.sum(CostEntry.output_tokens), 0),
        func.count(CostEntry.id),
        func.count(case((CostEntry.cached, 1))),
        func.count(case((CostEntry.unknown, 1))),
        func.array_remove(func.array_agg(CostEntry.shared_from_run_id.distinct()), None),
    )
    row = (await session.execute(stmt)).one()
    return CostTotals(
        credits=_dec(row[0]),
        usd=_dec(row[1]),
        input_tokens=int(row[2]),
        output_tokens=int(row[3]),
        calls=int(row[4]),
        cached_calls=int(row[5]),
        unknown_calls=int(row[6]),
        shared_from_run_ids=list(row[7] or []),
    )


async def case_totals(
    session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID
) -> CostTotals:
    """What this case cost. Data reused from discovery is listed, not re-counted."""
    stmt = (
        select(CostEntry)
        .join(Case, Case.id == CostEntry.case_id)
        .where(CostEntry.case_id == case_id, Case.workspace_id == workspace_id)
    )
    return await _totals(session, stmt)


async def discovery_run_totals(
    session: AsyncSession, workspace_id: uuid.UUID, discovery_run_id: uuid.UUID
) -> CostTotals:
    stmt = select(CostEntry).where(
        CostEntry.discovery_run_id == discovery_run_id, CostEntry.workspace_id == workspace_id
    )
    return await _totals(session, stmt)


async def investor_run_totals(
    session: AsyncSession, workspace_id: uuid.UUID, investor_run_id: uuid.UUID
) -> CostTotals:
    stmt = select(CostEntry).where(
        CostEntry.investor_run_id == investor_run_id, CostEntry.workspace_id == workspace_id
    )
    return await _totals(session, stmt)


async def workspace_totals(session: AsyncSession, workspace_id: uuid.UUID) -> CostTotals:
    stmt = select(CostEntry).where(CostEntry.workspace_id == workspace_id)
    return await _totals(session, stmt)


async def spent_credits(
    session: AsyncSession,
    *,
    case_id: uuid.UUID | None = None,
    discovery_run_id: uuid.UUID | None = None,
    investor_run_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
) -> Decimal:
    """Credits spent by one owner (or one run when no owner is given)."""
    stmt = select(func.coalesce(func.sum(CostEntry.credits), 0))
    if case_id is not None:
        stmt = stmt.where(CostEntry.case_id == case_id)
    elif discovery_run_id is not None:
        stmt = stmt.where(CostEntry.discovery_run_id == discovery_run_id)
    elif investor_run_id is not None:
        stmt = stmt.where(CostEntry.investor_run_id == investor_run_id)
    elif run_id is not None:
        stmt = stmt.where(CostEntry.run_id == run_id)
    else:
        raise ValueError("spent_credits needs an owner or a run id")
    return _dec((await session.execute(stmt)).scalar_one())
