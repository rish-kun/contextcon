import ssl
from pathlib import Path

import pytest
from sqlalchemy import event

from app.db.session import (
    _connect_args,
    make_engine,
    normalise_url,
    tls_mode,
    to_async_url,
    verified_ssl_context,
)

NEON_POOLED = (
    "postgresql://u:p@ep-x-123-pooler.ap-southeast-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def _assert_verifying(value: object) -> None:
    assert isinstance(value, ssl.SSLContext)
    assert value.verify_mode == ssl.CERT_REQUIRED
    assert value.check_hostname is True
    assert value.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_neon_url_becomes_asyncpg_url() -> None:
    url = "postgresql://u:p@ep-x-123.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    async_url, args = normalise_url(url)
    assert async_url == "postgresql+asyncpg://u:p@ep-x-123.ap-southeast-1.aws.neon.tech/neondb"
    assert set(args) == {"ssl"}
    _assert_verifying(args["ssl"])
    assert to_async_url(url) == async_url


def test_neon_pooled_url_verifies_tls_and_disables_statement_cache() -> None:
    async_url, args = normalise_url(NEON_POOLED)
    assert "channel_binding" not in async_url
    assert "sslmode" not in async_url
    _assert_verifying(args["ssl"])
    assert args["statement_cache_size"] == 0


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full", "true", "1"])
def test_every_encrypting_mode_verifies_the_server(mode: str) -> None:
    """libpq's `require` would accept any certificate; here it verifies CA and host."""
    _, args = normalise_url(f"postgresql://u@db.example.com/db?sslmode={mode}")
    _assert_verifying(args["ssl"])
    assert tls_mode(args) == "verify-full"


def test_remote_host_without_sslmode_still_verifies() -> None:
    """asyncpg's own default is unverified `prefer`; a remote host never gets that."""
    _, args = normalise_url("postgresql://u@db.example.com/db")
    _assert_verifying(args["ssl"])


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u@127.0.0.1:5432/db",
        "postgresql://u@localhost/db",
        "postgresql://u@[::1]/db",
        "postgresql:///db",
    ],
)
def test_local_hosts_keep_asyncpg_default(url: str) -> None:
    _, args = normalise_url(url)
    assert "ssl" not in args
    assert tls_mode(args) == "default"


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_explicit_non_verifying_modes_pass_through(mode: str) -> None:
    _, args = normalise_url(f"postgresql://u@127.0.0.1/db?sslmode={mode}")
    assert args == {"ssl": mode}


def test_verified_context_uses_a_ca_store() -> None:
    """The context can reach CA certificates, or every Neon connection fails. (The image
    itself is checked by the Dockerfile.) A CA file is loaded up front and counted; a CA
    directory (e.g. /etc/ssl/certs on Ubuntu) is read lazily per lookup, so it counts 0
    until a handshake and is checked by its contents instead."""
    loaded = verified_ssl_context().cert_store_stats()["x509_ca"]
    paths = ssl.get_default_verify_paths()
    capath = Path(paths.capath) if paths.capath else None
    lazy = capath is not None and capath.is_dir() and any(capath.glob("*.0"))
    assert loaded > 0 or lazy, f"no CA certificates found ({paths})"


def test_other_query_params_are_kept() -> None:
    async_url, args = normalise_url("postgresql://u@h/db?application_name=dp&sslmode=verify-full")
    assert async_url == "postgresql+asyncpg://u@h/db?application_name=dp"
    assert set(args) == {"ssl"}
    _assert_verifying(args["ssl"])


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
    _assert_verifying(seen["ssl"])
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
