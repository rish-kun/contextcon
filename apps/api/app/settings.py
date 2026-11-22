"""Application settings.

Values come from environment variables first, then from the repo-root `.env`
(local dev only; deployed services get the same names from Secret Manager).
Every field has a safe default so the app boots without any secrets.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_env(settings_file: Path) -> Path | None:
    """Return the repo-root `.env` when running from the monorepo, else None.

    In the repo, apps/api/app/settings.py sits three levels below the root. In the
    Docker image the file is /app/app/settings.py, which has no such ancestor, so
    the app relies on process environment variables only.
    """
    parents = settings_file.resolve().parents
    if len(parents) <= 3:
        return None
    candidate = parents[3] / ".env"
    return candidate if candidate.is_file() else None


ENV_FILE = _find_repo_env(Path(__file__))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Crustdata (company / people / funding / web data)
    crustdata_api_key: SecretStr = SecretStr("")

    # Anthropic (direct Messages API)
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-haiku-5-5"
    anthropic_max_tokens: int = Field(default=4096, gt=0)

    # Email (Resend). Sending stays off unless explicitly enabled.
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = ""
    email_send_enabled: bool = False

    # Storage
    database_url: SecretStr = SecretStr("")
    gcs_bucket: str = ""
    upload_retention_days: int = Field(default=30, gt=0)

    # Per-case Crustdata credit budget
    case_credit_budget: int = Field(default=150, ge=0)

    # Web origin(s) allowed by CORS; comma-separated for more than one.
    web_origin: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
