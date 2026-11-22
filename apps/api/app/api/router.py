"""Every API route, registered in one place. `app.main` includes `api_router` only.

CP-16 adds the `current_user` dependency at include time here (every router except
`/health`, `/policy` and `/auth/login`).
"""

from fastapi import APIRouter

from app.api import auth, cases, claims, documents, investors, policy, requests, runs, theses

api_router = APIRouter()
for module in (auth, theses, investors, cases, claims, documents, requests, runs, policy):
    api_router.include_router(module.router)
