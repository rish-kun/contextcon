#!/usr/bin/env bash
# Build and deploy DealProof (api + web) to Cloud Run. Idempotent: run it at every
# checkpoint. See docs/deploy.md.
#
#   scripts/deploy.sh                 # deploy the committed HEAD
#   REF=origin/main scripts/deploy.sh # deploy another committed ref
#   ONLY=api scripts/deploy.sh        # api only (ONLY=web for web only)
#
# Builds run on Cloud Build from a `git archive` of REF, so uncommitted files and
# `.env` are never uploaded. Secrets come from Secret Manager at runtime; this
# script never reads or prints them.
set -euo pipefail

PROJECT="${PROJECT:-cc-g527-showproduct}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-dealproof}"
API_SERVICE="${API_SERVICE:-dealproof-api}"
WEB_SERVICE="${WEB_SERVICE:-dealproof-web}"
BUCKET="${BUCKET:-cc-g527-showproduct-dealproof-uploads}"
REF="${REF:-HEAD}"
ONLY="${ONLY:-all}"
# 1 keeps the in-process job worker alive between requests (see docs/deploy.md).
API_MIN_INSTANCES="${API_MIN_INSTANCES:-1}"
API_MEMORY="${API_MEMORY:-512Mi}"
UPLOAD_RETENTION_DAYS="${UPLOAD_RETENTION_DAYS:-30}"

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
SHA="$(git -C "$ROOT" rev-parse --short=12 "$REF")"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

log() { printf '\n==> %s\n' "$*" >&2; }

# Both URL forms Cloud Run serves for a service (deterministic + legacy hash).
service_urls() {
  local svc="$1" status_url
  status_url="$(gcloud run services describe "$svc" --project "$PROJECT" --region "$REGION" \
    --format='value(status.url)' 2>/dev/null || true)"
  local det="https://${svc}-${PROJECT_NUMBER}.${REGION}.run.app"
  if [[ -n "$status_url" && "$status_url" != "$det" ]]; then
    printf '%s,%s' "$det" "$status_url"
  else
    printf '%s' "$det"
  fi
}

SRC_DIR="$(mktemp -d)"
trap 'rm -rf "$SRC_DIR"' EXIT
log "Packaging ${REF} (${SHA}) with git archive"
git -C "$ROOT" archive --format=tar.gz -o "$SRC_DIR/source.tgz" "$REF"

build() { # name dockerfile context [api_url]
  local name="$1" dockerfile="$2" context="$3" api_url="${4:-unused}"
  log "Building ${name}:${SHA} on Cloud Build"
  gcloud builds submit "$SRC_DIR/source.tgz" \
    --project "$PROJECT" --region "$REGION" \
    --config "$ROOT/scripts/cloudbuild.yaml" \
    --substitutions "_IMAGE=${REGISTRY}/${name},_TAG=${SHA},_DOCKERFILE=${dockerfile},_CONTEXT=${context},_API_URL=${api_url}"
}

deploy_api() {
  local web_origin
  web_origin="$(service_urls "$WEB_SERVICE")"
  log "Deploying ${API_SERVICE} (WEB_ORIGIN=${web_origin})"
  # '^@^' switches the env-var delimiter so WEB_ORIGIN can hold a comma.
  gcloud run deploy "$API_SERVICE" \
    --project "$PROJECT" --region "$REGION" \
    --image "${REGISTRY}/api:${SHA}" \
    --service-account "$RUNTIME_SA" \
    --cpu 1 --memory "$API_MEMORY" \
    --min-instances "$API_MIN_INSTANCES" --max-instances 2 \
    --no-cpu-throttling \
    --concurrency 80 --timeout 3600 \
    --allow-unauthenticated \
    --set-env-vars "^@^EMAIL_SEND_ENABLED=false@GCS_BUCKET=${BUCKET}@UPLOAD_RETENTION_DAYS=${UPLOAD_RETENTION_DAYS}@WEB_ORIGIN=${web_origin}" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,CRUSTDATA_API_KEY=CRUSTDATA_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest" \
    --quiet
}

deploy_web() {
  log "Deploying ${WEB_SERVICE}"
  gcloud run deploy "$WEB_SERVICE" \
    --project "$PROJECT" --region "$REGION" \
    --image "${REGISTRY}/web:${SHA}" \
    --service-account "$RUNTIME_SA" \
    --cpu 1 --memory 512Mi \
    --min-instances 0 --max-instances 2 \
    --cpu-throttling \
    --allow-unauthenticated \
    --quiet
}

API_URL="https://${API_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

if [[ "$ONLY" == "all" || "$ONLY" == "api" ]]; then
  build api apps/api/Dockerfile apps/api
  deploy_api
fi

if [[ "$ONLY" == "all" || "$ONLY" == "web" ]]; then
  build web apps/web/Dockerfile . "$API_URL"
  web_existed="$(gcloud run services describe "$WEB_SERVICE" --project "$PROJECT" --region "$REGION" --format='value(metadata.name)' 2>/dev/null || true)"
  deploy_web
  # First deploy: the web URL did not exist when the api was deployed. Fix CORS.
  want_origin="$(service_urls "$WEB_SERVICE")"
  have_origin="$(gcloud run services describe "$API_SERVICE" --project "$PROJECT" --region "$REGION" \
    --format=json | python3 -c 'import json,sys
for e in json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0].get("env", []):
    if e.get("name") == "WEB_ORIGIN": print(e.get("value", ""))')"
  if [[ -z "$web_existed" || "$have_origin" != "$want_origin" ]]; then
    log "Updating ${API_SERVICE} WEB_ORIGIN=${want_origin}"
    gcloud run services update "$API_SERVICE" --project "$PROJECT" --region "$REGION" \
      --update-env-vars "^@^WEB_ORIGIN=${want_origin}" --quiet
  fi
fi

log "Done (${SHA})"
echo "api: ${API_URL}"
echo "web: https://${WEB_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
