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
