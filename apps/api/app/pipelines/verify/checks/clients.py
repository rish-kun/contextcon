"""How claim intake and checks get their Crustdata and LLM clients.

Both are cached and metered through the step's recorder. LLM calls carry claim or
document text, which is confidential, so their cache is scoped to the case and
stamped with `delete_after` (the retention purge removes it). Tests swap the
factory with `set_client_factory`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from app.db.adapters import DbCache
from app.documents.storage import compute_delete_after
from app.settings import get_settings


class ClientFactory(Protocol):
    def crustdata(self, ctx: Any) -> Any: ...

    def llm(self, ctx: Any, *, delete_after: datetime | None) -> Any: ...


class SettingsClientFactory:
    def crustdata(self, ctx: Any) -> Any:
        from app.clients import CrustdataClient

        return CrustdataClient.from_settings(recorder=ctx.recorder, cache=ctx.cache)

    def llm(self, ctx: Any, *, delete_after: datetime | None) -> Any:
        from app.clients import LLMClient

        cache = None
        if ctx.cost is not None and ctx.cost.case_id is not None:
            expires = delete_after or compute_delete_after(
                datetime.now(UTC), get_settings().upload_retention_days
            )
            cache = DbCache(ctx.sessionmaker, ctx.cost, confidential=True, delete_after=expires)
        return LLMClient.from_settings(recorder=ctx.recorder, cache=cache)


_factory: ClientFactory = SettingsClientFactory()


def client_factory() -> ClientFactory:
    return _factory


def set_client_factory(factory: ClientFactory | None) -> None:
    global _factory
    _factory = factory or SettingsClientFactory()


async def close_quietly(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if close is not None:
        try:
            await close()
        except Exception:  # pragma: no cover - closing must never mask the result
            pass
