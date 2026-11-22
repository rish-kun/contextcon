"""Helpers shared by the route modules: stub responses and fixture mode.

Until an owner checkpoint fills a handler, it raises 501. With `DEALPROOF_FIXTURES=1`
handlers return canned, contract-valid fixture data instead (fictional companies named
"… (fixture)", and every response carries `X-DealProof-Fixture: 1`). Production never sets
the flag.
"""

import os
from collections.abc import Callable
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.routing import APIRoute

from app.api.schemas.common import ErrorOut

FIXTURE_HEADER = "X-DealProof-Fixture"


def fixtures_enabled() -> bool:
    return os.environ.get("DEALPROOF_FIXTURES", "").strip() == "1"


def _mark_fixture(response: Response) -> None:
    if fixtures_enabled():
        response.headers[FIXTURE_HEADER] = "1"


def operation_id(route: APIRoute) -> str:
    return route.name


COMMON_RESPONSES: dict[int | str, dict] = {
    401: {"model": ErrorOut, "description": "No valid session."},
    404: {"model": ErrorOut, "description": "Not found, or not visible to this user."},
    501: {"model": ErrorOut, "description": "Not implemented yet (stub)."},
}


def make_router(*, tags: list[str], prefix: str = "") -> APIRouter:
    return APIRouter(
        prefix=prefix,
        tags=tags,
        responses=COMMON_RESPONSES,
        dependencies=[Depends(_mark_fixture)],
        generate_unique_id_function=operation_id,
    )


def not_implemented(owner: str) -> NoReturn:
    raise HTTPException(status_code=501, detail=f"Not implemented yet: owned by {owner}.")


def fixture_or_501[T](owner: str, build: Callable[[], T]) -> T:
    """Return fixture data in fixture mode, else raise the 501 stub error."""
    if fixtures_enabled():
        return build()
    not_implemented(owner)


def not_found(what: str) -> NoReturn:
    raise HTTPException(status_code=404, detail=f"{what} not found.")
