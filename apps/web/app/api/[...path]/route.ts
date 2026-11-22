/**
 * Same-origin proxy: the browser calls `/api/<path>` and this forwards to
 * `${API_BASE_URL}/<path>` (builder call 14). Only the `dp_session` cookie goes upstream,
 * and only allowlisted `Set-Cookie`s come back (host-only on this origin), so the session
 * stays first-party. Hop-by-hop headers are stripped both ways (`lib/api/proxy-rules.ts`).
 * Request and response bodies are streamed, never buffered, so uploads and server-sent
 * events (`/api/runs/{id}/events`) work through it.
 */
import type { NextRequest } from "next/server";

import { downstreamResponseHeaders, upstreamRequestHeaders } from "@/lib/api/proxy-rules";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_BASE_URL = (process.env.API_BASE_URL?.trim() || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  const target = `${API_BASE_URL}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = upstreamRequestHeaders(request.headers);
  // The right-most X-Forwarded-For entry is the one our own front end appended (Cloud Run);
  // anything left of it was written by the client. Forward only that address.
  const clientIp = request.headers.get("x-forwarded-for")?.split(",").pop()?.trim();
  if (clientIp) headers.set("x-forwarded-for", clientIp);
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
