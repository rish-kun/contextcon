from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import sessions
from app.db import repo
from app.db.models import Case, User, Workspace

PASSWORD = "correct horse battery"


@dataclass
class Account:
    workspace: Workspace
    user: User
    case: Case
    email: str


async def account(db: AsyncSession, name: str) -> Account:
    ws = await sessions.create_workspace(db, f"{name} fund")
    email = f"{name}@fund.example"
    user = await sessions.create_user(
        db, ws.id, email=email, display_name=f"{name.title()} Analyst", password=PASSWORD
    )
    case = await repo.create_case(
        db, ws.id, company_name=f"{name} target (fixture)", created_by=user.id
    )
    await db.commit()
    return Account(ws, user, case, email)


async def login(client, email: str, password: str = PASSWORD, **kw):
    return await client.post("/auth/login", json={"email": email, "password": password}, **kw)
