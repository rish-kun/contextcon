"""Case writes for the routes in `app.api.cases`: open a case, record a manual identity
pick, start a verify run. Every query is scoped to the actor's workspace."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cases_deps import CaseActor
from app.api.schemas.cases import CaseCreate, IdentityPickIn
from app.db import repo
from app.db.enums import IdentityStatus, RunKind
from app.db.models import Candidate, Case, DiscoveryRun, Run, Step
from app.jobs import StepSpec, append_steps, create_run
from app.pipelines.verify.claims.intake import schedule_case_checks
from app.pipelines.verify.common import IDENTITY, normalize_domain
from app.pipelines.verify.identity import (
    CORROBORATING_KEYS,
    apply_confirmation,
    dependent_steps,
    record_key_evidence,
)
from app.pipelines.verify.tail import ensure_assessment_tail
from app.settings import get_settings


def _uuid(value: str | None, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.") from None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def identity_step() -> StepSpec:
    return StepSpec(IDENTITY, IDENTITY, label="Confirm which company this is")


async def _shortlist_candidate(
    session: AsyncSession, actor: CaseActor, item_id: str
) -> tuple[Candidate, DiscoveryRun]:
    row = (
        await session.execute(
            select(Candidate, DiscoveryRun)
            .join(DiscoveryRun, DiscoveryRun.id == Candidate.discovery_run_id)
            .where(
                Candidate.id == _uuid(item_id, "Shortlist item"),
                DiscoveryRun.workspace_id == actor.workspace_id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shortlist item not found.")
    return row[0], row[1]


async def create_case(session: AsyncSession, actor: CaseActor, body: CaseCreate) -> Case:
    """Open a case and enqueue its verify run (identity first; the rest follows a
    confirmed identity)."""
    expected: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    if body.shortlist_item_id is not None:
        candidate, discovery = await _shortlist_candidate(session, actor, body.shortlist_item_id)
        card = candidate.card or {}
        name, website = candidate.name, candidate.domain
        expected = {
            "crustdata_company_id": _int(candidate.crustdata_company_id),
            "founded_year": _int(card.get("year_founded") or card.get("founded_year")),
            "profile_url": card.get("professional_network_url") or card.get("profile_url"),
        }
        # Linked so the discovery cost shows as "shared from run X", never re-counted.
        fields = {"candidate_id": candidate.id, "thesis_id": discovery.thesis_id}
    else:
        assert body.name and (body.website or body.crustdata_id)
        name, website = body.name, body.website
        if body.crustdata_id is not None:
            expected["crustdata_company_id"] = body.crustdata_id
        if body.thesis_id is not None:
            thesis = await repo.get_thesis(
                session, actor.workspace_id, _uuid(body.thesis_id, "Thesis")
            )
            fields["thesis_id"] = thesis.id
    expected.update({"name": name, "domain": normalize_domain(website) if website else None})
    case = await repo.create_case(
        session,
        actor.workspace_id,
        company_name=name,
        website=website,
        created_by=actor.user_id,
        credit_budget=Decimal(get_settings().case_credit_budget),
        identity_status=IdentityStatus.UNRESOLVED,
        identity_identifiers={"expected": {k: v for k, v in expected.items() if v is not None}},
        identity_candidates=[],
        **fields,
    )
    await create_run(
        session,
        workspace_id=actor.workspace_id,
        kind=RunKind.VERIFY,
        case_id=case.id,
        created_by=actor.user_id,
        steps=[identity_step()],
    )
    await session.commit()
    return case


async def latest_verify_run(session: AsyncSession, case: Case) -> Run | None:
    stmt = (
        select(Run)
        .where(Run.case_id == case.id, Run.kind == RunKind.VERIFY)
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def pick_identity(
    session: AsyncSession, actor: CaseActor, case_id: str, body: IdentityPickIn
) -> Case:
    """Record a person's pick among the stored candidates, with the evidence they were
    shown (matching and differing identifiers), who picked and when. Then unblock the
    identity-dependent steps."""
    case = await repo.get_case(session, actor.workspace_id, _uuid(case_id, "Case"))
    # Lock the row and re-read it, so two picks cannot both win.
    await session.execute(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if case.identity_status == IdentityStatus.CONFIRMED:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Identity is already confirmed.")
    chosen = next(
        (
            c
            for c in case.identity_candidates or []
            if c.get("crustdata_company_id") == body.crustdata_company_id
        ),
        None,
    )
    if chosen is None:
        await session.rollback()
        raise HTTPException(422, "Pick one of the candidates shown for this case.")
    matched = [k["key"] for k in chosen.get("matching", []) if k["key"] in CORROBORATING_KEYS]
    pick = {
        "crustdata_company_id": body.crustdata_company_id,
        "user_id": str(actor.user_id),
        "display_name": actor.display_name,
        "picked_at": datetime.now(UTC).isoformat(),
        "matched_keys": matched,
        "previous_state": case.identity_status,
        "evidence_shown": {
            "matching": chosen.get("matching", []),
            "differing": chosen.get("differing", []),
            "found_by": chosen.get("found_by", []),
            "confidence_score": chosen.get("confidence_score"),
            "other_candidates": [
                c.get("crustdata_company_id")
                for c in case.identity_candidates or []
                if c is not chosen
            ],
        },
    }
    keys = await record_key_evidence(session, case, chosen, basis="manual")
    note = f"Picked by {actor.display_name}" + (
        f"; matching identifiers: {', '.join(matched)}" if matched else "; no identifier matched"
    )
    apply_confirmation(case, chosen, keys=keys, basis="manual", note=note, pick=pick)
    run = await latest_verify_run(session, case)
    if run is None or not await _has_step(session, run, IDENTITY):
        run = await create_run(
            session,
            workspace_id=actor.workspace_id,
            kind=RunKind.VERIFY,
            case_id=case.id,
            created_by=actor.user_id,
            steps=[identity_step(), *dependent_steps()],
        )
    else:
        await append_steps(session, run.id, dependent_steps())
    # Claims checked before the pick read "not checked: identity unresolved"; check them
    # again against the picked company, then re-assess and redraft the request list.
    await schedule_case_checks(session, case=case, run_id=run.id)
    await ensure_assessment_tail(session, run_id=run.id)
    await session.commit()
    return case


async def _has_step(session: AsyncSession, run: Run, key: str) -> bool:
    found = await session.execute(select(Step.id).where(Step.run_id == run.id, Step.key == key))
    return found.first() is not None


async def start_verify(session: AsyncSession, actor: CaseActor, case_id: str) -> Run:
    """A fresh verify run. Cached calls replay at no new cost; a manual pick stands."""
    case = await repo.get_case(session, actor.workspace_id, _uuid(case_id, "Case"))
    run = await create_run(
        session,
        workspace_id=actor.workspace_id,
        kind=RunKind.VERIFY,
        case_id=case.id,
        created_by=actor.user_id,
        steps=[identity_step()],
    )
    # Every readable claim is checked again in this run. The identity step adds the
    # closing evaluate → request list once it has confirmed (or kept) the identity.
    await schedule_case_checks(session, case=case, run_id=run.id)
    await session.commit()
    return run
