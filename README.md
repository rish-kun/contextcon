# DealProof

DealProof is an AI analyst for investors and acquirers: it finds companies that match a thesis, checks their claims against independent evidence, and says which ones deserve a closer look and why.
It also works the other way round, finding investors whose dated track record fits a business that is raising money.

See `DealProof product description.md` (product) and `docs/superpowers/specs/` (design).

## Layout

- `apps/web`: Next.js (App Router, TypeScript, Tailwind CSS)
- `apps/api`: Python FastAPI service, managed with uv

## Local development

Prerequisites: Node 22.13+ with pnpm, Python 3.12+ and uv.

```sh
cp .env.example .env        # then fill in keys; never commit .env
pnpm install                # web dependencies
(cd apps/api && uv sync)    # API dependencies

pnpm dev                    # web on :3000 and API on :8000 together
pnpm dev:web                # web only
pnpm dev:api                # API only (uvicorn --reload on :8000)
```

Checks:

```sh
pnpm lint                   # eslint (web) + ruff (api)
pnpm test                   # pytest (api)
pnpm build                  # next build (web) + uv sync (api)

cd apps/api && uv run pytest && uv run ruff check
pnpm --filter web build
```

Health check: `curl http://localhost:8000/health` returns `{"status":"ok"}`.

## Containers (Cloud Run)

```sh
docker build -t dealproof-api apps/api
docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://<api-url> -t dealproof-web .
```

Both images listen on `$PORT` (default 8080).
