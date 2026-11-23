"""Every API route, registered in one place. `app.main` includes `api_router` only.

`app.act.router` (messages: revisions, approval, send once) is implemented by the Act
checkpoint and mounted here as-is; its auth and case-access dependencies fail closed
with 501 until CP-16 wires them through `app.dependency_overrides`.

CP-16 adds the `current_user` dependency at include time here (every router except
`/health`, `/policy` and `/auth/login`).
"""

from fastapi import APIRouter

from app.act import router as act
from app.api import (
    auth,
    cases,
    claims,
    companies,
    decision_flip,
    documents,
    investors,
    policy,
    requests,
    runs,
    showcase,
    theses,
    workspace,
)
from app.api._base import operation_id

api_router = APIRouter()
for module in (
    auth,
    theses,
    investors,
    cases,
    companies,
    decision_flip,
    claims,
    documents,
    requests,
    runs,
    policy,
    showcase,
    workspace,
):
    api_router.include_router(module.router)
api_router.include_router(act.router, generate_unique_id_function=operation_id)
