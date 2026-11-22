from fastapi.testclient import TestClient

from app.main import app
from app.settings import Settings


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_defaults_are_safe(monkeypatch) -> None:
    for name in ("EMAIL_SEND_ENABLED", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.email_send_enabled is False
    assert settings.anthropic_model == "claude-haiku-5-5"
