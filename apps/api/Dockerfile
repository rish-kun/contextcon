# DealProof API — Cloud Run image (build context: apps/api)
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini docker-entrypoint.sh ./

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080
# Runs `alembic upgrade head` (fails the start if it fails), then uvicorn on $PORT
# (Cloud Run sets it; 8080 locally). RUN_MIGRATIONS=0 skips the migration step.
CMD ["sh", "/app/docker-entrypoint.sh"]
