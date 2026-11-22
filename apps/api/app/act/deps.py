"""Injectable dependencies for the Act router.

`get_actor` is the signed-in user (`app.auth.deps.current_user`; 401 without a session)
and `authorize_case` checks the case is in that user's workspace (404 otherwise), so
every approval records a real, named user. Tests may still replace them with
`app.dependency_overrides`.

`get_act_service` stores messages in Postgres (`PostgresActRepository`) whenever
`DATABASE_URL` is set; the in-memory repository is only a local-development fallback
and is never durable.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.act.models import Actor
from app.act.pg_repository import PostgresActRepository
from app.act.repository import ActRepository, InMemoryActRepository
from app.act.resend import ResendClient
from app.act.service import ActService, SendConfig
from app.auth.deps import CurrentUser, check_case_access
from app.db.session import database_configured, get_sessionmaker
from app.settings import get_settings

log = logging.getLogger(__name__)


async def get_actor(user: CurrentUser) -> Actor:
    """The signed-in user as the Act step's actor (id + display name)."""
    return Actor(user_id=str(user.id), display_name=user.display_name)


async def authorize_case(case_id: str, user: CurrentUser) -> str:
    """Return `case_id` if the signed-in user's workspace owns the case; 404 otherwise."""
    await check_case_access(user, case_id)
    return case_id


def default_act_repository() -> ActRepository:
    if database_configured():
        return PostgresActRepository(get_sessionmaker())
    if get_settings().email_send_enabled:
        # A real send must leave a durable record; refuse rather than forget it.
        raise RuntimeError("EMAIL_SEND_ENABLED=true needs DATABASE_URL (Postgres).")
    log.warning("act: DATABASE_URL is not set; messages are kept in memory only")
    return InMemoryActRepository()


@lru_cache
def get_act_service() -> ActService:
    """Default service: Postgres storage and Resend from settings. Sending stays off
    unless `EMAIL_SEND_ENABLED=true`."""
    settings = get_settings()
    api_key = settings.resend_api_key.get_secret_value()
    provider = ResendClient(api_key) if api_key else None
    config = SendConfig(enabled=settings.email_send_enabled, sender=settings.email_from)
    return ActService(default_act_repository(), config, provider)
