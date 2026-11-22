"""Application settings.

Values come from environment variables first, then from the repo-root `.env`
(local dev only; deployed services get the same names from Secret Manager).
Every field has a safe default so the app boots without any secrets.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/settings.py -> repo root is three levels up from this file's directory.
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
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
    database_url: str = ""
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
