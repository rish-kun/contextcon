import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from app.db.base import Base
from app.db.models import IMMUTABLE_TABLES
from app.db.session import make_engine
from tests.db import pg


def test_upgrade_downgrade_upgrade(pg_server: str) -> None:
    with pg.fresh_database(pg_server) as url:
        pg.migrate(url)
        pg.downgrade(url, "base")
        pg.migrate(url)


@pytest.mark.asyncio
async def test_models_match_migrations(db_url: str) -> None:
    engine = make_engine(db_url)
    try:
        async with engine.connect() as conn:
            diff = await conn.run_sync(
                lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
            )
            triggers = (
                await conn.execute(
                    text("SELECT event_object_table FROM information_schema.triggers")
                )
            ).scalars()
            assert set(IMMUTABLE_TABLES) <= set(triggers)
    finally:
        await engine.dispose()
    assert diff == []
