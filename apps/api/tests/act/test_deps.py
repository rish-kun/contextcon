import pytest

from app.act import deps
from app.act.pg_repository import PostgresActRepository
from app.act.repository import InMemoryActRepository


def test_default_repository_is_postgres_when_a_database_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(deps, "database_configured", lambda: True)
    monkeypatch.setattr(deps, "get_sessionmaker", lambda: object())
    assert isinstance(deps.default_act_repository(), PostgresActRepository)


def test_without_a_database_memory_is_only_allowed_in_test_mode(monkeypatch) -> None:
    class Flags:
        email_send_enabled = False

    monkeypatch.setattr(deps, "database_configured", lambda: False)
    monkeypatch.setattr(deps, "get_settings", lambda: Flags)
    assert isinstance(deps.default_act_repository(), InMemoryActRepository)
    Flags.email_send_enabled = True
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        deps.default_act_repository()
