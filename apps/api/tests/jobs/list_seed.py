"""A realistic workspace for the list endpoints: cases with runs, steps, call attempts,
cost entries, claims, assessments and DecisionFlip analyses. Used by the query-count
tests (`test_list_queries.py`) and by local profiling."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import CallAttempt, Claim, CostEntry, Run, Step
from app.jobs import StepSpec, create_run
from app.pipelines import evaluate
from app.pipelines.evaluate import flip as flip_service
from tests.db.factories import Tenant, discovery_run, tenant
from tests.evaluate.builders import (
    INDIA_MUST,
    SIZE_PREF,
    TODAY,
    World,
    check,
    field,
    source,
    thesis,
)

STEP_KEYS = ["identity", "profile", "funding", "people", "headcount", "news", "claims", "evaluate"]


@dataclass
class Seeded:
    t: Tenant
    case_ids: list[uuid.UUID]
    run_ids: list[uuid.UUID]


async def _run(
    session: AsyncSession, t: Tenant, *, case_id=None, discovery_run_id=None, state="done"
) -> Run:
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify" if case_id else "discover",
        case_id=case_id,
        discovery_run_id=discovery_run_id,
        steps=[StepSpec(k, "noop", label=k.capitalize()) for k in STEP_KEYS],
    )
    await session.flush()
    now = datetime.now(UTC)
    steps = list(
        (
            await session.execute(
                Step.__table__.select().where(Step.run_id == run.id).order_by(Step.position)
            )
        ).all()
    )
    for i, step in enumerate(steps):
        step_state = "done"
        if state == "running":
            step_state = "done" if i < 3 else ("running" if i == 3 else "pending")
        elif i == len(steps) - 2 and state == "done":
            step_state = "skipped_budget"
        await session.execute(
            update(Step)
            .where(Step.id == step.id)
            .values(
                state=step_state,
                started_at=now - timedelta(minutes=10 - i) if step_state != "pending" else None,
                finished_at=now - timedelta(minutes=9 - i) if step_state == "done" else None,
            )
        )
        owner = {"case_id": case_id} if case_id else {"discovery_run_id": discovery_run_id}
        for n in range(2):
            attempt = CallAttempt(
                call_id=uuid.uuid4().hex,
                workspace_id=t.workspace.id,
                run_id=run.id,
                step_id=step.id,
                provider="crustdata",
                endpoint="/company/enrich",
                status="started" if step_state == "running" and n else "succeeded",
                reserved_credits=Decimal(1),
                **owner,
            )
            session.add(attempt)
            await session.flush()
            if attempt.status == "succeeded":
                session.add(
                    CostEntry(
                        workspace_id=t.workspace.id,
                        run_id=run.id,
                        step_id=step.id,
                        call_attempt_id=attempt.id,
                        provider="crustdata",
                        endpoint="/company/enrich",
                        credits=Decimal("1.5"),
                        usd=Decimal("0.01"),
                        input_tokens=100,
                        output_tokens=20,
                        **owner,
                    )
                )
    await session.execute(
        update(Run)
        .where(Run.id == run.id)
        .values(state=state, finished_at=now if state == "done" else None)
    )
    await session.flush()
    return run


async def seed(session: AsyncSession, n_cases: int = 15) -> Seeded:
    """`n_cases` cases in one workspace, two runs each (one still running for every
    fifth case), claims with checks, and an assessment plus DecisionFlip for half."""
    t = await tenant(session, "lists")
    case_ids, run_ids = [], []
    for i in range(n_cases):
        if i == 0:
            case = t.case
            case.crustdata_company_id = "4242"
            case.identity_status = "confirmed"
        else:
            case = await repo.create_case(
                session,
                t.workspace.id,
                company_name=f"Company {i} (fixture)",
                created_by=t.user.id,
                crustdata_company_id="4242",
                identity_status="confirmed",
                website=f"https://company-{i}.test",
            )
        await session.flush()
        ct = Tenant(t.workspace, t.user, case)
        enrich = await source(session, ct, title="Company profile")
        await field(session, ct, enrich, "basic_info.name", case.company_name)
        await field(session, ct, enrich, "locations.country", "India")
        await field(session, ct, enrich, "basic_info.year_founded", 2014)
        profile = await source(
            session, ct, source_class="professional_profile_signal", title="Headcount estimate"
        )
        headcount = await field(session, ct, profile, "headcount.total", 180)
        await thesis(session, ct, [INDIA_MUST, SIZE_PREF])
        for n in range(3):
            claim = Claim(
                case_id=case.id,
                original_text=f"We have {250 + n} employees",
                origin="deck",
                category="team_size",
                components={"employee_count": str(250 + n)},
            )
            session.add(claim)
            await session.flush()
            await check(session, claim, "cannot_verify", [(headcount, "employee_count")])
        run_ids.append((await _run(session, ct, case_id=case.id)).id)
        later = await _run(session, ct, case_id=case.id, state="running" if i % 5 == 0 else "done")
        run_ids.append(later.id)
        await session.commit()
        if i % 2 == 0:
            out = await evaluate.evaluate_case(session, t.workspace.id, case.id, today=TODAY)
            await flip_service.flip_for_version(session, t.workspace.id, out.version)
            await session.commit()
        case_ids.append(case.id)
        _ = World(ct, claim)
    dr = await discovery_run(session, t)
    run_ids.append((await _run(session, t, discovery_run_id=dr.id)).id)
    await session.commit()
    return Seeded(t, case_ids, run_ids)
