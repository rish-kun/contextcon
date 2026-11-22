#!/bin/sh
# Container start: apply database migrations, then serve. A failed migration exits
# non-zero before uvicorn starts, so Cloud Run marks the revision as failed instead
# of serving against an out-of-date schema.
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "entrypoint: alembic upgrade head" >&2
  if ! alembic upgrade head; then
    echo "entrypoint: FATAL: alembic upgrade head failed; not starting the API" >&2
    exit 1
  fi
  echo "entrypoint: migrations applied" >&2
else
  echo "entrypoint: RUN_MIGRATIONS=${RUN_MIGRATIONS}; skipping migrations" >&2
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" \
  --proxy-headers --forwarded-allow-ips='*'
