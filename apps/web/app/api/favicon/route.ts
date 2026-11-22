/**
 * Same-origin favicon proxy: `GET /api/favicon?domain=example.com`.
 *
 * The source ticker shows a favicon beside every page a run reads. The list of domains a
 * firm is reading about a target is itself sensitive, so the browser never asks a
 * third-party favicon service: it asks this route, and this route asks the site.
 *
 * What it will and will not do:
 * - Signed-in readers only (the session cookie must be present), so it is not an open proxy.
 * - Public host names only: a strict name pattern, no IP literals, no single-label or
 *   reserved names, and every address the name resolves to must be a public one.
 * - `https://<domain>/favicon.ico` only. At most three redirects, each checked the same way.
 * - Nothing of the reader's goes upstream: no cookies, no referrer, no forwarded headers.
 * - The answer must be a raster image type on the allowlist, at most 64 KB, inside 3 s.
 * - Results, misses included, are cached in memory here and in the browser.
 *
 * A miss is a 404 with no body; the ticker then shows the source-class glyph.
 */
import { lookup } from "node:dns/promises";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/api/proxy-rules";
import { isPublicAddress, publicHost } from "@/lib/run/favicon-rules";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BYTES = 64 * 1024;
const TIMEOUT_MS = 3000;
const MAX_REDIRECTS = 3;
const HIT_TTL_MS = 24 * 60 * 60 * 1000;
const MISS_TTL_MS = 60 * 60 * 1000;
const MAX_ENTRIES = 500;

/** SVG is left out on purpose: it can carry script, and this route serves from our origin. */
const IMAGE_TYPES = new Set([
  "image/x-icon",
  "image/vnd.microsoft.icon",
  "image/png",
  "image/gif",
  "image/jpeg",
  "image/webp",
]);

interface Entry {
  expires: number;
  icon: { bytes: Uint8Array<ArrayBuffer>; type: string } | null;
}

const cache = new Map<string, Entry>();
const inFlight = new Map<string, Promise<Entry["icon"]>>();

async function resolvesPublicly(host: string): Promise<boolean> {
  try {
    const addresses = await lookup(host, { all: true });
    return addresses.length > 0 && addresses.every((entry) => isPublicAddress(entry.address));
  } catch {
    return false;
  }
}

/** Reads the body up to the size limit. Null when it is larger. */
async function readCapped(response: Response): Promise<Uint8Array<ArrayBuffer> | null> {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_BYTES) return null;
  const reader = response.body?.getReader();
  if (!reader) return null;
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  if (total === 0) return null;
  const bytes = new Uint8Array(new ArrayBuffer(total));
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

async function fetchIcon(host: string): Promise<Entry["icon"]> {
  const signal = AbortSignal.timeout(TIMEOUT_MS);
  let url = new URL(`https://${host}/favicon.ico`);
  try {
    for (let hop = 0; hop <= MAX_REDIRECTS; hop += 1) {
      const target = publicHost(url.hostname);
      if (url.protocol !== "https:" || url.port !== "" || !target) return null;
      if (!(await resolvesPublicly(target))) return null;
      const response = await fetch(url, {
        method: "GET",
        // Fresh headers: nothing from the reader's request is passed on.
        headers: { accept: "image/*", "user-agent": "favicon-fetch" },
        credentials: "omit",
        referrerPolicy: "no-referrer",
        redirect: "manual",
        cache: "no-store",
        signal,
      });
      if (response.status >= 300 && response.status < 400) {
        const location = response.headers.get("location");
        await response.body?.cancel();
        if (!location) return null;
        url = new URL(location, url);
        continue;
      }
      if (!response.ok) {
        await response.body?.cancel();
        return null;
      }
      const type = (response.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
      if (!IMAGE_TYPES.has(type)) {
        await response.body?.cancel();
        return null;
      }
      const bytes = await readCapped(response);
      return bytes ? { bytes, type } : null;
    }
  } catch {
    /* timeout, DNS, TLS or a malformed redirect: a miss */
  }
  return null;
}

async function iconFor(host: string): Promise<Entry["icon"]> {
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

export async function GET(request: NextRequest): Promise<Response> {
  const fixtures = process.env.NEXT_PUBLIC_API_MODE === "fixtures";
  if (!fixtures && !request.cookies.has(SESSION_COOKIE)) {
    return new Response(null, { status: 401, headers: baseHeaders });
  }
  const host = publicHost(request.nextUrl.searchParams.get("domain"));
  if (!host) {
    return new Response(null, {
      status: 404,
      headers: { ...baseHeaders, "cache-control": "private, max-age=86400" },
    });
  }
  const icon = await iconFor(host);
  if (!icon) {
    return new Response(null, {
      status: 404,
      headers: { ...baseHeaders, "cache-control": "private, max-age=3600" },
    });
  }
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
