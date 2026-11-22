/**
 * Same-origin proxy: the browser calls `/api/<path>` and this forwards to
 * `${API_BASE_URL}/<path>` (builder call 14). Only the `dp_session` cookie goes upstream,
 * and only allowlisted `Set-Cookie`s come back (host-only on this origin), so the session
 * stays first-party. Hop-by-hop headers are stripped both ways (`lib/api/proxy-rules.ts`).
 * Request and response bodies are streamed, never buffered, so uploads and server-sent
 * events (`/api/runs/{id}/events`) work through it.
 *
 * The browser's IP goes upstream only as `X-DealProof-Client-IP`, signed with
 * `PROXY_SHARED_SECRET` (`lib/api/proxy-auth.ts`); `X-Forwarded-For` is not forwarded, so
 * the API never trusts an address a caller wrote.
 *
 * CSRF: POST/PUT/PATCH/DELETE (sign-in and sign-out included) need an `Origin`, or failing
 * that a `Referer`, from this web app (`isSameOriginRequest`); anything else gets 403.
 */
import type { NextRequest } from "next/server";

import { addSignedClientIp } from "@/lib/api/proxy-auth";
import {
  downstreamResponseHeaders,
  isSameOriginRequest,
  parseOrigins,
  upstreamRequestHeaders,
} from "@/lib/api/proxy-rules";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_BASE_URL = (process.env.API_BASE_URL?.trim() || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

type Context = { params: Promise<{ path: string[] }> };

/** Extra origins accepted for unsafe requests besides this host (server-only env). */
const WEB_ORIGINS = parseOrigins(process.env.WEB_ORIGIN);

async function proxy(request: NextRequest, context: Context): Promise<Response> {
  if (!isSameOriginRequest(request.method, request.headers, WEB_ORIGINS)) {
    return Response.json({ detail: "Cross-site request refused." }, { status: 403 });
  }
  const { path } = await context.params;
  const target = `${API_BASE_URL}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = upstreamRequestHeaders(request.headers);
  addSignedClientIp(headers, request.headers, process.env.PROXY_SHARED_SECRET?.trim());
  headers.set("x-forwarded-host", request.nextUrl.host);
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));

  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    } as RequestInit);
  } catch {
    return Response.json({ detail: "The DealProof API is unreachable." }, { status: 502 });
  }

  const responseHeaders = downstreamResponseHeaders(upstream.headers);

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as HEAD,
  proxy as OPTIONS,
};
