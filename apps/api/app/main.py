from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.jobs.lifespan import jobs_lifespan
from app.runtime import check_startup, is_production
from app.settings import get_settings


def create_app() -> FastAPI:
    check_startup()
    settings = get_settings()
    # No interactive docs or live schema in production. `app.openapi()` still works, so
    # `python -m app.api.export_openapi` keeps writing the committed `openapi.json`.
    docs = not is_production()
    app = FastAPI(
        title="DealProof API",
        version="0.1.0",
        lifespan=jobs_lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
