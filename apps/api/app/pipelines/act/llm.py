"""The drafting model for the seller email, charged to the case.

The request includes claim text from the seller's own documents, so the response cache
is confidential: keyed to this case and deleted on the upload retention schedule.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.adapters import DbCache, DbCallRecorder
from app.db.ledger import CostContext
from app.extraction.llm import DraftingLlm
from app.settings import get_settings


@asynccontextmanager
async def settings_llm(
    sessionmaker: async_sessionmaker[AsyncSession],
    cost: CostContext,
    recorder: Any = None,
) -> AsyncIterator[DraftingLlm | None]:
    """An `LLMClient` from settings, or None when no Anthropic key is configured (the
    email then comes from the deterministic template)."""
    settings = get_settings()
    if not settings.anthropic_api_key.get_secret_value():
        yield None
        return
    from app.clients.llm import LLMClient

    cache = DbCache(
        sessionmaker,
        cost,
        confidential=True,
        delete_after=datetime.now(UTC) + timedelta(days=settings.upload_retention_days),
    )
    client = LLMClient.from_settings(
        recorder=recorder or DbCallRecorder(sessionmaker, cost), cache=cache
    )
    try:
        yield client
    finally:
        await client.aclose()


# Swappable in tests: (sessionmaker, cost, recorder) -> async context of a DraftingLlm.
LlmFactory = Callable[..., Any]
llm_factory: LlmFactory = settings_llm
