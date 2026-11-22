import pytest
from sqlalchemy import event

from app.db.session import _connect_args, make_engine, normalise_url, to_async_url

NEON_POOLED = (
    "postgresql://u:p@ep-x-123-pooler.ap-southeast-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_neon_url_becomes_asyncpg_url() -> None:
    url = "postgresql://u:p@ep-x-123.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    async_url, args = normalise_url(url)
    assert async_url == "postgresql+asyncpg://u:p@ep-x-123.ap-southeast-1.aws.neon.tech/neondb"
    assert args == {"ssl": "require"}
    assert to_async_url(url) == async_url


def test_neon_pooled_url_keeps_ssl_and_disables_statement_cache() -> None:
    async_url, args = normalise_url(NEON_POOLED)
    assert "channel_binding" not in async_url
    assert "sslmode" not in async_url
    assert args["ssl"] == "require"
    assert args["statement_cache_size"] == 0


def test_other_query_params_are_kept() -> None:
    async_url, args = normalise_url("postgresql://u@h/db?application_name=dp&sslmode=verify-full")
    assert async_url == "postgresql+asyncpg://u@h/db?application_name=dp"
    assert args == {"ssl": "verify-full"}


def test_unknown_sslmode_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_url("postgresql://u@h/db?sslmode=bogus")


@pytest.mark.anyio
async def test_make_engine_passes_ssl_to_asyncpg() -> None:
    """The arguments asyncpg.connect receives: ssl set, libpq-only params gone."""
    engine = make_engine(NEON_POOLED)
    seen: dict = {}

    class _Stop(Exception):
        pass

    @event.listens_for(engine.sync_engine, "do_connect")
    def _capture(dialect, conn_rec, cargs, cparams):  # noqa: ANN001, ANN202
        seen.update(cparams)
        raise _Stop

    try:
        with pytest.raises(_Stop):
            async with engine.connect():
                pass
    finally:
        await engine.dispose()
    assert seen["ssl"] == "require"
    assert seen["statement_cache_size"] == 0
    assert "channel_binding" not in seen
    assert "sslmode" not in seen


def test_postgres_scheme_and_plain_url() -> None:
    assert to_async_url("postgres://u@h:5432/db") == "postgresql+asyncpg://u@h:5432/db"
    assert to_async_url("postgresql+asyncpg://u@h/db") == "postgresql+asyncpg://u@h/db"


def test_empty_url_rejected() -> None:
    with pytest.raises(ValueError):
        to_async_url("")


def test_pooler_host_disables_statement_cache() -> None:
    args = _connect_args("postgresql+asyncpg://u@ep-x-pooler.neon.tech/db")
    assert args["statement_cache_size"] == 0
    assert _connect_args("postgresql+asyncpg://u@localhost/db") == {}
