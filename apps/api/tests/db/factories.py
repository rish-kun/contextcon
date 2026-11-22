"""Small builders for test rows."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import Case, DiscoveryRun, Thesis, User, Workspace


@dataclass
class Tenant:
    workspace: Workspace
    user: User
    case: Case


async def tenant(session: AsyncSession, name: str = "acme", **case_fields) -> Tenant:
    ws = await repo.create_workspace(session, name)
    user = await repo.create_user(
        session, ws.id, email=f"{name}-{ws.id.hex[:6]}@example.test", display_name=f"{name} analyst"
    )
    case = await repo.create_case(
        session, ws.id, company_name=f"{name} target (fixture)", created_by=user.id, **case_fields
    )
    await session.commit()
    return Tenant(ws, user, case)


async def discovery_run(session: AsyncSession, t: Tenant) -> DiscoveryRun:
    thesis = Thesis(workspace_id=t.workspace.id, text="fixture thesis", created_by=t.user.id)
    session.add(thesis)
    await session.flush()
    dr = DiscoveryRun(workspace_id=t.workspace.id, thesis_id=thesis.id)
    session.add(dr)
    await session.commit()
    return dr


def days(n: float) -> datetime:
    return datetime.now(UTC) + timedelta(days=n)
