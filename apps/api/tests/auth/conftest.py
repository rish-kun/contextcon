from collections.abc import AsyncIterator

import httpx2 as httpx
import pytest
import pytest_asyncio

from app.act.deps import get_act_service
from app.auth.config import get_auth_settings
from app.auth.ratelimit import login_limiter
from app.db.session import dispose_engine, init_engine
from app.main import create_app
from tests.act.fakes import make_service
from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_auth_settings.cache_clear()
    login_limiter().reset()
    yield
    get_auth_settings.cache_clear()
    login_limiter().reset()


@pytest_asyncio.fixture
async def app(sm, db_url):  # noqa: F811
    """The real app on the test database (the in-process worker is not started)."""
    init_engine(db_url)
    application = create_app()
    service, *_ = make_service(enabled=False)
    application.dependency_overrides[get_act_service] = lambda: service
    try:
        yield application
    finally:
        await dispose_engine()


def client_for(application, **kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://t", **kw
    )


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(app) as c:
        yield c
