// Run with `pnpm --filter web test`. The expected signature matches
// `apps/api/app/auth/proxy.py` (`sign("s3cret", "203.0.113.9", 1000)`).
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";

import { addSignedClientIp, clientIpFrom, signClientIp } from "./proxy-auth.ts";

test("signature format matches the API", () => {
  const sig = createHmac("sha256", "s3cret").update("1000\n203.0.113.9").digest("hex");
  assert.equal(signClientIp("s3cret", "203.0.113.9", 1_000_500), `t=1000,sig=${sig}`);
});

test("client IP is the right-most X-Forwarded-For entry", () => {
  assert.equal(clientIpFrom(new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.9" })), "203.0.113.9");
  assert.equal(clientIpFrom(new Headers()), null);
});

test("headers are added only with a secret and an IP", () => {
  const incoming = new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.9" });
  const out = new Headers({ "x-dealproof-client-ip": "forged", "x-dealproof-proxy": "forged" });
  addSignedClientIp(out, incoming, undefined);
  assert.equal(out.get("x-dealproof-client-ip"), null);
  assert.equal(out.get("x-dealproof-proxy"), null);

  addSignedClientIp(out, incoming, "s3cret", 1_000_000);
  assert.equal(out.get("x-dealproof-client-ip"), "203.0.113.9");
  assert.equal(out.get("x-dealproof-proxy"), signClientIp("s3cret", "203.0.113.9", 1_000_000));

  const none = new Headers();
  addSignedClientIp(none, new Headers(), "s3cret");
  assert.equal(none.get("x-dealproof-proxy"), null);
});
