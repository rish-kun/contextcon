"""Users, password checks and sign-in sessions in the database.

The session cookie carries a 256-bit random token. Only `sha256(token)` is stored, so a
leaked database row cannot be replayed as a cookie. Sessions have an absolute expiry;
logout deletes the row.
"""

import asyncio
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.ratelimit import verification_slots
from app.db import repo
from app.db.models import AuthSession, User, Workspace

SESSION_COOKIE = "dp_session"


@dataclass(frozen=True, slots=True)
class AuthUser:
    """The signed-in person. Safe to keep after the database session closes."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    display_name: str

    @classmethod
    def of(cls, user: User) -> "AuthUser":
        return cls(user.id, user.workspace_id, user.email, user.display_name)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == normalize_email(email))
    return (await db.execute(stmt)).scalar_one_or_none()


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """The user if the password matches, else None (same work either way).

    Raises `ratelimit.VerifierBusy` when every Argon2 slot stays taken too long."""
    user = await find_user_by_email(db, email)
    # Argon2 is deliberately slow; keep it off the event loop, and cap how many run at once.
    stored = user.password_hash if user else None
    async with verification_slots().slot():
        ok = await asyncio.to_thread(verify_password, stored, password)
    if not ok:
        return None
    assert user is not None and user.password_hash is not None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


async def create_session(
    db: AsyncSession, user: User | AuthUser, *, ttl: timedelta
) -> tuple[str, AuthSession]:
    """Start a session; returns the raw token (cookie value) and the row. Flushes."""
    token = secrets.token_urlsafe(32)
    row = AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=_now() + ttl)
    db.add(row)
    await db.flush()
    return token, row


async def resolve_session(db: AsyncSession, token: str) -> AuthUser | None:
    """The user behind a live session token, or None if unknown or expired."""
    if not token:
        return None
    stmt = (
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.expires_at > _now())
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    return AuthUser.of(user) if user is not None else None


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))


async def revoke_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


async def purge_expired_sessions(db: AsyncSession) -> int:
    result = await db.execute(delete(AuthSession).where(AuthSession.expires_at <= _now()))
    return result.rowcount  # type: ignore[attr-defined,no-any-return]


# --- Account administration (CLI) ---------------------------------------------


async def create_workspace(db: AsyncSession, name: str) -> Workspace:
    return await repo.create_workspace(db, name.strip())


async def find_workspace(db: AsyncSession, ref: str) -> Workspace:
    """A workspace by id, or by exact name when that name is unique."""
    try:
        ws = await db.get(Workspace, uuid.UUID(ref))
    except ValueError:
        rows = list((await db.execute(select(Workspace).where(Workspace.name == ref))).scalars())
        if len(rows) > 1:
            raise LookupError(f"several workspaces are named {ref!r}; pass the id") from None
        ws = rows[0] if rows else None
    if ws is None:
        raise LookupError(f"no workspace {ref!r}")
    return ws


async def create_user(
    db: AsyncSession, workspace_id: uuid.UUID, *, email: str, display_name: str, password: str
) -> User:
    user = await repo.create_user(
        db, workspace_id, email=normalize_email(email), display_name=display_name.strip()
    )
    user.password_hash = hash_password(password)
    await db.flush()
    return user


async def set_password(db: AsyncSession, email: str, password: str) -> User:
    """Replace the password and end every session of that user."""
    user = await find_user_by_email(db, email)
    if user is None:
        raise LookupError(f"no user with email {normalize_email(email)!r}")
    user.password_hash = hash_password(password)
    await revoke_user_sessions(db, user.id)
    await db.flush()
    return user
