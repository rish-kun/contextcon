"""Small builders for test rows."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import Case, DiscoveryRun, Thesis, User, Workspace


@dataclass
class Tenant:
    workspace: Workspace
    user: User
    case: Case


async def tenant(session: AsyncSession, name: str = "acme", **case_fields) -> Tenant:
    ws = await repo.create_workspace(session, name)
    user = await repo.create_user(
        session, ws.id, email=f"{name}-{ws.id.hex[:6]}@example.test", display_name=f"{name} analyst"
    )
    case = await repo.create_case(
        session, ws.id, company_name=f"{name} target (fixture)", created_by=user.id, **case_fields
    )
    await session.commit()
    return Tenant(ws, user, case)


async def discovery_run(session: AsyncSession, t: Tenant) -> DiscoveryRun:
    thesis = Thesis(workspace_id=t.workspace.id, text="fixture thesis", created_by=t.user.id)
    session.add(thesis)
    await session.flush()
    dr = DiscoveryRun(workspace_id=t.workspace.id, thesis_id=thesis.id)
    session.add(dr)
    await session.commit()
    return dr


def days(n: float) -> datetime:
    return datetime.now(UTC) + timedelta(days=n)


IDENTIFY_BODY = [
    {
        "matched_on": "example-logistics.test",
        "match_type": "domain",
        "matches": [
            {
                "confidence_score": 1.0,
                "company_data": {
                    "crustdata_company_id": 4242,
                    "basic_info": {
                        "crustdata_company_id": 4242,
                        "name": "Example Logistics (fixture)",
                        "primary_domain": "example-logistics.test",
                        "year_founded": 2014,
                    },
                },
            }
        ],
    }
]


class FakeCrustdataApi:
    """A real `CrustdataClient` over a mock transport that counts HTTP calls."""

    def __init__(self, credits: str | None = "0.2") -> None:
        self.http_calls = 0
        self.credits = credits

    def client(self, *, recorder, cache):  # type: ignore[no-untyped-def]
        import httpx2

        from app.clients import CrustdataClient, SlidingWindowRateLimiter

        def handle(request: httpx2.Request) -> httpx2.Response:
            self.http_calls += 1
            headers = {"x-request-id": f"req-{self.http_calls}"}
            if self.credits is not None:
                headers["x-credits-used"] = self.credits
            return httpx2.Response(200, json=IDENTIFY_BODY, headers=headers)

        async def no_sleep(_: float) -> None:
            return None

        return CrustdataClient(
            "test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
            recorder=recorder,
            cache=cache,
            rate_limiter=SlidingWindowRateLimiter({}),
            sleep=no_sleep,
            max_retries=0,
        )
