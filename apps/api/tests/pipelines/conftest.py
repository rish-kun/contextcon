from contextlib import asynccontextmanager

import pytest

from app.pipelines.act import llm as act_llm
from app.pipelines.memo import llm as memo_llm
from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401


@pytest.fixture(autouse=True)
def no_real_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify runs end with evaluate → request list. Neither reaches the real model in
    tests: the memo and the seller email use their deterministic fallbacks."""

    @asynccontextmanager
    async def no_llm(*_args, **_kwargs):
        yield None

    monkeypatch.setattr(memo_llm, "make_llm", lambda ctx: None)
    monkeypatch.setattr(act_llm, "llm_factory", no_llm)
