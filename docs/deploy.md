# Deploying DealProof

DealProof runs on Cloud Run in GCP project `cc-g527-showproduct`, region `asia-south1` (Mumbai). Postgres is on Neon.

| | URL |
|---|---|
| Web | https://dealproof-web-527967664479.asia-south1.run.app |
| API | https://dealproof-api-527967664479.asia-south1.run.app (`/health`) |

Each service also answers on a legacy `*.a.run.app` URL. The API allows both web URLs in CORS.

## Redeploy

```sh
scripts/deploy.sh                  # build + deploy the committed HEAD (api, then web)
REF=origin/main scripts/deploy.sh  # deploy another committed ref
ONLY=api scripts/deploy.sh         # one service only (ONLY=web for the web app)
```

The script is idempotent. Run it at every checkpoint. It:

1. Packages `REF` with `git archive`. Uncommitted work and `.env` are never uploaded, so **commit before you deploy**.
2. Builds each image on Cloud Build (`scripts/cloudbuild.yaml`; Docker doesn't need to run locally) and pushes it to Artifact Registry, tagged with the git SHA and `latest`.
3. Deploys `dealproof-api`, then builds the web image with `NEXT_PUBLIC_API_URL` set to the API URL and deploys `dealproof-web`.
4. Sets the API's `WEB_ORIGIN` to the web URLs if they changed. This only happens on the first deploy.
5. Prints both URLs.

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

Runtime identity: both services run as the default compute service account `527967664479-compute@developer.gserviceaccount.com`. It has `secretmanager.secretAccessor` on the four secrets and `storage.objectAdmin` on the uploads bucket.

Plain env vars on the API: `EMAIL_SEND_ENABLED=false`, `GCS_BUCKET`, `UPLOAD_RETENTION_DAYS=30`, `WEB_ORIGIN`. Secrets never go into plain env vars or build args. `NEXT_PUBLIC_API_URL` is a public URL, not a secret.

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

- `ANTHROPIC_API_KEY` and `RESEND_API_KEY` hold the value `placeholder` until real keys are added. The repo `.env` had no Anthropic key at deploy time. Set real values with the command above.
- To rotate the Neon password, reset the `dealproof` role password in Neon (console or `reset_postgres_role_password`). Then add the new pooled connection string as a new `DATABASE_URL` version and redeploy the API.
- To turn on real email, add a real `RESEND_API_KEY` version, then change `EMAIL_SEND_ENABLED=true` in `scripts/deploy.sh` and redeploy.

## Logs

```sh
gcloud run services logs read dealproof-api --project cc-g527-showproduct --region asia-south1 --limit 50
gcloud builds list --project cc-g527-showproduct --region asia-south1 --limit 5
```
