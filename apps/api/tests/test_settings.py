from pathlib import Path

from pydantic import SecretStr

from app.settings import Settings, _find_repo_env


def test_find_repo_env_handles_shallow_docker_layout() -> None:
    # In the API image settings.py lives at /app/app/settings.py (only three parents).
    assert _find_repo_env(Path("/app/app/settings.py")) is None
    assert _find_repo_env(Path("/settings.py")) is None


def test_find_repo_env_returns_none_when_env_file_missing(tmp_path: Path) -> None:
    settings_file = tmp_path / "apps" / "api" / "app" / "settings.py"
    settings_file.parent.mkdir(parents=True)
    settings_file.touch()
    assert _find_repo_env(settings_file) is None


def test_find_repo_env_finds_repo_root_env(tmp_path: Path) -> None:
    settings_file = tmp_path / "apps" / "api" / "app" / "settings.py"
    settings_file.parent.mkdir(parents=True)
    settings_file.touch()
    env_file = tmp_path / ".env"
    env_file.write_text("")
    assert _find_repo_env(settings_file) == env_file.resolve()


def test_settings_load_from_process_env_without_env_file(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    settings = Settings(_env_file=None)
    assert isinstance(settings.database_url, SecretStr)
    assert settings.database_url.get_secret_value() == "postgresql://user:pw@host/db"
    assert "pw@host" not in repr(settings)


def test_database_url_defaults_to_empty_secret(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url.get_secret_value() == ""


def test_anthropic_key_accepts_claude_api_key_name(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-test-claude")
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key.get_secret_value() == "sk-test-claude"


def test_anthropic_key_prefers_anthropic_name(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-test-claude")
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key.get_secret_value() == "sk-test-anthropic"


def test_anthropic_key_read_from_env_file_under_claude_name(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("CLAUDE_API_KEY=sk-test-file\n")
    settings = Settings(_env_file=env_file)
    assert settings.anthropic_api_key.get_secret_value() == "sk-test-file"


def test_credit_budget_defaults(monkeypatch) -> None:
    for name in ("CASE_CREDIT_BUDGET", "DISCOVER_CREDIT_BUDGET", "INVESTOR_CREDIT_BUDGET"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.case_credit_budget == 150
    assert settings.discover_credit_budget == 100
    assert settings.investor_credit_budget == 60
