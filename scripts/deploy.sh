#!/usr/bin/env bash
# Build and deploy DealProof (api + web) to Cloud Run. Idempotent: run it at every
# checkpoint. See docs/deploy.md.
#
#   scripts/deploy.sh                 # deploy the committed HEAD
#   REF=origin/main scripts/deploy.sh # deploy another committed ref
#   ONLY=api scripts/deploy.sh        # api only (ONLY=web for web only)
#   DRY_RUN=1 scripts/deploy.sh       # build (and push) the images, deploy nothing
#
# Order:
#   1. identities and grants (fail-loud policy reads)
#   2. build every selected image, in parallel, as dealproof-build-sa. Nothing deploys
#      until all builds have finished, so a broken build is found before any change.
#   3. api: run the migration job (RUN_MIGRATIONS=only, schema owner), then update the
#      service (RUN_MIGRATIONS=verify, DML-only role). A failed migration skips the
#      api update and leaves the running revision alone.
#   4. web: update the service. Runs whatever happened to the api.
#   5. revoke legacy grants, then verify every policy this script manages.
# The script reports each step and exits non-zero at the end if any failed.
#
# Builds run on Cloud Build from a `git archive` of REF, so uncommitted files and
# `.env` are never uploaded. The Cloud Build config is read from the same REF.
# Secrets come from Secret Manager; this script never reads or prints their values.
set -euo pipefail

PROJECT="${PROJECT:-cc-g527-showproduct}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-dealproof}"
API_SERVICE="${API_SERVICE:-dealproof-api}"
WEB_SERVICE="${WEB_SERVICE:-dealproof-web}"
MIGRATE_JOB="${MIGRATE_JOB:-dealproof-migrate}"
BUCKET="${BUCKET:-cc-g527-showproduct-dealproof-uploads}"
STAGING_BUCKET="${STAGING_BUCKET:-${PROJECT}_cloudbuild}"
REF="${REF:-HEAD}"
ONLY="${ONLY:-all}"
DRY_RUN="${DRY_RUN:-0}"
# 1 keeps the in-process job worker alive between requests (see docs/deploy.md).
API_MIN_INSTANCES="${API_MIN_INSTANCES:-1}"
API_MEMORY="${API_MEMORY:-512Mi}"
UPLOAD_RETENTION_DAYS="${UPLOAD_RETENTION_DAYS:-30}"
# Client IP for rate limiting: the X-Forwarded-For entry this many places from the
# right (web proxy + the API's front end). See app/auth/config.py.
AUTH_TRUSTED_PROXY_HOPS="${AUTH_TRUSTED_PROXY_HOPS:-2}"
# Crustdata credit budgets per case evaluation, discovery run and investor run.
CASE_CREDIT_BUDGET="${CASE_CREDIT_BUDGET:-600}"
DISCOVER_CREDIT_BUDGET="${DISCOVER_CREDIT_BUDGET:-300}"
INVESTOR_CREDIT_BUDGET="${INVESTOR_CREDIT_BUDGET:-300}"

case "$ONLY" in all | api | web) ;; *) echo "ONLY must be all, api or web" >&2; exit 2 ;; esac
want() { [[ "$ONLY" == "all" || "$ONLY" == "$1" ]]; }

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
SHA="$(git -C "$ROOT" rev-parse --short=12 "$REF")"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT"; }
API_SA="$(sa_email "${API_SA_NAME:-dealproof-api-sa}")"
WEB_SA="$(sa_email "${WEB_SA_NAME:-dealproof-web-sa}")"
MIGRATE_SA="$(sa_email "${MIGRATE_SA_NAME:-dealproof-migrate-sa}")"
BUILD_SA="$(sa_email "${BUILD_SA_NAME:-dealproof-build-sa}")"
# Earlier deploys ran both services (and Cloud Build) as this account. Its grants on
# our secrets and bucket are revoked below once no serving revision uses it. Its
# project-level roles/editor is GCP's default and is left alone (docs/deploy.md).
LEGACY_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
# Custom role holding only iam.serviceAccounts.signBlob (signed download URLs).
SIGN_ROLE_ID="dealproofSignBlob"
SIGN_ROLE="projects/${PROJECT}/roles/${SIGN_ROLE_ID}"

# Who may read each secret. Nothing else should hold secretAccessor on these.
API_SECRETS=(DATABASE_URL ANTHROPIC_API_KEY CRUSTDATA_API_KEY RESEND_API_KEY PROXY_SHARED_SECRET)
WEB_SECRETS=(PROXY_SHARED_SECRET)
MIGRATE_SECRETS=(DATABASE_MIGRATION_URL)
ALL_SECRETS=(DATABASE_URL ANTHROPIC_API_KEY CRUSTDATA_API_KEY RESEND_API_KEY PROXY_SHARED_SECRET DATABASE_MIGRATION_URL)
OUR_SAS=("$API_SA" "$WEB_SA" "$MIGRATE_SA" "$BUILD_SA")

log() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
in_list() { local x="$1"; shift; local y; for y in "$@"; do [[ "$x" == "$y" ]] && return 0; done; return 1; }

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

# Read an IAM policy as JSON. A failed read is an error, never "no bindings".
policy() { # kind resource
  local out
  case "$1" in
    secret) out="$(gcloud secrets get-iam-policy "$2" --project "$PROJECT" --format=json)" ;;
    bucket) out="$(gcloud storage buckets get-iam-policy "gs://$2" --format=json)" ;;
    sa) out="$(gcloud iam service-accounts get-iam-policy "$2" --project "$PROJECT" --format=json)" ;;
    repo) out="$(gcloud artifacts repositories get-iam-policy "$2" --project "$PROJECT" --location "$REGION" --format=json)" ;;
    project) out="$(gcloud projects get-iam-policy "$PROJECT" --format=json)" ;;
    *) die "unknown policy kind $1" ;;
  esac || die "could not read the IAM policy of $1 $2"
  [[ -n "$out" ]] || die "empty IAM policy read for $1 $2"
  printf '%s' "$out"
}

# Members holding `role` in a policy (JSON on stdin), one per line.
members_with() { # role
  ROLE="$1" python3 -c 'import json, os, sys
for b in json.load(sys.stdin).get("bindings", []):
    if b["role"] == os.environ["ROLE"] and not b.get("condition"):
        print("\n".join(b.get("members", [])))'
}

# Roles a member holds in a policy (JSON on stdin), one per line.
roles_of() { # member
  MEMBER="$1" python3 -c 'import json, os, sys
for b in json.load(sys.stdin).get("bindings", []):
    if os.environ["MEMBER"] in b.get("members", []):
        print(b["role"])'
}

has_binding() { # kind resource role member
  policy "$1" "$2" | members_with "$3" | grep -qxF "$4"
}

# Create a service account if it does not exist yet.
ensure_sa() { # email display-name
  local name="${1%%@*}"
  if ! gcloud iam service-accounts describe "$1" --project "$PROJECT" >/dev/null 2>&1; then
    log "Creating service account $1"
    gcloud iam service-accounts create "$name" --project "$PROJECT" --display-name "$2" --quiet
    # New accounts take a few seconds to become visible to IAM policy calls.
    for _ in 1 2 3 4 5 6; do
      gcloud iam service-accounts describe "$1" --project "$PROJECT" >/dev/null 2>&1 && break
      sleep 5
    done
  fi
}

# PROXY_SHARED_SECRET: random, generated here and piped straight into Secret Manager.
ensure_proxy_secret() {
  if ! gcloud secrets describe PROXY_SHARED_SECRET --project "$PROJECT" >/dev/null 2>&1; then
    log "Creating PROXY_SHARED_SECRET (random, never printed)"
    python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_urlsafe(48))' \
      | gcloud secrets create PROXY_SHARED_SECRET --project "$PROJECT" \
        --replication-policy user-managed --locations "$REGION" --data-file=- --quiet
  fi
}

ensure_sign_role() {
  local state
  state="$(gcloud iam roles describe "$SIGN_ROLE_ID" --project "$PROJECT" \
    --format='value(deleted,includedPermissions)' 2>/dev/null || true)"
  if [[ -z "$state" ]]; then
    log "Creating custom role ${SIGN_ROLE_ID} (iam.serviceAccounts.signBlob only)"
    gcloud iam roles create "$SIGN_ROLE_ID" --project "$PROJECT" \
      --title "DealProof signBlob" --description "Sign blobs as a service account (signed URLs)" \
      --permissions iam.serviceAccounts.signBlob --stage GA --quiet >/dev/null
    return 0
  elif [[ "$state" == True* ]]; then
    gcloud iam roles undelete "$SIGN_ROLE_ID" --project "$PROJECT" --quiet >/dev/null
  fi
  if [[ "$state" != *$'\t'iam.serviceAccounts.signBlob ]]; then
    gcloud iam roles update "$SIGN_ROLE_ID" --project "$PROJECT" \
      --permissions iam.serviceAccounts.signBlob --quiet >/dev/null
  fi
}

grant_secret() { # secret member-email
  iam_retry gcloud secrets add-iam-policy-binding "$1" --project "$PROJECT" \
    --member "serviceAccount:$2" --role roles/secretmanager.secretAccessor --condition=None --quiet
}

# Least-privilege identities. add-iam-policy-binding is a no-op when the binding
# already exists, so this is safe to run every time. Only the selected services'
# identities are touched: ONLY=web changes nothing that belongs to the API.
ensure_identities() {
  log "Ensuring service accounts, secrets and grants"
  ensure_sa "$BUILD_SA" "DealProof Cloud Build"
  ensure_proxy_secret # both services read it
  local secret

  if want web; then
    ensure_sa "$WEB_SA" "DealProof web runtime"
    for secret in "${WEB_SECRETS[@]}"; do grant_secret "$secret" "$WEB_SA"; done
  fi

  if want api; then
    # DATABASE_MIGRATION_URL holds the schema owner's direct URL; it is created once
    # by hand (docs/deploy.md), never by this script.
    gcloud secrets describe DATABASE_MIGRATION_URL --project "$PROJECT" >/dev/null \
      || die "secret DATABASE_MIGRATION_URL is missing; see docs/deploy.md (Database roles)"
    ensure_sa "$API_SA" "DealProof API runtime"
    ensure_sa "$MIGRATE_SA" "DealProof schema migrations"
    ensure_sign_role
    for secret in "${API_SECRETS[@]}"; do grant_secret "$secret" "$API_SA"; done
    for secret in "${MIGRATE_SECRETS[@]}"; do grant_secret "$secret" "$MIGRATE_SA"; done
    iam_retry gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
      --member "serviceAccount:${API_SA}" --role roles/storage.objectAdmin --quiet
    # Signed download URLs: Cloud Run credentials have no private key, so the API signs
    # through IAM signBlob on its own account. Only that permission, not tokenCreator.
    iam_retry gcloud iam service-accounts add-iam-policy-binding "$API_SA" --project "$PROJECT" \
      --member "serviceAccount:${API_SA}" --role "$SIGN_ROLE" --condition=None --quiet
    if has_binding sa "$API_SA" roles/iam.serviceAccountTokenCreator "serviceAccount:${API_SA}"; then
      log "Replacing ${API_SA}'s self tokenCreator with ${SIGN_ROLE_ID}"
      iam_retry gcloud iam service-accounts remove-iam-policy-binding "$API_SA" --project "$PROJECT" \
        --member "serviceAccount:${API_SA}" --role roles/iam.serviceAccountTokenCreator --quiet
    fi
  fi

  # Cloud Build: push to our repo, write build logs, read the uploaded source.
  iam_retry gcloud artifacts repositories add-iam-policy-binding "$REPO" --project "$PROJECT" \
    --location "$REGION" --member "serviceAccount:${BUILD_SA}" --role roles/artifactregistry.writer --quiet
  iam_retry gcloud projects add-iam-policy-binding "$PROJECT" \
    --member "serviceAccount:${BUILD_SA}" --role roles/logging.logWriter --condition=None --quiet
  iam_retry gcloud storage buckets add-iam-policy-binding "gs://${STAGING_BUCKET}" \
    --member "serviceAccount:${BUILD_SA}" --role roles/storage.objectViewer --quiet
}

# Service accounts of a service's template and of every revision serving traffic.
serving_identities() { # service
  local svc="$1" json revs rev sa
  json="$(gcloud run services describe "$svc" --project "$PROJECT" --region "$REGION" --format=json)" \
    || die "could not describe ${svc}"
  revs="$(printf '%s' "$json" | python3 -c 'import json, sys
s = json.load(sys.stdin)
print("TEMPLATE", s["spec"]["template"]["spec"].get("serviceAccountName", ""))
for t in s.get("status", {}).get("traffic", []):
    if t.get("percent", 0) > 0:
        print("REVISION", t.get("revisionName") or s["status"]["latestReadyRevisionName"])')"
  while read -r kind rev; do
    if [[ "$kind" == TEMPLATE ]]; then
      printf '%s\n' "${rev:-<default>}"
    else
      sa="$(gcloud run revisions describe "$rev" --project "$PROJECT" --region "$REGION" \
        --format='value(spec.serviceAccountName)')" || die "could not describe revision ${rev}"
      printf '%s\n' "${sa:-<default>}"
    fi
  done <<<"$revs"
}

LEGACY_REVOKED=0
# Revoke what earlier deploys gave the default compute account, once neither service's
# template nor any traffic-serving revision runs as it.
revoke_legacy_grants() {
  local svc ids
  for svc in "$API_SERVICE" "$WEB_SERVICE"; do
    ids="$(serving_identities "$svc")"
    if grep -qxF -e "$LEGACY_SA" -e "<default>" <<<"$ids"; then
      log "Keeping legacy grants: ${svc} still serves traffic as the default compute account"
      return 0
    fi
  done
  local secret
  for secret in "${ALL_SECRETS[@]}"; do
    if has_binding secret "$secret" roles/secretmanager.secretAccessor "serviceAccount:${LEGACY_SA}"; then
      log "Revoking ${secret} access from ${LEGACY_SA}"
      iam_retry gcloud secrets remove-iam-policy-binding "$secret" --project "$PROJECT" \
        --member "serviceAccount:${LEGACY_SA}" --role roles/secretmanager.secretAccessor --quiet
    fi
  done
  if has_binding bucket "$BUCKET" roles/storage.objectAdmin "serviceAccount:${LEGACY_SA}"; then
    log "Revoking gs://${BUCKET} objectAdmin from ${LEGACY_SA}"
    iam_retry gcloud storage buckets remove-iam-policy-binding "gs://${BUCKET}" \
      --member "serviceAccount:${LEGACY_SA}" --role roles/storage.objectAdmin --quiet
  fi
  set_result legacy-revoked yes
}

# Check every policy this script manages ends up exactly as intended.
verify_iam() {
  log "Verifying IAM policies"
  local bad=0 secret sa expected members p
  fail() { printf '  FAIL: %s\n' "$*" >&2; bad=1; }
  for secret in "${ALL_SECRETS[@]}"; do
    expected=("")  # never empty: bash 3.2 treats "${a[@]}" of () as unset
    in_list "$secret" "${API_SECRETS[@]}" && expected+=("$API_SA")
    in_list "$secret" "${WEB_SECRETS[@]}" && expected+=("$WEB_SA")
    in_list "$secret" "${MIGRATE_SECRETS[@]}" && expected+=("$MIGRATE_SA")
    members="$(policy secret "$secret" | members_with roles/secretmanager.secretAccessor)"
    for sa in "${OUR_SAS[@]}" "$LEGACY_SA"; do
      if in_list "$sa" "${expected[@]}"; then
        grep -qxF "serviceAccount:${sa}" <<<"$members" || fail "${sa} cannot read ${secret}"
      elif grep -qxF "serviceAccount:${sa}" <<<"$members"; then
        [[ "$sa" == "$LEGACY_SA" && "$LEGACY_REVOKED" == 0 ]] || fail "${sa} can read ${secret}"
      fi
    done
  done

  p="$(policy bucket "$BUCKET")"
  [[ "$(roles_of "serviceAccount:${API_SA}" <<<"$p")" == "roles/storage.objectAdmin" ]] \
    || fail "${API_SA} should hold only objectAdmin on gs://${BUCKET}"
  for sa in "$WEB_SA" "$MIGRATE_SA" "$BUILD_SA"; do
    [[ -z "$(roles_of "serviceAccount:${sa}" <<<"$p")" ]] || fail "${sa} has roles on gs://${BUCKET}"
  done
  if [[ "$LEGACY_REVOKED" == 1 && -n "$(roles_of "serviceAccount:${LEGACY_SA}" <<<"$p")" ]]; then
    fail "${LEGACY_SA} still has roles on gs://${BUCKET}"
  fi

  p="$(policy sa "$API_SA")"
  [[ "$(roles_of "serviceAccount:${API_SA}" <<<"$p")" == "$SIGN_ROLE" ]] \
    || fail "${API_SA} should hold only ${SIGN_ROLE_ID} on itself"
  [[ "$(gcloud iam roles describe "$SIGN_ROLE_ID" --project "$PROJECT" --format='value(includedPermissions)')" \
    == "iam.serviceAccounts.signBlob" ]] || fail "${SIGN_ROLE_ID} should contain only signBlob"

  p="$(policy repo "$REPO")"
  [[ "$(roles_of "serviceAccount:${BUILD_SA}" <<<"$p")" == "roles/artifactregistry.writer" ]] \
    || fail "${BUILD_SA} should hold only artifactregistry.writer on ${REPO}"
  p="$(policy bucket "$STAGING_BUCKET")"
  [[ "$(roles_of "serviceAccount:${BUILD_SA}" <<<"$p")" == "roles/storage.objectViewer" ]] \
    || fail "${BUILD_SA} should hold only objectViewer on gs://${STAGING_BUCKET}"

  p="$(policy project "")"
  [[ "$(roles_of "serviceAccount:${BUILD_SA}" <<<"$p")" == "roles/logging.logWriter" ]] \
    || fail "${BUILD_SA} should hold only logging.logWriter on the project"
  for sa in "$API_SA" "$WEB_SA" "$MIGRATE_SA"; do
    [[ -z "$(roles_of "serviceAccount:${sa}" <<<"$p")" ]] || fail "${sa} has project-level roles"
  done

  [[ "$bad" == 0 ]] || return 1
  printf '  ok: secrets, uploads bucket, signBlob role, Artifact Registry, staging bucket, project roles\n' >&2
}

SRC_DIR="$(mktemp -d)"
trap 'rm -rf "$SRC_DIR"' EXIT
git -C "$ROOT" archive --format=tar.gz -o "$SRC_DIR/source.tgz" "$REF"
# Use the build config from the same commit as the source, not the working tree.
git -C "$ROOT" show "${REF}:scripts/cloudbuild.yaml" >"$SRC_DIR/cloudbuild.yaml"

# Start one Cloud Build in the background, logging to a file. Call it in the main
# shell (not in $(...)) so `wait` can collect it; the PID is in $!.
start_build() { # name dockerfile context
  local name="$1"
  gcloud builds submit "$SRC_DIR/source.tgz" \
    --project "$PROJECT" --region "$REGION" \
    --config "$SRC_DIR/cloudbuild.yaml" \
    --service-account "projects/${PROJECT}/serviceAccounts/${BUILD_SA}" \
    --substitutions "_IMAGE=${REGISTRY}/${name},_TAG=${SHA},_DOCKERFILE=$2,_CONTEXT=$3" \
    >"$SRC_DIR/build-${name}.log" 2>&1 &
}

wait_build() { # name pid
  if wait "$2"; then
    log "Built ${1}:${SHA}"
    return 0
  fi
  log "Build ${1}:${SHA} FAILED. Last lines of its log:"
  tail -n 40 "$SRC_DIR/build-${1}.log" >&2
  return 1
}

# Step results live in files so steps run in subshells can record them too.
result() { cat "$SRC_DIR/result-$1" 2>/dev/null || true; }
set_result() { echo "$2" >"$SRC_DIR/result-$1"; }

# Run a step in a subshell with errexit, record its result, never abort the script.
step() { # name function...
  local name="$1" rc
  shift
  set +e
  (set -e; "$@")
  rc=$?
  set -e
  set_result "$name" "$([[ $rc == 0 ]] && echo ok || echo FAILED)"
  return 0
}

API_URL="https://${API_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
WEB_URLS="https://${WEB_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

# Both URL forms Cloud Run serves for the web service (deterministic + legacy hash).
web_origins() {
  local status_url
  status_url="$(gcloud run services describe "$WEB_SERVICE" --project "$PROJECT" --region "$REGION" \
    --format='value(status.url)' 2>/dev/null || true)"
  if [[ -n "$status_url" && "$status_url" != "$WEB_URLS" ]]; then
    printf '%s,%s' "$WEB_URLS" "$status_url"
  else
    printf '%s' "$WEB_URLS"
  fi
}

migrate() {
  log "Migrating the database with job ${MIGRATE_JOB} (api:${SHA}, ${MIGRATE_SA})"
  gcloud run jobs deploy "$MIGRATE_JOB" \
    --project "$PROJECT" --region "$REGION" \
    --image "${REGISTRY}/api:${SHA}" \
    --service-account "$MIGRATE_SA" \
    --cpu 1 --memory 512Mi \
    --tasks 1 --parallelism 1 --max-retries 0 --task-timeout 900s \
    --set-env-vars "RUN_MIGRATIONS=only" \
    --set-secrets "DATABASE_MIGRATION_URL=DATABASE_MIGRATION_URL:latest" \
    --quiet >/dev/null
  # The job's own migration lock and lock_timeout/retry (alembic/env.py) let it run
  # next to the live API, whose worker holds row locks on runs/steps.
  gcloud run jobs execute "$MIGRATE_JOB" --project "$PROJECT" --region "$REGION" --wait --quiet
}

deploy_api() {
  local origins
  origins="$(web_origins)"
  log "Deploying ${API_SERVICE} (WEB_ORIGIN=${origins})"
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
    --set-env-vars "^@^RUN_MIGRATIONS=verify@AUTH_TRUSTED_PROXY_HOPS=${AUTH_TRUSTED_PROXY_HOPS}@EMAIL_SEND_ENABLED=false@GCS_BUCKET=${BUCKET}@UPLOAD_RETENTION_DAYS=${UPLOAD_RETENTION_DAYS}@CASE_CREDIT_BUDGET=${CASE_CREDIT_BUDGET}@DISCOVER_CREDIT_BUDGET=${DISCOVER_CREDIT_BUDGET}@INVESTOR_CREDIT_BUDGET=${INVESTOR_CREDIT_BUDGET}@WEB_ORIGIN=${origins}" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,CRUSTDATA_API_KEY=CRUSTDATA_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest,PROXY_SHARED_SECRET=PROXY_SHARED_SECRET:latest" \
    --quiet
}

api_pipeline() {
  [[ "$(result build-api)" == ok ]] || { log "Skipping api: its build failed"; return 1; }
  step migrate migrate
  [[ "$(result migrate)" == ok ]] || { log "Skipping the api update: migration failed; the running revision is unchanged"; return 1; }
  deploy_api
}

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
    --update-secrets "PROXY_SHARED_SECRET=PROXY_SHARED_SECRET:latest" \
    --quiet
}

# If the web URLs changed (first deploy), point the API's CORS at them. Only touches
# an API whose template already runs RUN_MIGRATIONS=verify, so a new revision built
# from an old template can never migrate at start.
api_env() { # name: a plain env var from the API's template ("-" if unset)
  gcloud run services describe "$API_SERVICE" --project "$PROJECT" --region "$REGION" \
    --format=json | NAME="$1" python3 -c 'import json, os, sys
env = {e["name"]: e.get("value", "") for e in json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0].get("env", [])}
print(env.get(os.environ["NAME"], "") or "-")'
}
api_web_origin() { api_env WEB_ORIGIN; }

fix_api_origin() {
  local want have run_mode
  want="$(web_origins)"
  have="$(api_web_origin)"
  run_mode="$(api_env RUN_MIGRATIONS)"
  [[ "$have" == "$want" ]] && return 0
  if [[ "$run_mode" != verify ]]; then
    log "Not updating ${API_SERVICE} WEB_ORIGIN: its template still migrates at start; redeploy the api"
    return 1
  fi
  log "Updating ${API_SERVICE} WEB_ORIGIN=${want}"
  gcloud run services update "$API_SERVICE" --project "$PROJECT" --region "$REGION" \
    --update-env-vars "^@^WEB_ORIGIN=${want}" --quiet
}

web_pipeline() {
  [[ "$(result build-web)" == ok ]] || { log "Skipping web: its build failed"; return 1; }
  deploy_web
  # Updating WEB_ORIGIN creates an API revision, so only when the API is selected too.
  if want api; then
    step api-origin fix_api_origin
  elif [[ "$(api_web_origin)" != "$(web_origins)" ]]; then
    log "Note: ${API_SERVICE} WEB_ORIGIN differs from the web URLs; run ONLY=api scripts/deploy.sh"
  fi
}

# ---------------------------------------------------------------------------------
log "Deploying ${REF} (${SHA}), ONLY=${ONLY}, DRY_RUN=${DRY_RUN}"
ensure_identities

log "Building images on Cloud Build as ${BUILD_SA} (logs only in Cloud Logging)"
if want api; then start_build api apps/api/Dockerfile apps/api; api_pid=$!; fi
if want web; then start_build web apps/web/Dockerfile .; web_pid=$!; fi
# `wait` must run in this shell (the builds are its children), not inside step().
if want api; then
  if wait_build api "$api_pid"; then set_result build-api ok; else set_result build-api FAILED; fi
fi
if want web; then
  if wait_build web "$web_pid"; then set_result build-web ok; else set_result build-web FAILED; fi
fi

if [[ "$DRY_RUN" != 1 ]]; then
  if want api; then step api api_pipeline; fi
  if want web; then step web web_pipeline; fi
  step iam-legacy revoke_legacy_grants
fi
# revoke_legacy_grants ran in a subshell; it records whether it revoked.
if [[ "$(result legacy-revoked)" == yes ]]; then LEGACY_REVOKED=1; fi
step iam-verify verify_iam

log "Summary (${SHA})"
status=0
for name in build-api build-web migrate api web api-origin iam-legacy iam-verify; do
  r="$(result "$name")"
  [[ -n "$r" ]] || continue
  printf '  %-11s %s\n' "$name" "$r"
  [[ "$r" == ok ]] || status=1
done
echo "api: ${API_URL}"
echo "web: ${WEB_URLS}"
exit "$status"
