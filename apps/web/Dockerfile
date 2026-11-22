# DealProof web — Cloud Run image.
# Build from the REPO ROOT so the pnpm workspace lockfile is available:
#   docker build -f apps/web/Dockerfile -t dealproof-web .
# Run with API_BASE_URL set to the API's URL. The browser only calls the same-origin
# /api/* proxy, which reads API_BASE_URL at runtime, so no URL is baked into the image.

FROM node:24-alpine AS base
RUN corepack enable
WORKDIR /repo

FROM base AS builder
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/api/package.json apps/api/
RUN pnpm install --frozen-lockfile --filter web...

COPY apps/web apps/web
# Optional. Only the legacy lib/api.ts helper reads it (inlined at build time); the
# client in lib/api/client.ts goes through the /api proxy and ignores it.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter web build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=8080

COPY --from=builder --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=node:node /repo/apps/web/public ./apps/web/public

USER node
EXPOSE 8080
CMD ["node", "apps/web/server.js"]
