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
scripts/deploy.sh                  # build + deploy the committed HEAD (api and web)
REF=origin/main scripts/deploy.sh  # deploy another committed ref
ONLY=api scripts/deploy.sh         # one service only (ONLY=web for the web app)
DRY_RUN=1 scripts/deploy.sh        # build (and push) the images, deploy nothing
```

`ONLY=web` changes nothing that belongs to the API: it does not check the migration secret, add API or migration grants, run the migration job, or update the API's `WEB_ORIGIN` (it only prints a note if that is out of date). It still reads every policy for the final check.

The script is idempotent. Run it at every checkpoint. It:

1. Packages `REF` with `git archive`. Uncommitted work and `.env` are never uploaded, so **commit before you deploy**. `scripts/cloudbuild.yaml` is taken from the same `REF`, not the working tree.
2. Creates the service accounts, the `PROXY_SHARED_SECRET` secret and the `dealproofSignBlob` custom role if they are missing, and adds the grants in [Identities](#identities). Every IAM policy read fails the script if it fails; nothing is ever treated as "no binding" because a read went wrong.
3. Builds **every selected image before deploying anything**, in parallel, on Cloud Build as `dealproof-build-sa`. The images are tagged with the git SHA and `latest` and take no build args. A broken build is found before any service changes. `DRY_RUN=1` stops here (after the IAM check in step 7).
4. **api**: runs the Cloud Run job `dealproof-migrate` with the new image (`RUN_MIGRATIONS=only`, as `dealproof-migrate-sa`, with `DATABASE_MIGRATION_URL`), waits for it, and only then deploys `dealproof-api` with `RUN_MIGRATIONS=verify`. A failed migration skips the API update and leaves the running revision as it was. See [Migrations](#migrations).
5. **web**: deploys `dealproof-web` with `API_BASE_URL` set to the API URL. This runs whatever happened to the API. If the web URLs changed (first deploy only), it also points the API's `WEB_ORIGIN` at them, but only when the API's template already runs `RUN_MIGRATIONS=verify`.
6. Revokes the secret and bucket grants earlier deploys gave the default compute account, once neither service's template **nor any revision serving traffic** runs as it.
7. Verifies every IAM policy it manages (see [Identities](#identities)) and fails if one differs.
8. Prints a summary line per step (`build-api`, `build-web`, `migrate`, `api`, `web`, `api-origin`, `iam-legacy`, `iam-verify`) and the URLs. It exits non-zero if any step failed, but only after attempting all of them, so an API failure never stops web from shipping.

A deploy takes about 4 minutes: the two builds run together (about 1–1.5 min), the migration job about 30 s, then each service update.

Requirements: an authenticated `gcloud` and `python3`. Nothing else is installed.

## What exists

| Resource | Name | Notes |
|---|---|---|
| Cloud Run service | `dealproof-api` | 2 vCPU / 4Gi, min 1, max 4, CPU always allocated (`--no-cpu-throttling`), concurrency 80, request timeout 3600 s (for SSE), public |
| Cloud Run service | `dealproof-web` | 2 vCPU / 2Gi, min 1, max 2, CPU only during requests, public |
| Cloud Run job | `dealproof-migrate` | The API image with `RUN_MIGRATIONS=only`: one task, no retries, 15 min timeout. Updated and run by every API deploy |
| Artifact Registry | `asia-south1-docker.pkg.dev/cc-g527-showproduct/dealproof` (images `api`, `web`) | Cleanup policy keeps the 5 most recent versions and deletes others after 1 day |
| GCS bucket | `gs://cc-g527-showproduct-dealproof-uploads` (asia-south1) | Private: uniform access, public access prevention enforced. Lifecycle deletes objects 30 days after upload (`UPLOAD_RETENTION_DAYS`) |
| Secret Manager | `DATABASE_URL`, `ANTHROPIC_API_KEY`, `CRUSTDATA_API_KEY`, `RESEND_API_KEY`, `PROXY_SHARED_SECRET`, `DATABASE_MIGRATION_URL` | Replicated in asia-south1 only. Mounted as env vars (`:latest`): the API gets the first five, the web app only `PROXY_SHARED_SECRET`, the migration job only `DATABASE_MIGRATION_URL` |
| Neon project | `dealproof` (`lively-term-65597239`), AWS ap-southeast-1 (Singapore, the closest Neon region to Mumbai) | Free plan, 0.25 CU fixed, scales to zero. Database `dealproof`, Postgres 18. Two roles, see [Database roles](#database-roles) |
| Cloud Build staging bucket | `gs://cc-g527-showproduct_cloudbuild` | Created automatically by `gcloud builds submit` and holds uploaded source archives |
| Custom IAM role | `projects/cc-g527-showproduct/roles/dealproofSignBlob` | Only `iam.serviceAccounts.signBlob` |

### Identities

Every workload runs as its own service account. `scripts/deploy.sh` creates them, keeps exactly the grants below in place, and checks them at the end of every run. IAM policy writes retry with backoff, because two deploys editing the same policy at once get a 409 ("concurrent policy changes").

| Service account | Used by | Grants (nothing else) |
|---|---|---|
| `dealproof-api-sa` | `dealproof-api` | `roles/secretmanager.secretAccessor` on `DATABASE_URL`, `ANTHROPIC_API_KEY`, `CRUSTDATA_API_KEY`, `RESEND_API_KEY`, `PROXY_SHARED_SECRET` (per secret). `roles/storage.objectAdmin` on the uploads bucket only. `dealproofSignBlob` on itself, so it can call `signBlob` for signed download URLs (Cloud Run credentials have no private key). This replaced `roles/iam.serviceAccountTokenCreator`, which also allowed minting access and ID tokens |
| `dealproof-web-sa` | `dealproof-web` | `secretAccessor` on `PROXY_SHARED_SECRET` only |
| `dealproof-migrate-sa` | `dealproof-migrate` job | `secretAccessor` on `DATABASE_MIGRATION_URL` only. Nothing else can read that secret |
| `dealproof-build-sa` | Cloud Build (`gcloud builds submit --service-account`) | `roles/artifactregistry.writer` on the `dealproof` repository, `roles/logging.logWriter` on the project (the only level it exists at), `roles/storage.objectViewer` on the staging bucket (to read the uploaded source) |

All four accounts are `@cc-g527-showproduct.iam.gserviceaccount.com`. None has a project-level role except the build account's `logWriter`.

Builds with a user-chosen service account must send their logs somewhere other than the default logs bucket; `scripts/cloudbuild.yaml` sets `options.logging: CLOUD_LOGGING_ONLY`. `gcloud builds submit` therefore prints no build log; on a failure, `deploy.sh` prints the tail of gcloud's output, and the full log is in Cloud Logging (`gcloud builds log <id> --region asia-south1`).

**The default compute account** `527967664479-compute@developer.gserviceaccount.com` keeps the project-level `roles/editor` GCP gives it. Nothing of ours runs as it any more: not the services, not the job, not Cloud Build. Leave that role alone. GCP manages it, other Google services may rely on it, and removing it can break them in ways that are hard to trace. Earlier deploys also gave it `secretAccessor` on the four original secrets and `objectAdmin` on the uploads bucket; `deploy.sh` revokes those once no template or serving revision runs as it.

When you add a secret for the API (for example `SESSION_SECRET`), add it to `API_SECRETS` and `ALL_SECRETS` and to `--set-secrets` in `scripts/deploy.sh`. The verification step then expects exactly `dealproof-api-sa` to read it.

### Database roles

| Role | Used by | Secret | Host | Privileges |
|---|---|---|---|---|
| `dealproof` | migrations only (the `dealproof-migrate` job) | `DATABASE_MIGRATION_URL` | direct (no `-pooler`) | Owns the schema. Created by Neon, so it is a member of `neon_superuser` |
| `dealproof_app` | the API at runtime | `DATABASE_URL` | pooled (`-pooler`) | `SELECT, INSERT, UPDATE, DELETE` on every table, `USAGE` on sequences, read-only `alembic_version`, and the same on tables later migrations create (default privileges). No DDL, `TRUNCATE`, `TRIGGER` or `REFERENCES`, no role memberships |

The grants are in [`scripts/db/app-role-grants.sql`](../scripts/db/app-role-grants.sql). The API test suite runs every database test as a role holding exactly those grants, so app code that needs more (DDL, `TRUNCATE`, disabling a trigger) fails in tests rather than in production. The immutability triggers still fire for `dealproof_app`, and the retention purge works with it: it only deletes rows, and the opt-in `SET LOCAL dealproof.retention_delete = 'on'` needs no extra privilege.

`dealproof_app` was created with SQL rather than the Neon API, so Neon did not make it a member of `neon_superuser`. To create it, or to give it a new password, run this as the owner. The URL goes from one pipe to the next and is never printed:

```sh
gcloud secrets versions access latest --secret DATABASE_MIGRATION_URL --project cc-g527-showproduct \
  | uv run --project apps/api python scripts/db/provision-app-role.py \
  | gcloud secrets versions add DATABASE_URL --project cc-g527-showproduct --data-file=-
ONLY=api scripts/deploy.sh   # the running revision keeps the old password until replaced
```

The script applies the grants, refuses to run before the schema exists, checks that the role has no extra attributes or memberships, connects as it through the pooler with full TLS verification, and checks that DDL is refused. A new password stops the running revision from connecting, so redeploy straight away.

To rotate the owner's password, reset the `dealproof` role in Neon (console or `reset_postgres_role_password`). Then store its **direct** connection string, with `sslmode=verify-full`, as a new `DATABASE_MIGRATION_URL` version. The API is unaffected.

### Database TLS

Every encrypting `sslmode` (`require`, `verify-ca`, `verify-full`), and a remote host with no `sslmode`, gets an `ssl.SSLContext` that checks the certificate chain against the system CA store and checks the hostname (`app/db/session.py`). The app engine and Alembic share it. libpq's `require` alone would encrypt without authenticating the server. The secrets use `sslmode=verify-full`. `channel_binding` (in Neon's URLs) is dropped because asyncpg rejects it. The image build fails if the image has no CA certificates. Alembic and the API both log `database TLS: verify-full` at start.

### Migrations

- **When**: every API deploy runs the `dealproof-migrate` job (`RUN_MIGRATIONS=only`, as `dealproof`) before the service update. The service itself starts with `RUN_MIGRATIONS=verify`: it runs `alembic current --check-heads` as `dealproof_app` and refuses to start if the schema is behind. It never migrates, and it has no credentials that could.
- **One at a time**: `alembic/env.py` takes a Postgres advisory lock (`pg_advisory_xact_lock`, the transaction-scoped form, which is released on commit, rollback or disconnect and works through the pooler) before Alembic reads the current revision. A second migrator waits, then finds the schema at head and does nothing.
- **Next to live traffic**: the running API's job worker holds `FOR UPDATE` row locks on `runs` and `steps`, and an `ALTER TABLE` queued behind them used to hang the whole start-up. Once it holds the migration lock, `env.py` sets `lock_timeout` (`MIGRATION_LOCK_TIMEOUT`, default `5s`). A lock timeout or deadlock rolls the whole upgrade back (DDL is transactional) and it is retried with backoff, up to `MIGRATION_ATTEMPTS` times (default 8, about 2 minutes). If it still fails, the job fails, the API update is skipped and the old revision keeps serving.
- Locally, the default `RUN_MIGRATIONS=1` still migrates at container start, and `RUN_MIGRATIONS=0` skips it.
- Logs: `alembic.env` lines name the role (`connected as database role dealproof`), the TLS mode, the lock and every retry.

```sh
gcloud run jobs executions list --job dealproof-migrate --project cc-g527-showproduct --region asia-south1 --limit 3
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="dealproof-migrate"' \
  --project cc-g527-showproduct --limit 30 --format='value(textPayload)'
```

### Proxy headers and client IP

uvicorn runs with `--no-proxy-headers` and an empty `--forwarded-allow-ips` (`apps/api/docker-entrypoint.sh`), so `request.client` is always the TCP peer (Cloud Run's front end) and no sender can rewrite it, or the scheme, with `X-Forwarded-*`. The client IP used for login rate limits is worked out in app code. Today that means `AUTH_TRUSTED_PROXY_HOPS=2`: the `X-Forwarded-For` entry two places from the right, written by the web proxy and the API's front end. The web proxy will also send a signed `X-DealProof-Proxy` header, keyed with `PROXY_SHARED_SECRET`, which both services receive.

### Env vars

- API (plain): `RUN_MIGRATIONS=verify`, `AUTH_TRUSTED_PROXY_HOPS=2`, `CASE_CREDIT_BUDGET=600`, `DISCOVER_CREDIT_BUDGET=300`, `INVESTOR_CREDIT_BUDGET=300` (Crustdata credits per case evaluation, discovery run and investor run; override any of them in the environment of `deploy.sh`), `EMAIL_SEND_ENABLED=false`, `GCS_BUCKET`, `UPLOAD_RETENTION_DAYS=30`, `WEB_ORIGIN`. Secrets come from Secret Manager and never go into plain env vars or build args.
- Migration job (plain): `RUN_MIGRATIONS=only`. Optional: `MIGRATION_LOCK_TIMEOUT`, `MIGRATION_ATTEMPTS`.
- Web (runtime): `PROXY_SHARED_SECRET` (secret), `API_BASE_URL`, the API URL the `/api/*` proxy and server components call. It is a public URL, not a secret. Changing it only needs a new revision, not a rebuild. `NEXT_PUBLIC_API_URL` is no longer used by the deploy; the Dockerfile accepts it as an optional build arg for the legacy `lib/api.ts` helper.
- Web (runtime, optional): `FAVICON_PROXY_ENABLED`, default off. Only the exact value `true` turns on the favicon proxy `/api/favicon`, which fetches `https://<domain>/favicon.ico` server-side for the run's source ticker. Off, the route answers 404 to everything without making any request, and the ticker shows the source-class glyph for every source. `deploy.sh` does not set it. Turn it on in production only once the proxy's SSRF tests pass (`pnpm --filter web test`), with `gcloud run services update dealproof-web --region asia-south1 --update-env-vars FAVICON_PROXY_ENABLED=true`; turn it off again with `--remove-env-vars FAVICON_PROXY_ENABLED`.

### Why the API uses min-instances 1 with CPU always allocated

The API runs the job worker in-process (spec §5.1), so it has to keep processing steps after the request that started a job has returned. With the default request-based billing, Cloud Run throttles CPU to almost zero between requests, and the worker would freeze. `--no-cpu-throttling` (instance-based billing) keeps CPU on for as long as an instance exists. `min-instances 1` keeps that instance alive when there is no traffic, so queued or long-running jobs keep moving and scheduled rechecks can run.

Cheaper option: `API_MIN_INSTANCES=0 scripts/deploy.sh` keeps CPU always allocated but lets the service scale to zero. An instance then lives for the length of its requests plus up to about 15 idle minutes, and you pay only for that time, roughly $0–5/month at demo traffic. The catch is that a job still running when the instance is reclaimed stops until the next request boots an instance. The worker's lease re-queue (§5.1) resumes it from there, but nothing runs while the service has no traffic. Keep `1` for demos where jobs must finish unattended.

Sizing is env-overridable: `API_CPU` (2), `API_MEMORY` (4Gi), `API_MIN_INSTANCES` (1), `API_MAX_INSTANCES` (4), `WEB_CPU` (2), `WEB_MEMORY` (2Gi), `WEB_MIN_INSTANCES` (1), `WEB_MAX_INSTANCES` (2). Web min 1 avoids cold starts on the first page load.

Each API instance keeps a SQLAlchemy pool of `DB_POOL_SIZE` (20) plus `DB_MAX_OVERFLOW` (20) connections, waits `DB_POOL_TIMEOUT` (10 s) for one, recycles them after `DB_POOL_RECYCLE` (300 s) and pings before use. At max 4 instances that is up to 160 connections, so point `DATABASE_URL` at Neon's pooled (`-pooler`) endpoint or lower the pool. The old 5 + 10 default ran out under SSE streams plus the in-process worker (`QueuePool limit ... reached`).

## Monthly cost estimate (USD)

| Item | Estimate |
|---|---|
| `dealproof-api`: 1 vCPU + 0.5 GiB always on, instance-based billing (about $0.000018/vCPU-s and $0.000002/GiB-s), after the Cloud Run free tier | **about $44** (about $49 before the free tier) |
| `dealproof-web`: scales to zero, request-based | about $0 (within the free tier at demo traffic) |
| Neon (free plan) | $0 |
| Artifact Registry (2 images × up to 5 versions, about 1–2 GB) | about $0.10–0.20 |
| GCS uploads, Cloud Build (well inside free minutes), the migration job (seconds per deploy), Secret Manager (6 secrets) | under $0.50 |
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
- Database passwords: see [Database roles](#database-roles). `DATABASE_URL` is the `dealproof_app` role, not the owner.
- `PROXY_SHARED_SECRET`: pipe a new random value in (`python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(48))' | gcloud secrets versions add PROXY_SHARED_SECRET --project cc-g527-showproduct --data-file=-`), then run `scripts/deploy.sh` so both services pick it up together.
- To turn on real email, add a real `RESEND_API_KEY` version, then change `EMAIL_SEND_ENABLED=true` in `scripts/deploy.sh` and redeploy.

## Logs

```sh
gcloud run services logs read dealproof-api --project cc-g527-showproduct --region asia-south1 --limit 50
gcloud builds list --project cc-g527-showproduct --region asia-south1 --limit 5
gcloud run jobs executions list --job dealproof-migrate --project cc-g527-showproduct --region asia-south1 --limit 5
```
