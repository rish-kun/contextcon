# Deploying DealProof

DealProof runs on Cloud Run in GCP project `cc-g527-showproduct`, region `asia-south1` (Mumbai). Postgres is on Neon.

| | URL |
|---|---|
| Web | https://dealproof-web-527967664479.asia-south1.run.app |
| API | https://dealproof-api-527967664479.asia-south1.run.app (`/health`) |

Each service also answers on a legacy `*.a.run.app` URL.

The browser only talks to the web origin. Every API call goes to the same-origin proxy `/api/*` (`apps/web/app/api/[...path]/route.ts`), which forwards it server-side to `API_BASE_URL` (for example `/api/health` → `<api>/health`). The `dp_session` cookie is set without a `Domain`, so it stays a first-party cookie on whichever web URL served it. CORS is not involved in this flow; the API still allows both web URLs (`WEB_ORIGIN`) for direct calls.

## Redeploy

```sh
scripts/deploy.sh                  # build + deploy the committed HEAD (api, then web)
REF=origin/main scripts/deploy.sh  # deploy another committed ref
ONLY=api scripts/deploy.sh         # one service only (ONLY=web for the web app)
```

The script is idempotent. Run it at every checkpoint. It:

1. Packages `REF` with `git archive`. Uncommitted work and `.env` are never uploaded, so **commit before you deploy**. `scripts/cloudbuild.yaml` is taken from the same `REF`, not the working tree.
2. Creates the runtime service accounts and their grants if they are missing (see [Runtime identity](#runtime-identity)).
3. Builds each image on Cloud Build (Docker doesn't need to run locally) and pushes it to Artifact Registry, tagged with the git SHA and `latest`. The images take no build args.
4. Deploys `dealproof-api`, then `dealproof-web` with `API_BASE_URL` set to the API URL as a runtime env var.
5. Sets the API's `WEB_ORIGIN` to the web URLs if they changed. This only happens on the first deploy.
6. Once both services run as their own accounts, revokes the secret and bucket grants that earlier deploys gave the default compute account (a no-op after the first time).
7. Prints both URLs.

A deploy takes about 3 minutes: about 35 s for the API build and about 1–1.5 min for the web build.

Requirements: an authenticated `gcloud` and `python3`. Nothing else is installed.

## What exists

| Resource | Name | Notes |
|---|---|---|
| Cloud Run service | `dealproof-api` | 1 vCPU / 512Mi, min 1, max 2, CPU always allocated (`--no-cpu-throttling`), concurrency 80, request timeout 3600 s (for SSE), public |
| Cloud Run service | `dealproof-web` | 1 vCPU / 512Mi, min 0, max 2, CPU only during requests, public |
| Artifact Registry | `asia-south1-docker.pkg.dev/cc-g527-showproduct/dealproof` (images `api`, `web`) | Cleanup policy keeps the 5 most recent versions and deletes others after 1 day |
| GCS bucket | `gs://cc-g527-showproduct-dealproof-uploads` (asia-south1) | Private: uniform access, public access prevention enforced. Lifecycle deletes objects 30 days after upload (`UPLOAD_RETENTION_DAYS`) |
| Secret Manager | `DATABASE_URL`, `ANTHROPIC_API_KEY`, `CRUSTDATA_API_KEY`, `RESEND_API_KEY` | Replicated in asia-south1 only. Mounted as env vars on the API (`:latest`) |
| Neon project | `dealproof` (`lively-term-65597239`), AWS ap-southeast-1 (Singapore, the closest Neon region to Mumbai) | Free plan, 0.25 CU fixed, scales to zero. Database `dealproof`, role `dealproof`. `DATABASE_URL` holds the **pooled** (`-pooler`) connection string |
| Cloud Build staging bucket | `gs://cc-g527-showproduct_cloudbuild` | Created automatically by `gcloud builds submit` and holds uploaded source archives |

### Runtime identity

Each service runs as its own service account. `scripts/deploy.sh` creates both and keeps the grants below in place. IAM policy writes retry with backoff, because two deploys editing the same policy at once get a 409 ("concurrent policy changes").

| Service account | Used by | Grants |
|---|---|---|
| `dealproof-api-sa@cc-g527-showproduct.iam.gserviceaccount.com` | `dealproof-api` | `roles/secretmanager.secretAccessor` on `DATABASE_URL`, `ANTHROPIC_API_KEY`, `CRUSTDATA_API_KEY`, `RESEND_API_KEY` (per secret, not project-wide). `roles/storage.objectAdmin` on `gs://cc-g527-showproduct-dealproof-uploads` only. `roles/iam.serviceAccountTokenCreator` on itself, so it can call `signBlob` for signed download URLs (Cloud Run credentials have no private key) |
| `dealproof-web-sa@cc-g527-showproduct.iam.gserviceaccount.com` | `dealproof-web` | None. The web app holds no secrets and never touches the bucket |

Earlier deploys ran both services as the default compute account `527967664479-compute@developer.gserviceaccount.com` and gave it `secretAccessor` on the four secrets and `objectAdmin` on the uploads bucket. Those five grants have been revoked. The account keeps the project-level `roles/editor` that GCP gives it by default; neither service runs as it, and Cloud Build still uses it to build and push images.

When you add a secret for the API (for example `SESSION_SECRET`), grant `dealproof-api-sa` access to that secret only: add it to `SECRETS` and `--set-secrets` in `scripts/deploy.sh`.

### Env vars

- API (plain): `EMAIL_SEND_ENABLED=false`, `GCS_BUCKET`, `UPLOAD_RETENTION_DAYS=30`, `WEB_ORIGIN`. Secrets come from Secret Manager and never go into plain env vars or build args.
- Web (runtime): `API_BASE_URL`, the API URL the `/api/*` proxy and server components call. It is a public URL, not a secret. Changing it only needs a new revision, not a rebuild. `NEXT_PUBLIC_API_URL` is no longer used by the deploy; the Dockerfile accepts it as an optional build arg for the legacy `lib/api.ts` helper.

The `DATABASE_URL` from Neon includes `sslmode=require&channel_binding=require`. psycopg/libpq accept both. asyncpg does not accept `channel_binding`, so strip it in code if you use asyncpg.

### Why the API uses min-instances 1 with CPU always allocated

The API runs the job worker in-process (spec §5.1), so it has to keep processing steps after the request that started a job has returned. With the default request-based billing, Cloud Run throttles CPU to almost zero between requests, and the worker would freeze. `--no-cpu-throttling` (instance-based billing) keeps CPU on for as long as an instance exists. `min-instances 1` keeps that instance alive when there is no traffic, so queued or long-running jobs keep moving and scheduled rechecks can run.

Cheaper option: `API_MIN_INSTANCES=0 scripts/deploy.sh` keeps CPU always allocated but lets the service scale to zero. An instance then lives for the length of its requests plus up to about 15 idle minutes, and you pay only for that time, roughly $0–5/month at demo traffic. The catch is that a job still running when the instance is reclaimed stops until the next request boots an instance. The worker's lease re-queue (§5.1) resumes it from there, but nothing runs while the service has no traffic. Keep `1` for demos where jobs must finish unattended.

If the API OOMs at 512Mi, use `API_MEMORY=1Gi scripts/deploy.sh`. Memory is about $2.6/month per 512Mi at min 1.

## Monthly cost estimate (USD)

| Item | Estimate |
|---|---|
| `dealproof-api`: 1 vCPU + 0.5 GiB always on, instance-based billing (about $0.000018/vCPU-s and $0.000002/GiB-s), after the Cloud Run free tier | **about $44** (about $49 before the free tier) |
| `dealproof-web`: scales to zero, request-based | about $0 (within the free tier at demo traffic) |
| Neon (free plan) | $0 |
| Artifact Registry (2 images × up to 5 versions, about 1–2 GB) | about $0.10–0.20 |
| GCS uploads, Cloud Build (well inside free minutes), Secret Manager (4 secrets, about 6 versions) | under $0.50 |
| **Total** | **about $45/month**, or about $1–5/month with `API_MIN_INSTANCES=0` |

These are list-price estimates. Check the actual spend in the billing console.

## Rotating or setting a secret

Pipe the value straight from `.env` into a new secret version, without printing it:

```sh
grep '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n' \
  | gcloud secrets versions add ANTHROPIC_API_KEY --project cc-g527-showproduct --data-file=-
ONLY=api scripts/deploy.sh   # new revision so the new :latest value is read
```

Then disable the old version once the new revision is healthy:

```sh
gcloud secrets versions list ANTHROPIC_API_KEY --project cc-g527-showproduct
gcloud secrets versions disable <OLD_VERSION> --secret ANTHROPIC_API_KEY --project cc-g527-showproduct
```

- `ANTHROPIC_API_KEY` holds the real key in version 3. Versions 1 (the old `placeholder`) and 2 are disabled.
- `RESEND_API_KEY` holds the value `placeholder` until a real key is added. Set it with the command above.
- To rotate the Neon password, reset the `dealproof` role password in Neon (console or `reset_postgres_role_password`). Then add the new pooled connection string as a new `DATABASE_URL` version and redeploy the API.
- To turn on real email, add a real `RESEND_API_KEY` version, then change `EMAIL_SEND_ENABLED=true` in `scripts/deploy.sh` and redeploy.

## Logs

```sh
gcloud run services logs read dealproof-api --project cc-g527-showproduct --region asia-south1 --limit 50
gcloud builds list --project cc-g527-showproduct --region asia-south1 --limit 5
```
