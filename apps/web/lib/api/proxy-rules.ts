/**
 * Rules for the same-origin `/api/*` proxy and the sign-in redirect in `proxy.ts`.
 * Kept free of imports so `node --test` can run `proxy-rules.test.mjs` directly.
 */

/** The API's session cookie (httpOnly, set by `POST /auth/login` and `POST /auth/verify`). */
export const SESSION_COOKIE = "dp_session";

/** Cookies the API may set on the web origin. Anything else is dropped. */
export const ALLOWED_SET_COOKIES: ReadonlySet<string> = new Set([SESSION_COOKIE]);

/** Request headers worth forwarding upstream. Everything else (host, …) is dropped. */
export const FORWARD_REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "content-type",
  "content-length",
  "cookie",
  "last-event-id",
  "idempotency-key",
] as const;

/** Hop-by-hop headers (RFC 9110 §7.6.1), never forwarded in either direction. */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

/** Response headers that are recomputed here rather than copied. */
const RECOMPUTED_RESPONSE_HEADERS = new Set([
  "content-encoding", // fetch already decoded the body
  "content-length",
  "set-cookie", // filtered and copied one by one
]);

/** Header names the `Connection` header nominates as hop-by-hop. */
export function connectionTokens(headers: Headers): Set<string> {
  const tokens = new Set<string>();
  for (const name of ["connection", "proxy-connection"]) {
    for (const token of (headers.get(name) ?? "").split(",")) {
      const t = token.trim().toLowerCase();
      if (t) tokens.add(t);
    }
  }
  return tokens;
}

function isHopByHop(name: string, nominated: Set<string>): boolean {
  const n = name.toLowerCase();
  return HOP_BY_HOP.has(n) || n.startsWith("proxy-") || nominated.has(n);
}

/** Keep only the session cookie from a `Cookie` request header. */
export function sessionCookieOnly(cookieHeader: string | null): string | null {
  if (!cookieHeader) return null;
  const kept = cookieHeader
    .split(";")
    .map((pair) => pair.trim())
    .filter((pair) => pair.slice(0, pair.indexOf("=")).trim() === SESSION_COOKIE);
  return kept.length ? kept.join("; ") : null;
}

/** Headers to send upstream: the allowlist, minus hop-by-hop, with only `dp_session`. */
export function upstreamRequestHeaders(incoming: Headers): Headers {
  const nominated = connectionTokens(incoming);
  const out = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    if (isHopByHop(name, nominated)) continue;
    const value = name === "cookie" ? sessionCookieOnly(incoming.get(name)) : incoming.get(name);
    if (value !== null) out.set(name, value);
  }
  return out;
}

/** The cookie name in a `Set-Cookie` value. */
export function setCookieName(setCookie: string): string {
  const pair = setCookie.split(";", 1)[0];
  const eq = pair.indexOf("=");
  return (eq === -1 ? "" : pair.slice(0, eq)).trim();
}

/**
 * An allowlisted `Set-Cookie`, made host-only on the web origin (any `Domain` attribute
 * is removed), or null to drop it.
 */
export function filterSetCookie(setCookie: string): string | null {
  if (!ALLOWED_SET_COOKIES.has(setCookieName(setCookie))) return null;
  return setCookie
    .split(";")
    .filter((part, i) => i === 0 || !/^\s*domain\s*=/i.test(part))
    .join(";");
}

/** Headers to send back to the browser from the upstream response. */
export function downstreamResponseHeaders(upstream: Headers): Headers {
  const nominated = connectionTokens(upstream);
  const out = new Headers();
  upstream.forEach((value, name) => {
    if (isHopByHop(name, nominated) || RECOMPUTED_RESPONSE_HEADERS.has(name)) return;
    out.set(name, value);
  });
  for (const cookie of upstream.getSetCookie()) {
    const kept = filterSetCookie(cookie);
    if (kept !== null) out.append("set-cookie", kept);
  }
  if (upstream.get("content-type")?.startsWith("text/event-stream")) {
    out.set("cache-control", "no-cache, no-transform");
    out.set("x-accel-buffering", "no");
  }
  return out;
}

/* ───────────────────────── CSRF: same-origin unsafe requests ───────────────────────── */

/** Methods that change state. They need an `Origin` (or `Referer`) from this web app. */
export const UNSAFE_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** The origin a request says it came from: `Origin`, else the `Referer`'s origin. */
export function requestSourceOrigin(headers: Headers): string | null {
  const origin = headers.get("origin");
  if (origin && origin !== "null") return origin;
  if (origin === "null") return null; // opaque origin (sandboxed frame, file:, …)
  const referer = headers.get("referer");
  if (!referer) return null;
  try {
    return new URL(referer).origin;
  } catch {
    return null;
  }
}

/**
 * Whether a proxied request may go upstream. Safe methods always may. Unsafe ones must
 * come from this web app: the source origin's host equals the request's `Host` (which a
 * cross-site page cannot set), or the origin is listed in `allowedOrigins`. The cookie is
 * SameSite=Lax, but that still lets same-site pages (other subdomains) post; this is the
 * gate, since the API never sees the browser's `Origin` through the proxy.
 */
export function isSameOriginRequest(
  method: string,
  headers: Headers,
  allowedOrigins: readonly string[] = [],
): boolean {
  if (!UNSAFE_METHODS.has(method.toUpperCase())) return true;
  const source = requestSourceOrigin(headers);
  if (!source) return false;
  if (allowedOrigins.includes(source)) return true;
  let host: string;
  try {
    host = new URL(source).host;
  } catch {
    return false;
  }
  const ownHost = headers.get("host");
  return ownHost !== null && host.toLowerCase() === ownHost.toLowerCase();
}

/** Comma-separated origins (e.g. `WEB_ORIGIN`) as a list. */
export function parseOrigins(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((o) => o.trim().replace(/\/+$/, ""))
    .filter(Boolean);
}

/* ───────────────────────── Sign-in redirect (proxy.ts) ───────────────────────── */

/** App areas behind sign-in. The API is the real check; this only saves a round trip. */
export const PROTECTED_PREFIXES = ["/app", "/cases", "/discover", "/investors"] as const;

/**
 * The sign-in, sign-up and email-verification pages. Always public (a visitor reaching
 * them has no session yet), and never a place to return to after signing in.
 */
export const AUTH_PAGES = ["/login", "/signup", "/verify"] as const;

function underPrefix(pathname: string, prefixes: readonly string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function isAuthPage(pathname: string): boolean {
  return underPrefix(pathname, AUTH_PAGES);
}

export function isProtectedPath(pathname: string): boolean {
  return !isAuthPage(pathname) && underPrefix(pathname, PROTECTED_PREFIXES);
}

/**
 * Where to send a request, or null to let it through: `/login?next=<path>` for a
 * protected path without a session cookie. `next` is always a same-origin path, and
 * never one of the `AUTH_PAGES`.
 */
export function signInRedirect(
  pathname: string,
  search: string,
  hasSessionCookie: boolean,
): string | null {
  if (hasSessionCookie || !isProtectedPath(pathname)) return null;
  return `/login?${new URLSearchParams({ next: `${pathname}${search}` })}`;
}
