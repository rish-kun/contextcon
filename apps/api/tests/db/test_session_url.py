import pytest

from app.db.session import _connect_args, to_async_url


def test_neon_url_becomes_asyncpg_url() -> None:
    url = "postgresql://u:p@ep-x-123.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert (
        to_async_url(url)
        == "postgresql+asyncpg://u:p@ep-x-123.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
    )


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
