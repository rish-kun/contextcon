"""Start-up checks: fixture mode is refused in production; docs are off there."""

import httpx2 as httpx
import pytest

from app.act import deps
from app.act.repository import InMemoryActRepository
from app.main import create_app
from app.runtime import is_production


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DEALPROOF_FIXTURES", "K_SERVICE", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("env", [{"K_SERVICE": "dealproof-api"}, {"APP_ENV": "production"}])
def test_fixture_mode_refused_in_production(monkeypatch, env) -> None:
    monkeypatch.setenv("DEALPROOF_FIXTURES", "1")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert is_production()
    with pytest.raises(RuntimeError, match="DEALPROOF_FIXTURES"):
        create_app()


def test_fixture_mode_allowed_locally(monkeypatch) -> None:
    monkeypatch.setenv("DEALPROOF_FIXTURES", "1")
    monkeypatch.setenv("APP_ENV", "development")
    assert not is_production()
    create_app()


def _routes(app) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


@pytest.mark.anyio
@pytest.mark.parametrize("env", [{"K_SERVICE": "dealproof-api"}, {"APP_ENV": "production"}])
async def test_docs_off_in_production(monkeypatch, env) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = create_app()
    assert not {"/docs", "/redoc", "/openapi.json"} & _routes(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404
    # The committed contract can still be exported.
    assert app.openapi()["paths"]


def test_docs_on_locally() -> None:
    assert {"/docs", "/redoc", "/openapi.json"} <= _routes(create_app())


def test_act_uses_an_isolated_repository_in_fixture_mode(monkeypatch) -> None:
    monkeypatch.setenv("DEALPROOF_FIXTURES", "1")
    # Even with a database configured, fixture traffic never reaches it.
    monkeypatch.setattr(deps, "database_configured", lambda: True)
    assert isinstance(deps.default_act_repository(), InMemoryActRepository)
    monkeypatch.setattr(deps, "live_act_service", lambda: pytest.fail("live service built"))
    service = deps.get_act_service()
    assert service is deps.fixture_act_service()
    assert isinstance(service._repo, InMemoryActRepository)
    assert not service._config.enabled and service._provider is None
