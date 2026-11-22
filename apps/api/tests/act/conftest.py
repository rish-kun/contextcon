"""Run the Act service tests on both repositories: in-memory and Postgres.

The Postgres variant uses a NullPool engine, so every repository call opens its own
connection on whichever event loop is running (the tests call `asyncio.run` per
scenario) and concurrent sends really race in the database.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.act.models import Actor
from app.act.pg_repository import PostgresActRepository
from app.act.repository import ActRepository, InMemoryActRepository
from app.act.service import ActService, SendConfig
from app.db.base import Base
from app.db.models import Case, User, Workspace
from app.db.session import make_engine, make_sessionmaker
from tests.act.fakes import SENDER, FakeClock, FakeResend
from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401


@dataclass
class ActEnv:
    backend: str
    case: str
    other_case: str
    alice: Actor
    bob: Actor
    new_repo: Callable[[], ActRepository]

    def make_service(
        self,
        *,
        enabled: bool = True,
        fake: FakeResend | None = None,
        clock: FakeClock | None = None,
        repo: ActRepository | None = None,
        sender: str = SENDER,
    ) -> tuple[ActService, FakeResend, ActRepository, FakeClock]:
        clock = clock or FakeClock()
        fake = fake or FakeResend(clock=clock)
        repo = repo or self.new_repo()
        service = ActService(
            repo, SendConfig(enabled=enabled, sender=sender), fake.client(), clock=clock
        )
        return service, fake, repo, clock


def _memory_env() -> ActEnv:
    return ActEnv(
        backend="memory",
        case="case-1",
        other_case="case-2",
        alice=Actor(user_id="u-alice", display_name="Alice Analyst"),
        bob=Actor(user_id="u-bob", display_name="Bob Manager"),
        new_repo=InMemoryActRepository,
    )


async def _seed(url: str) -> dict[str, uuid.UUID]:
    engine = make_engine(url, poolclass=NullPool)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    try:
        async with make_sessionmaker(engine)() as session:
            await session.execute(text(f"TRUNCATE {tables} CASCADE"))
            ws = Workspace(name="act tests")
            session.add(ws)
            await session.flush()
            alice = User(
                workspace_id=ws.id, email="alice@example.test", display_name="Alice Analyst"
            )
            bob = User(workspace_id=ws.id, email="bob@example.test", display_name="Bob Manager")
            case = Case(workspace_id=ws.id, company_name="Act target (fixture)")
            other = Case(workspace_id=ws.id, company_name="Other target (fixture)")
            session.add_all([alice, bob, case, other])
            await session.commit()
            return {"alice": alice.id, "bob": bob.id, "case": case.id, "other": other.id}
    finally:
        await engine.dispose()


def _postgres_env(url: str) -> Iterator[ActEnv]:
    ids = asyncio.run(_seed(url))
    engine = make_engine(url, poolclass=NullPool)
    sessionmaker = make_sessionmaker(engine)
    yield ActEnv(
        backend="postgres",
        case=str(ids["case"]),
        other_case=str(ids["other"]),
        alice=Actor(user_id=str(ids["alice"]), display_name="Alice Analyst"),
        bob=Actor(user_id=str(ids["bob"]), display_name="Bob Manager"),
        new_repo=lambda: PostgresActRepository(sessionmaker),
    )


@pytest.fixture(params=["memory", "postgres"])
def act(request: pytest.FixtureRequest) -> Iterator[ActEnv]:
    if request.param == "memory":
        yield _memory_env()
        return
    url = request.getfixturevalue("db_url")
    yield from _postgres_env(url)
