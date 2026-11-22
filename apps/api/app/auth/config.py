"""Auth settings, read from the environment (`AUTH_*`)."""

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.settings import ENV_FILE


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTH_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # Absolute session lifetime. A session never extends itself; sign in again after it.
    session_ttl_hours: float = Field(default=24.0, gt=0)
    # Mark the cookie Secure. Unset: on when running on Cloud Run (`K_SERVICE`) or when
    # the request arrived over https (the web proxy sends `x-forwarded-proto`).
    cookie_secure: bool | None = None
    # Failed sign-ins allowed per (email, client IP) and per email within the window.
    login_max_failures_per_client: int = Field(default=5, ge=1)
    login_max_failures_per_email: int = Field(default=20, ge=1)
    login_window_seconds: int = Field(default=900, ge=1)
    min_password_length: int = Field(default=10, ge=8)

    @property
    def on_cloud_run(self) -> bool:
        return bool(os.environ.get("K_SERVICE"))


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
