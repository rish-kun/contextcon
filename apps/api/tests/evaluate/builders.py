"""Rows for evaluate and memo tests: a confirmed fictional company with sourced profile
fields, thesis criteria, and claims whose checks link to evidence."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx2 as httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import cases as case_routes
from app.api.cases_deps import get_case_session
from app.auth.deps import current_user
from app.auth.sessions import AuthUser
from app.db import repo
from app.db.models import (
    Case,
    Claim,
    ClaimCheck,
    ClaimCheckEvidence,
    Criterion,
    Evidence,
    Source,
    Thesis,
)
from app.main import create_app
from tests.db.factories import Tenant, tenant

COMPANY_ID = "4242"
RETRIEVED = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
TODAY = date(2026, 11, 22)


@dataclass
class World:
    t: Tenant
    claim: Claim


async def source(
    session: AsyncSession,
    t: Tenant,
    *,
    provider: str = "crustdata",
    endpoint: str = "/company/enrich",
    source_class: str = "data_provider",
    title: str | None = None,
    request: dict | None = None,
    document_id: uuid.UUID | None = None,
) -> Source:
    src = Source(
        workspace_id=t.workspace.id,
        case_id=t.case.id,
        provider=provider,
        endpoint_or_url=endpoint,
        request=request or {"crustdata_company_ids": [int(COMPANY_ID)]},
        retrieved_at=RETRIEVED,
        source_class=source_class,
        title=title,
        document_id=document_id,
    )
    session.add(src)
    await session.flush()
    return src


async def field(
    session: AsyncSession, t: Tenant, src: Source, path: str, value, *, as_of=date(2026, 11, 1)
) -> Evidence:
    ev = Evidence(
        source_id=src.id,
        case_id=t.case.id,
        entity_ref=f"crustdata:company:{COMPANY_ID}",
        field_path=path,
        value=value,
        as_of=as_of,
        origin_key=f"{path}:{value}",
    )
    session.add(ev)
    await session.flush()
    return ev


async def quote(
    session: AsyncSession, t: Tenant, src: Source, text: str, value, *, page: int | None = None
) -> Evidence:
    ev = Evidence(
        source_id=src.id,
        case_id=t.case.id,
        entity_ref=COMPANY_ID,
        span=text,
        page=page,
        value=value,
        as_of=date(2026, 10, 31),
        origin_key=f"quote:{text}",
    )
    session.add(ev)
    await session.flush()
    return ev


async def check(
    session: AsyncSession,
    claim: Claim,
    status: str,
    links: list[tuple[Evidence, str]],
    *,
    reason: str = "decided by rules",
) -> ClaimCheck:
    row = ClaimCheck(
        claim_id=claim.id,
        case_id=claim.case_id,
        status=status,
        reason=reason,
        policy_version="2026-11-22.1",
    )
    row.evidence_links = [ClaimCheckEvidence(evidence_id=e.id, relation=r) for e, r in links]
    session.add(row)
    await session.flush()
    return row


async def thesis(session: AsyncSession, t: Tenant, criteria: list[dict]) -> Thesis:
    th = Thesis(workspace_id=t.workspace.id, text="Logistics in India (fixture)", status="ready")
    session.add(th)
    await session.flush()
    for i, c in enumerate(criteria):
        session.add(Criterion(thesis_id=th.id, position=i, **c))
    case = await session.get(Case, t.case.id)
    case.thesis_id = th.id
    await session.flush()
    return th


INDIA_MUST = {
    "label": "Based in India",
    "kind": "must",
    "dimension": "geography",
    "operator": "eq",
    "value": "India",
    "crustdata_filter": {"column": "locations.country"},
}
SIZE_PREF = {
    "label": "At least 100 people",
    "kind": "preference",
    "dimension": "size",
    "operator": "gte",
    "value": 100,
}


async def confirmed_world(
    session: AsyncSession, *, with_thesis: bool = True, identity: str = "confirmed"
) -> World:
    """A confirmed company with a team-size claim the profile cannot settle."""
    t = await tenant(
        session,
        "eval",
        crustdata_company_id=COMPANY_ID,
        identity_status=identity,
        website="https://example-logistics.test",
    )
    enrich = await source(session, t, title="Company profile")
    await field(session, t, enrich, "locations.country", "India")
    await field(session, t, enrich, "basic_info.year_founded", 2014)
    profile = await source(
        session, t, source_class="professional_profile_signal", title="Headcount estimate"
    )
    headcount = await field(session, t, profile, "headcount.total", 180)
    if with_thesis:
        await thesis(session, t, [INDIA_MUST, SIZE_PREF])
    claim = Claim(
        case_id=t.case.id,
        original_text="We have 250 employees",
        origin="deck",
        category="team_size",
        components={"employee_count": "250"},
    )
    session.add(claim)
    await session.flush()
    await check(session, claim, "cannot_verify", [(headcount, "employee_count")])
    await session.commit()
    return World(t, claim)


async def add_payroll(session: AsyncSession, w: World) -> Evidence:
    """The seller's payroll summary arrives and states 250."""
    doc_src = await source(
        session,
        w.t,
        provider="upload",
        endpoint="upload://payroll_summary.pdf",
        source_class="seller_document",
        title="payroll_summary.pdf, p. 2",
        request={"document_type": "payroll_record"},
    )
    ev = await quote(session, w.t, doc_src, "Total employees on payroll: 250", "250", page=2)
    headcount = next(
        e
        for e in await repo.list_case_children(session, Evidence, w.t.workspace.id, w.t.case.id)
        if e.field_path == "headcount.total"
    )
    await check(
        session, w.claim, "supported", [(headcount, "employee_count"), (ev, "employee_count")]
    )
    await session.commit()
    return ev


def api_client(
    sm: async_sessionmaker[AsyncSession], workspace_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> httpx.AsyncClient:
    app = create_app()

    async def user() -> AuthUser:
        return AuthUser(
            id=user_id or uuid.uuid4(),
            workspace_id=workspace_id,
            email="analyst@example.test",
            display_name="Test analyst",
        )

    async def session():
        async with sm() as s:
            yield s

    app.dependency_overrides[current_user] = user
    app.dependency_overrides[case_routes.case_session] = session
    app.dependency_overrides[get_case_session] = session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
