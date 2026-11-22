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
    # Failed sign-ins allowed per client IP across all emails, and in total, per window.
    login_max_failures_per_ip: int = Field(default=50, ge=1)
    login_max_failures_global: int = Field(default=1000, ge=1)
    # Limiter keys kept in memory at most (least recently hit evicted first).
    login_max_tracked_keys: int = Field(default=100_000, ge=100)
    # Argon2 checks running at once, and how long a sign-in waits for a slot before 503.
    login_max_concurrent_verifications: int = Field(default=4, ge=1)
    login_verification_wait_seconds: float = Field(default=5.0, gt=0)
    min_password_length: int = Field(default=10, ge=8)
    # How many trusted proxies append to `X-Forwarded-For` in front of the API. The client
    # IP is the entry that many places from the right; 0 ignores the header and uses the
    # socket peer. Deployed behind the web proxy on Cloud Run: 2 (the web proxy forwards
    # only the address Google's front end appended, then the API's front end appends the
    # web service's address).
    trusted_proxy_hops: int = Field(default=0, ge=0)

    @property
    def on_cloud_run(self) -> bool:
        return bool(os.environ.get("K_SERVICE"))


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
