#!/usr/bin/env bash
# Build and deploy DealProof (api + web) to Cloud Run. Idempotent: run it at every
# checkpoint. See docs/deploy.md.
#
#   scripts/deploy.sh                 # deploy the committed HEAD
#   REF=origin/main scripts/deploy.sh # deploy another committed ref
#   ONLY=api scripts/deploy.sh        # api only (ONLY=web for web only)
#
# Builds run on Cloud Build from a `git archive` of REF, so uncommitted files and
# `.env` are never uploaded. The Cloud Build config is read from the same REF.
# Secrets come from Secret Manager at runtime; this script never reads or prints them.
#
# Each service runs as its own service account (created here if missing):
#   dealproof-api-sa  secretAccessor on the four secrets, objectAdmin on the uploads
#                     bucket, tokenCreator on itself (signBlob for signed URLs)
#   dealproof-web-sa  no roles at all
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
API_SA_NAME="${API_SA_NAME:-dealproof-api-sa}"
WEB_SA_NAME="${WEB_SA_NAME:-dealproof-web-sa}"
API_SA="${API_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
WEB_SA="${WEB_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
# Earlier deploys ran both services as this account and granted it the secrets and the
# bucket. Those grants are revoked below once neither service uses it.
LEGACY_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
SECRETS=(DATABASE_URL ANTHROPIC_API_KEY CRUSTDATA_API_KEY RESEND_API_KEY)

log() { printf '\n==> %s\n' "$*" >&2; }

# IAM policy writes are read-modify-write and fail with 409 ("concurrent policy
# changes") when another deploy edits the same policy. Every call wrapped here is
# idempotent, so retry any failure with backoff.
iam_retry() {
  local attempt delay=2
  for attempt in 1 2 3 4 5 6; do
    if "$@" >/dev/null; then return 0; fi
    [[ $attempt -eq 6 ]] && break
    log "IAM call failed (attempt ${attempt}), retrying in ${delay}s"
    sleep "$delay"
    delay=$((delay * 2))
  done
  return 1
}

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

# Create a service account if it does not exist yet.
ensure_sa() { # name display-name
  local email="$1@${PROJECT}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "$email" --project "$PROJECT" >/dev/null 2>&1; then
    log "Creating service account ${email}"
    gcloud iam service-accounts create "$1" --project "$PROJECT" --display-name "$2" --quiet
    # New accounts take a few seconds to become visible to IAM policy calls.
    for _ in 1 2 3 4 5 6; do
      gcloud iam service-accounts describe "$email" --project "$PROJECT" >/dev/null 2>&1 && break
      sleep 5
    done
  fi
}

# Least-privilege runtime identities. add-iam-policy-binding is a no-op when the
# binding already exists, so this is safe to run every time.
ensure_runtime_identities() {
  log "Ensuring runtime service accounts and grants"
  ensure_sa "$API_SA_NAME" "DealProof API runtime"
  ensure_sa "$WEB_SA_NAME" "DealProof web runtime"
  local secret
  for secret in "${SECRETS[@]}"; do
    iam_retry gcloud secrets add-iam-policy-binding "$secret" --project "$PROJECT" \
      --member "serviceAccount:${API_SA}" --role roles/secretmanager.secretAccessor \
      --condition=None --quiet
  done
  iam_retry gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member "serviceAccount:${API_SA}" --role roles/storage.objectAdmin --quiet
  # Signed download URLs: Cloud Run credentials have no private key, so the API signs
  # through the IAM signBlob call on its own account.
  iam_retry gcloud iam service-accounts add-iam-policy-binding "$API_SA" --project "$PROJECT" \
    --member "serviceAccount:${API_SA}" --role roles/iam.serviceAccountTokenCreator \
    --condition=None --quiet
}

# Revoke the grants earlier deploys gave the default compute account, once neither
# service runs as it. Only these five bindings; the account's other roles are untouched.
revoke_legacy_grants() {
  local svc sa
  for svc in "$API_SERVICE" "$WEB_SERVICE"; do
    sa="$(gcloud run services describe "$svc" --project "$PROJECT" --region "$REGION" \
      --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
    if [[ -z "$sa" || "$sa" == "$LEGACY_SA" ]]; then return 0; fi
  done
  local secret
  for secret in "${SECRETS[@]}"; do
    if gcloud secrets get-iam-policy "$secret" --project "$PROJECT" \
      --flatten=bindings --filter="bindings.role=roles/secretmanager.secretAccessor AND bindings.members:serviceAccount:${LEGACY_SA}" \
      --format='value(bindings.role)' 2>/dev/null | grep -q .; then
      log "Revoking ${secret} access from ${LEGACY_SA}"
      iam_retry gcloud secrets remove-iam-policy-binding "$secret" --project "$PROJECT" \
        --member "serviceAccount:${LEGACY_SA}" --role roles/secretmanager.secretAccessor --quiet
    fi
  done
  # `gcloud storage` has no --filter, so check the policy JSON instead.
  if gcloud storage buckets get-iam-policy "gs://${BUCKET}" --format=json 2>/dev/null \
    | LEGACY_SA="$LEGACY_SA" python3 -c 'import json,os,sys
m = "serviceAccount:" + os.environ["LEGACY_SA"]
sys.exit(0 if any(b["role"] == "roles/storage.objectAdmin" and m in b.get("members", [])
                  for b in json.load(sys.stdin).get("bindings", [])) else 1)'; then
    log "Revoking gs://${BUCKET} objectAdmin from ${LEGACY_SA}"
    iam_retry gcloud storage buckets remove-iam-policy-binding "gs://${BUCKET}" \
      --member "serviceAccount:${LEGACY_SA}" --role roles/storage.objectAdmin --quiet
  fi
}

SRC_DIR="$(mktemp -d)"
trap 'rm -rf "$SRC_DIR"' EXIT
log "Packaging ${REF} (${SHA}) with git archive"
git -C "$ROOT" archive --format=tar.gz -o "$SRC_DIR/source.tgz" "$REF"
# Use the build config from the same commit as the source, not the working tree.
git -C "$ROOT" show "${REF}:scripts/cloudbuild.yaml" > "$SRC_DIR/cloudbuild.yaml"

build() { # name dockerfile context
  local name="$1" dockerfile="$2" context="$3"
  log "Building ${name}:${SHA} on Cloud Build"
  gcloud builds submit "$SRC_DIR/source.tgz" \
    --project "$PROJECT" --region "$REGION" \
    --config "$SRC_DIR/cloudbuild.yaml" \
    --substitutions "_IMAGE=${REGISTRY}/${name},_TAG=${SHA},_DOCKERFILE=${dockerfile},_CONTEXT=${context}"
}

deploy_api() {
  local web_origin
  web_origin="$(service_urls "$WEB_SERVICE")"
  log "Deploying ${API_SERVICE} (WEB_ORIGIN=${web_origin})"
  # '^@^' switches the env-var delimiter so WEB_ORIGIN can hold a comma.
  gcloud run deploy "$API_SERVICE" \
    --project "$PROJECT" --region "$REGION" \
    --image "${REGISTRY}/api:${SHA}" \
    --service-account "$API_SA" \
    --cpu 1 --memory "$API_MEMORY" \
    --min-instances "$API_MIN_INSTANCES" --max-instances 2 \
    --no-cpu-throttling \
    --concurrency 80 --timeout 3600 \
    --allow-unauthenticated \
    --set-env-vars "^@^EMAIL_SEND_ENABLED=false@GCS_BUCKET=${BUCKET}@UPLOAD_RETENTION_DAYS=${UPLOAD_RETENTION_DAYS}@WEB_ORIGIN=${web_origin}" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,CRUSTDATA_API_KEY=CRUSTDATA_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest" \
    --quiet
}

API_URL="https://${API_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

deploy_web() {
  # The browser only calls the web origin; the /api/* proxy forwards server-side to
  # API_BASE_URL, which is read at runtime (not baked into the image).
  log "Deploying ${WEB_SERVICE} (API_BASE_URL=${API_URL})"
  gcloud run deploy "$WEB_SERVICE" \
    --project "$PROJECT" --region "$REGION" \
    --image "${REGISTRY}/web:${SHA}" \
    --service-account "$WEB_SA" \
    --cpu 1 --memory 512Mi \
    --min-instances 0 --max-instances 2 \
    --cpu-throttling \
    --allow-unauthenticated \
    --update-env-vars "API_BASE_URL=${API_URL}" \
    --quiet
}

ensure_runtime_identities

if [[ "$ONLY" == "all" || "$ONLY" == "api" ]]; then
  build api apps/api/Dockerfile apps/api
  deploy_api
fi

if [[ "$ONLY" == "all" || "$ONLY" == "web" ]]; then
  build web apps/web/Dockerfile .
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

revoke_legacy_grants

log "Done (${SHA})"
echo "api: ${API_URL}"
echo "web: https://${WEB_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
