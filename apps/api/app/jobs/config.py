"""Worker settings. Read from the environment (and the repo `.env` in local dev)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.settings import ENV_FILE


class JobSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # Run the worker inside the API process (FastAPI lifespan). Set false when a
    # separate `python -m app.jobs.worker` process does the work.
    worker_in_process: bool = True
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    worker_lease_seconds: float = Field(default=60.0, gt=0)
    worker_poll_seconds: float = Field(default=1.0, gt=0)
    worker_max_attempts: int = Field(default=3, ge=1)
    worker_retry_base_seconds: float = Field(default=2.0, ge=0)
    worker_retry_max_seconds: float = Field(default=120.0, ge=0)
    purge_interval_seconds: float = Field(default=3600.0, gt=0)


@lru_cache
def get_job_settings() -> JobSettings:
    return JobSettings()
