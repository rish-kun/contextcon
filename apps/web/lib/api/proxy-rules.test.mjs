// Run with `pnpm --filter web test` (Node's built-in runner; Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  connectionTokens,
  downstreamResponseHeaders,
  filterSetCookie,
  isProtectedPath,
  isSameOriginRequest,
  parseOrigins,
  requestSourceOrigin,
  sessionCookieOnly,
  signInRedirect,
  upstreamRequestHeaders,
} from "./proxy-rules.ts";

test("only the session cookie goes upstream", () => {
  assert.equal(sessionCookieOnly("a=1; dp_session=tok; _ga=x"), "dp_session=tok");
  assert.equal(sessionCookieOnly("a=1; xdp_session=nope"), null);
  assert.equal(sessionCookieOnly(null), null);
  const out = upstreamRequestHeaders(
    new Headers({ cookie: "theme=dark; dp_session=tok", accept: "application/json" }),
  );
  assert.equal(out.get("cookie"), "dp_session=tok");
  assert.equal(out.get("accept"), "application/json");
  assert.equal(upstreamRequestHeaders(new Headers({ cookie: "theme=dark" })).get("cookie"), null);
});

test("request headers: allowlist only, minus Connection-nominated ones", () => {
  const out = upstreamRequestHeaders(
    new Headers({
      host: "web.example",
      authorization: "Bearer x",
      "proxy-authorization": "Basic x",
      upgrade: "websocket",
      te: "trailers",
      connection: "keep-alive, Last-Event-ID",
      "last-event-id": "7",
      "content-type": "application/json",
    }),
  );
  assert.deepEqual([...out.keys()].sort(), ["content-type"]);
});

test("connection tokens are parsed case-insensitively", () => {
  const tokens = connectionTokens(new Headers({ connection: " Close , X-Secret ,," }));
  assert.deepEqual([...tokens].sort(), ["close", "x-secret"]);
});

test("Set-Cookie: allowlisted names only, made host-only", () => {
  assert.equal(
    filterSetCookie("dp_session=abc; Domain=api.example; Path=/; HttpOnly; Secure; SameSite=lax"),
    "dp_session=abc; Path=/; HttpOnly; Secure; SameSite=lax",
  );
  assert.equal(filterSetCookie("tracker=1; Path=/"), null);
  assert.equal(filterSetCookie("garbage"), null);
});

test("response headers drop hop-by-hop and unknown cookies", () => {
  const upstream = new Headers({
    "content-type": "application/json",
    "content-length": "10",
    "content-encoding": "gzip",
    connection: "close, x-internal",
    "x-internal": "secret",
    "keep-alive": "timeout=5",
    "transfer-encoding": "chunked",
    trailer: "x-checksum",
    upgrade: "h2c",
    "proxy-authenticate": "Basic",
    "x-dealproof-fixture": "1",
  });
  upstream.append("set-cookie", "dp_session=abc; Path=/; HttpOnly");
  upstream.append("set-cookie", "other=1; Path=/");
  const out = downstreamResponseHeaders(upstream);
  assert.deepEqual([...out.keys()].sort(), ["content-type", "set-cookie", "x-dealproof-fixture"]);
  assert.deepEqual(out.getSetCookie(), ["dp_session=abc; Path=/; HttpOnly"]);
});

test("event streams are marked unbuffered", () => {
  const out = downstreamResponseHeaders(new Headers({ "content-type": "text/event-stream" }));
  assert.equal(out.get("cache-control"), "no-cache, no-transform");
  assert.equal(out.get("x-accel-buffering"), "no");
});

test("sign-in redirect covers the app areas only", () => {
  assert.equal(isProtectedPath("/app"), true);
  assert.equal(isProtectedPath("/app/cases/1"), true);
  assert.equal(isProtectedPath("/cases"), true);
  assert.equal(isProtectedPath("/application"), false);
  assert.equal(isProtectedPath("/login"), false);
  assert.equal(isProtectedPath("/"), false);
  assert.equal(
    signInRedirect("/app/cases/1", "?tab=claims", false),
    "/login?next=%2Fapp%2Fcases%2F1%3Ftab%3Dclaims",
  );
  assert.equal(signInRedirect("/app/cases/1", "", true), null);
  assert.equal(signInRedirect("/", "", false), null);
});

test("CSRF: safe methods always pass", () => {
  assert.equal(isSameOriginRequest("GET", new Headers({ origin: "https://evil.example" })), true);
  assert.equal(isSameOriginRequest("HEAD", new Headers()), true);
  assert.equal(isSameOriginRequest("OPTIONS", new Headers()), true);
});

test("CSRF: unsafe methods need this web app's origin", () => {
  const host = "app.dealproof.example";
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "post"]) {
    const same = new Headers({ host, origin: `https://${host}` });
    assert.equal(isSameOriginRequest(method, same), true, method);
    const cross = new Headers({ host, origin: "https://evil.example" });
    assert.equal(isSameOriginRequest(method, cross), false, method);
    // A sibling subdomain is same-site (SameSite=Lax lets it post) but not same-origin.
    const sibling = new Headers({ host, origin: "https://blog.dealproof.example" });
    assert.equal(isSameOriginRequest(method, sibling), false, method);
    assert.equal(isSameOriginRequest(method, new Headers({ host })), false, method);
    assert.equal(isSameOriginRequest(method, new Headers({ host, origin: "null" })), false);
  }
});

test("CSRF: Referer is the fallback, Origin wins when present", () => {
  const host = "localhost:3000";
  const viaReferer = new Headers({ host, referer: "http://localhost:3000/login?next=/app" });
  assert.equal(isSameOriginRequest("POST", viaReferer), true);
  assert.equal(
    isSameOriginRequest("POST", new Headers({ host, referer: "https://evil.example/x" })),
    false,
  );
  assert.equal(isSameOriginRequest("POST", new Headers({ host, referer: "not a url" })), false);
  const both = new Headers({ host, origin: "https://evil.example", referer: `http://${host}/` });
  assert.equal(isSameOriginRequest("POST", both), false);
  assert.equal(requestSourceOrigin(new Headers({ origin: "null", referer: `http://${host}/` })), null);
});

test("CSRF: configured origins are accepted", () => {
  const origins = parseOrigins(" https://dealproof.example/ , http://localhost:3000,");
  assert.deepEqual(origins, ["https://dealproof.example", "http://localhost:3000"]);
  const headers = new Headers({ host: "web-abc.a.run.app", origin: "https://dealproof.example" });
  assert.equal(isSameOriginRequest("POST", headers, origins), true);
  assert.equal(isSameOriginRequest("POST", headers), false);
});
