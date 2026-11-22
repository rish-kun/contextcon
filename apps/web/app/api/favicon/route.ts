/**
 * Same-origin favicon proxy: `GET /api/favicon?domain=example.com`.
 *
 * The source ticker shows a favicon beside every page a run reads. The list of domains a
 * firm is reading about a target is itself sensitive, so the browser never asks a
 * third-party favicon service: it asks this route, and this route asks the site.
 *
 * What it will and will not do (the fetch itself is in `lib/run/favicon-proxy.ts`):
 * - Off unless `FAVICON_PROXY_ENABLED=true`: every request is then a 404 and nothing is
 *   fetched (see docs/deploy.md).
 * - Signed-in readers only: the session cookie is checked with the API (`GET /auth/me`),
 *   not just looked for, so it is not an open proxy.
 * - Public host names only: no IP literals in any notation, no single-label or reserved
 *   names. Each hop's name is resolved once, every address must be public, and the
 *   connection is pinned to a checked address with TLS verified against the name.
 * - `https://<domain>/favicon.ico` only. At most three redirects, each checked the same way.
 * - Nothing of the reader's goes upstream: no cookies, no referrer, no forwarded headers.
 * - The answer must be a raster image type on the allowlist, at most 64 KB, with DNS, the
 *   connection and the body all inside one 3 s deadline.
 * - Results, misses included, are cached in memory here and in the browser.
 *
 * A miss is a 404 with no body; the ticker then shows the source-class glyph.
 */
import type { NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/api/proxy-rules";
import {
  SessionCheck,
  faviconProxyEnabled,
  fetchIcon,
  publicHost,
  verifySessionWithApi,
  type Icon,
} from "@/lib/run/favicon-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HIT_TTL_MS = 24 * 60 * 60 * 1000;
const MISS_TTL_MS = 60 * 60 * 1000;
const MAX_ENTRIES = 500;

const API_BASE_URL = (process.env.API_BASE_URL?.trim() || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

interface Entry {
  expires: number;
  icon: Icon | null;
}

const cache = new Map<string, Entry>();
const inFlight = new Map<string, Promise<Icon | null>>();
const sessions = new SessionCheck((token) =>
  verifySessionWithApi(API_BASE_URL, SESSION_COOKIE, token),
);

async function iconFor(host: string): Promise<Icon | null> {
  const cached = cache.get(host);
  if (cached && cached.expires > Date.now()) return cached.icon;
  const pending = inFlight.get(host);
  if (pending) return pending;
  const work = fetchIcon(host).then((icon) => {
    if (cache.size >= MAX_ENTRIES) {
      const oldest = cache.keys().next().value;
      if (oldest !== undefined) cache.delete(oldest);
    }
    cache.set(host, { icon, expires: Date.now() + (icon ? HIT_TTL_MS : MISS_TTL_MS) });
    inFlight.delete(host);
    return icon;
  });
  inFlight.set(host, work);
  return work;
}

const baseHeaders = {
  "x-content-type-options": "nosniff",
  "content-security-policy": "default-src 'none'; sandbox",
  "cross-origin-resource-policy": "same-origin",
};

const notFound = (maxAge: number) =>
  new Response(null, {
    status: 404,
    headers: { ...baseHeaders, "cache-control": `private, max-age=${maxAge}` },
  });

export async function GET(request: NextRequest): Promise<Response> {
  if (!faviconProxyEnabled(process.env)) return notFound(3600);
  const fixtures = process.env.NEXT_PUBLIC_API_MODE === "fixtures";
  if (!fixtures && !(await sessions.isValid(request.cookies.get(SESSION_COOKIE)?.value))) {
    return new Response(null, {
      status: 401,
      headers: { ...baseHeaders, "cache-control": "no-store" },
    });
  }
  const host = publicHost(request.nextUrl.searchParams.get("domain"));
  if (!host) return notFound(86400);
  const icon = await iconFor(host);
  if (!icon) return notFound(3600);
  return new Response(icon.bytes, {
    status: 200,
    headers: {
      ...baseHeaders,
      "content-type": icon.type,
      "content-length": String(icon.bytes.byteLength),
      "cache-control": "private, max-age=86400",
    },
  });
}
