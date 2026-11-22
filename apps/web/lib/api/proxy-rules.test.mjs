// Run with `pnpm --filter web test` (Node's built-in runner; Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  connectionTokens,
  downstreamResponseHeaders,
  filterSetCookie,
  isProtectedPath,
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
