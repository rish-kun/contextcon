"""Fixtures for pipeline tests: a migrated test database, the real app with auth, and
fake provider clients (no network)."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.api.documents import document_storage
from app.documents import LocalStorage
from app.pipelines.verify.checks.clients import set_client_factory
from tests.auth.conftest import _auth_env, app, client  # noqa: F401
from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "uploads")


@pytest_asyncio.fixture
async def api(app, storage) -> AsyncIterator:  # noqa: F811
    app.dependency_overrides[document_storage] = lambda: storage
    yield app


@pytest.fixture(autouse=True)
def _reset_client_factory():
    yield
    set_client_factory(None)
