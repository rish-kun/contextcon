import pytest

from app.pipelines.memo import llm as memo_llm
from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401


@pytest.fixture(autouse=True)
def no_real_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Memo drafting never reaches the real model in tests; tests that need a model
    install a scripted one."""
    monkeypatch.setattr(memo_llm, "make_llm", lambda ctx: None)
