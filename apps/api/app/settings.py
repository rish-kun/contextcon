"""Application settings.

Values come from environment variables first, then from the repo-root `.env`
(local dev only; deployed services get the same names from Secret Manager).
Every field has a safe default so the app boots without any secrets.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
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
        # Lets code and tests pass fields by name (e.g. `anthropic_api_key=`) as well
        # as by their env aliases.
        populate_by_name=True,
    )

    # Crustdata (company / people / funding / web data)
    crustdata_api_key: SecretStr = SecretStr("")
    crustdata_base_url: str = "https://api.crustdata.com"
    # Crustdata requires this header value on every request (docs: x-api-version).
    crustdata_api_version: str = "2025-11-01"
    crustdata_timeout_seconds: float = Field(default=60.0, gt=0)
    # Retries on 429 / 5xx / network errors, on top of the first attempt.
    crustdata_max_retries: int = Field(default=3, ge=0)

    # Anthropic (direct Messages API)
    # Accepts either env name; ANTHROPIC_API_KEY wins when both are set.
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    )
    anthropic_model: str = "claude-haiku-5-5"
    # Where the app's LLM calls go. Deliberately not ANTHROPIC_BASE_URL, which agent
    # and developer shells set for their own proxies; the client never reads it.
    anthropic_base_url_override: str = "https://api.anthropic.com"
    anthropic_max_tokens: int = Field(default=4096, gt=0)
    # There is deliberately no temperature / top_p / top_k setting: Haiku 5.5 rejects
    # non-default sampling values, and the client has no code path that sends them.
    # A stray ANTHROPIC_TEMPERATURE in the environment is ignored.
    # Thinking depth / token spend. Unset means the model's default (medium on Haiku 5.5).
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "low"
    anthropic_timeout_seconds: float = Field(default=120.0, gt=0)
    anthropic_max_retries: int = Field(default=2, ge=0)
    # Optional per-model price overrides (USD per million tokens), as JSON, e.g.
    # {"claude-haiku-5-5": {"input_per_mtok": 0.10, "output_per_mtok": 0.50}}
    anthropic_prices: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Model names the API may return mapped to a priced model, as JSON, e.g.
    # {"claude-haiku-5-5-20261001": "claude-haiku-5-5"}. Unmatched models are recorded
    # as unknown cost.
    anthropic_model_aliases: dict[str, str] = Field(default_factory=dict)

    # Email (Resend). Sending stays off unless explicitly enabled.
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = ""
    email_send_enabled: bool = False

    # Storage
    database_url: SecretStr = SecretStr("")
    gcs_bucket: str = ""
    upload_retention_days: int = Field(default=30, gt=0)

    # Crustdata credit budgets: per case, per discover run, per investor search
    case_credit_budget: int = Field(default=150, ge=0)
    discover_credit_budget: int = Field(default=100, ge=0)
    investor_credit_budget: int = Field(default=60, ge=0)

    # Web origin(s) allowed by CORS; comma-separated for more than one.
    web_origin: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
