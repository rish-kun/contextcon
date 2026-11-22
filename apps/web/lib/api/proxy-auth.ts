/**
 * Signs the browser's IP for the API (`apps/api/app/auth/proxy.py` verifies it).
 *
 * Deployment: browser → this web proxy (Cloud Run) → API (Cloud Run). The API can't tell
 * browsers apart by its socket peer (Google's front end) or by `X-Forwarded-For` (which
 * callers can write), so the proxy sends the IP in `X-DealProof-Client-IP` with an HMAC in
 * `X-DealProof-Proxy`, keyed by `PROXY_SHARED_SECRET` (server-only, set on both services).
 * Without the secret nothing is sent and the API limits by the address it sees.
 * Kept to `node:crypto` so `node --test` can run `proxy-auth.test.mjs` directly.
 */
import { createHmac } from "node:crypto";

export const CLIENT_IP_HEADER = "x-dealproof-client-ip";
export const PROXY_HEADER = "x-dealproof-proxy";

/** `t=<unix seconds>,sig=<hex HMAC-SHA256(secret, "<t>\n<ip>")>`. */
export function signClientIp(secret: string, ip: string, nowMs: number = Date.now()): string {
  const t = Math.floor(nowMs / 1000);
  const sig = createHmac("sha256", secret).update(`${t}\n${ip}`).digest("hex");
  return `t=${t},sig=${sig}`;
}

/**
 * The browser's IP as our own front end saw it: the right-most `X-Forwarded-For` entry
 * (Cloud Run appends the connecting address; anything left of it was written by the client).
 */
export function clientIpFrom(headers: Headers): string | null {
  const ip = headers.get("x-forwarded-for")?.split(",").pop()?.trim();
  return ip || null;
}

/** Add the signed client-IP headers to an upstream request, when a secret is configured. */
export function addSignedClientIp(
  upstream: Headers,
  incoming: Headers,
  secret: string | undefined,
  nowMs: number = Date.now(),
): void {
  upstream.delete(CLIENT_IP_HEADER);
  upstream.delete(PROXY_HEADER);
  const ip = clientIpFrom(incoming);
  if (!secret || !ip) return;
  upstream.set(CLIENT_IP_HEADER, ip);
  upstream.set(PROXY_HEADER, signClientIp(secret, ip, nowMs));
}
