"""Where the API is running, and the start-up checks that depend on it.

Production means Cloud Run (`K_SERVICE` is set by the platform) or `APP_ENV=production`.
There, fixture mode (`DEALPROOF_FIXTURES=1`, which signs every request in as the fixture
user) is refused at start-up, and the interactive docs and `/openapi.json` are off.
"""

import os

from app.api._base import fixtures_enabled


def is_production() -> bool:
    return bool(os.environ.get("K_SERVICE")) or (
        os.environ.get("APP_ENV", "").strip().lower() == "production"
    )


def check_startup() -> None:
    """Raise if the environment is unsafe to serve requests in."""
    if fixtures_enabled() and is_production():
        raise RuntimeError(
            "DEALPROOF_FIXTURES=1 is not allowed in production (K_SERVICE or "
            "APP_ENV=production is set): fixture mode signs every request in."
        )
