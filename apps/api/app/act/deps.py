"""Injectable dependencies for the Act router.

The integrator wires real auth and case access with `app.dependency_overrides`:

    app.dependency_overrides[get_actor] = <returns the signed-in Actor>
    app.dependency_overrides[authorize_case] = <checks the actor may act on case_id>
    app.dependency_overrides[get_act_service] = <ActService on the Postgres repository>

Until then `get_actor` and `authorize_case` fail closed with 501, so an unwired router
can never send anything.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.act.models import Actor
from app.act.repository import InMemoryActRepository
from app.act.resend import ResendClient
from app.act.service import ActService, SendConfig
from app.settings import get_settings


async def get_actor() -> Actor:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Act: authentication is not wired.")


async def authorize_case(case_id: str, actor: Annotated[Actor, Depends(get_actor)]) -> str:
    """Return `case_id` if `actor` may act on it; raise 403/404 otherwise."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Act: case access is not wired.")


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
