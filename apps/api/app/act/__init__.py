"""Act step: approve a seller request, then send it exactly once.

Public API: `ActService` (service.py), `ActRepository` / `InMemoryActRepository`
(repository.py), `PostgresActRepository` (pg_repository.py), `ResendClient`
(resend.py) and `router` (router.py, mounted by `app.api.router`).
"""
