"""What a case cost, as the memo says it.

The readout itself is CP-19's `cost` section (`app.api.cases_sections`): the case's own
Crustdata credits and model dollars, never added together, with the discovery run's
cost shown once as shared and not added (each case opened from one shortlist would
otherwise count it again). This module adds what it cannot see in `cost_entries`:
calls that started and never reported a cost are unknown, never zero.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.cases import CaseCostOut
from app.db.enums import CallStatus
from app.db.models import CallAttempt, Case, CostEntry


async def unrecorded_calls(session: AsyncSession, case: Case) -> int:
    """Calls that started for this case but never reported a cost (lost or in flight)."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(CallAttempt)
            .outerjoin(CostEntry, CostEntry.call_attempt_id == CallAttempt.id)
            .where(
                CallAttempt.case_id == case.id,
                CallAttempt.status == CallStatus.STARTED,
                CostEntry.id.is_(None),
            )
        )
        or 0
    )


def cost_line(cost: CaseCostOut) -> str:
    """The memo summary's cost sentence; unknown costs are said, never hidden."""
    text = (
        f"{cost.crustdata_credits:g} of {cost.credit_budget:g} Crustdata credits · "
        f"${cost.llm_usd:.2f} model usage"
    )
    if cost.unknown_cost_calls:
        text += f" + {cost.unknown_cost_calls} call(s) of unknown cost"
    if cost.shared_discovery is not None:
        shared = cost.shared_discovery.cost
        text += (
            f" · discovery shared from run {cost.shared_discovery.run_id}: "
            f"{shared.crustdata_credits:g} credits, ${shared.llm_usd:.2f} (not added)"
        )
    return text
