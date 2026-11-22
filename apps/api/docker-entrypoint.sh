#!/bin/sh
# Container start. RUN_MIGRATIONS picks what happens before uvicorn:
#
#   1       (default, local/dev) `alembic upgrade head`, then serve.
#   only    `alembic upgrade head`, then exit. The Cloud Run migration job uses this
#           with DATABASE_MIGRATION_URL (the schema owner).
#   verify  check that the database is at the latest revision, then serve. The
#           deployed API uses this: it runs as the DML-only role, which cannot migrate.
#   0       serve without touching the schema.
#
# Every failure exits non-zero before uvicorn starts, so Cloud Run marks the revision
# (or job execution) as failed instead of serving against the wrong schema.
# Concurrent upgrades are safe: alembic/env.py takes an advisory lock, so a second
# instance waits and then finds nothing to do.
set -eu

mode="${RUN_MIGRATIONS:-1}"
case "$mode" in
  1 | only)
    echo "entrypoint: alembic upgrade head" >&2
    if ! alembic upgrade head; then
      echo "entrypoint: FATAL: alembic upgrade head failed; not starting the API" >&2
      exit 1
    fi
    echo "entrypoint: migrations applied" >&2
    if [ "$mode" = "only" ]; then
      exit 0
    fi
    ;;
  verify)
    echo "entrypoint: checking the database is at the latest revision" >&2
    if ! alembic current --check-heads; then
      echo "entrypoint: FATAL: database is not at the latest revision (run the migration job); not starting the API" >&2
      exit 1
    fi
    ;;
  0)
    echo "entrypoint: RUN_MIGRATIONS=0; skipping migrations" >&2
    ;;
  *)
    echo "entrypoint: FATAL: unknown RUN_MIGRATIONS=${mode} (use 1, only, verify or 0)" >&2
    exit 1
    ;;
esac

# No proxy-header trust: uvicorn keeps request.client as the TCP peer (Cloud Run's
# front end) and never rewrites it from X-Forwarded-For / X-Forwarded-Proto, which any
# sender can write. FORWARDED_ALLOW_IPS is cleared so it cannot re-enable that.
# The caller's IP for rate limiting is the app's job (app.auth.cookies.client_ip): the
# deployed API sets AUTH_TRUSTED_PROXY_HOPS=2 (scripts/deploy.sh), and the web proxy's
# signed X-DealProof-Proxy header (PROXY_SHARED_SECRET) replaces that once the app
# checks it. Without either, every caller would share the front end's address.
unset FORWARDED_ALLOW_IPS
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" \
  --no-proxy-headers --forwarded-allow-ips ''
