"""Injectable dependencies for the Act router.

`get_actor` is the signed-in user (`app.auth.deps.current_user`; 401 without a session)
and `authorize_case` checks the case is in that user's workspace (404 otherwise), so
every approval records a real, named user. Tests may still replace them with
`app.dependency_overrides`.

`get_act_service` still uses in-memory storage until the Postgres repository is wired.
"""

from __future__ import annotations

from functools import lru_cache

from app.act.models import Actor
from app.act.repository import InMemoryActRepository
from app.act.resend import ResendClient
from app.act.service import ActService, SendConfig
from app.auth.deps import CurrentUser, check_case_access
from app.settings import get_settings


async def get_actor(user: CurrentUser) -> Actor:
    """The signed-in user as the Act step's actor (id + display name)."""
    return Actor(user_id=str(user.id), display_name=user.display_name)


async def authorize_case(case_id: str, user: CurrentUser) -> str:
    """Return `case_id` if the signed-in user's workspace owns the case; 404 otherwise."""
    await check_case_access(user, case_id)
    return case_id


@lru_cache
def get_act_service() -> ActService:
    """Default service: in-memory storage (swap for the Postgres repository once
    `app/db/` lands) and Resend from settings. Sending stays off unless
    `EMAIL_SEND_ENABLED=true`."""
    settings = get_settings()
    api_key = settings.resend_api_key.get_secret_value()
    provider = ResendClient(api_key) if api_key else None
    config = SendConfig(enabled=settings.email_send_enabled, sender=settings.email_from)
    return ActService(InMemoryActRepository(), config, provider)
