// Run with `pnpm --filter web test`. The SSRF guards of the favicon proxy
// (`app/api/favicon/route.ts`, `lib/run/favicon-proxy.ts`). These must pass before
// FAVICON_PROXY_ENABLED is turned on anywhere (docs/deploy.md).
import assert from "node:assert/strict";
import { lookup } from "node:dns";
import { test } from "node:test";

import {
  MAX_BYTES,
  SessionCheck,
  faviconProxyEnabled,
  fetchIcon,
  isPublicAddress,
  pickPublicAddress,
  pinnedLookup,
  pinnedRequestOptions,
  publicHost,
  verifySessionWithApi,
} from "./favicon-proxy.ts";

test("the favicon proxy is off unless FAVICON_PROXY_ENABLED is true", () => {
  assert.equal(faviconProxyEnabled({}), false);
  for (const value of ["", "false", "0", "1", "yes", "on"]) {
    assert.equal(faviconProxyEnabled({ FAVICON_PROXY_ENABLED: value }), false, value);
  }
  assert.equal(faviconProxyEnabled({ FAVICON_PROXY_ENABLED: "true" }), true);
  assert.equal(faviconProxyEnabled({ FAVICON_PROXY_ENABLED: " TRUE " }), true);
});

test("only public host names are asked, never an IP in any notation", () => {
  assert.equal(publicHost("Example.COM."), "example.com");
  assert.equal(publicHost("xn--bcher-kva.ch"), "xn--bcher-kva.ch");
  const refused = [
    "localhost", "intranet", "site.local", "foo.example", "a..b.com", "evil.com/path",
    "evil.com:8080", "metadata.google.internal", "", "internal", "user@evil.com",
    // IP literals, including the forms a URL parser would read as IPv4.
    "10.0.0.1", "127.0.0.1", "169.254.169.254", "[::1]", "::1", "[::ffff:127.0.0.1]",
    "2130706433", "0x7f000001", "0x7f.0.0.1", "0177.0.0.1", "127.1", "0x7f.1",
    "017700000001", "1.0x7f", "evil.0x10", "a.b.255",
  ];
  for (const bad of refused) assert.equal(publicHost(bad), null, bad);
});

test("hosts a URL normalises to an IP are refused", () => {
  // A redirect `Location` goes through `new URL`, which rewrites numeric hosts to dotted
  // IPv4; the hop check sees the rewritten name.
  for (const location of [
    "https://2130706433/x", "https://0x7f000001/x", "https://0177.0.0.1/x",
    "https://127.1/x", "https://[::ffff:127.0.0.1]/x", "https://[::1]/x",
    "https://169.254.169.254/latest/meta-data/",
  ]) {
    assert.equal(publicHost(new URL(location).hostname), null, location);
  }
});

test("private, loopback, link-local, CGNAT, metadata and reserved addresses are not public", () => {
  const blocked = [
    // IPv4
    "0.0.0.0", "0.1.2.3", "10.1.2.3", "100.64.0.1", "100.127.255.255", "127.0.0.1",
    "127.255.255.254", "169.254.169.254", "169.254.0.1", "172.16.0.1", "172.31.255.255",
    "192.0.0.8", "192.0.2.1", "192.88.99.1", "192.168.1.1", "198.18.0.1", "198.19.255.1",
    "198.51.100.7", "203.0.113.9", "224.0.0.1", "239.255.255.250", "240.0.0.1",
    "255.255.255.255",
    // IPv6
    "::", "::1", "fc00::1", "fd00::1", "fdff:ffff::1", "fe80::1", "fe80::1%en0", "febf::1",
    "ff02::1", "100::1", "2001:db8::1", "2001::1", "2001:0:4136:e378::1", "3fff::1",
    "64:ff9b:1::1",
    // IPv4 inside IPv6
    "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::ffff:7f00:1", "::ffff:169.254.169.254",
    "::ffff:a9fe:a9fe", "0:0:0:0:0:ffff:7f00:0001", "::127.0.0.1", "::7f00:1",
    "::ffff:0:127.0.0.1", "64:ff9b::127.0.0.1", "64:ff9b::a9fe:a9fe", "2002:7f00:1::",
    "2002:a9fe:a9fe::1", "2002:c0a8:0101::1",
    // Not an address at all
    "2130706433", "0x7f000001", "0177.0.0.1", "example.com", "",
  ];
  for (const address of blocked) assert.equal(isPublicAddress(address), false, address);
  for (const address of [
    "93.184.216.34", "8.8.8.8", "1.1.1.1", "172.32.0.1", "100.128.0.1", "2606:2800:220:1:248:1893:25c8:1946",
    "2a00:1450:4001:80b::200e", "::ffff:93.184.216.34", "64:ff9b::808:808", "2002:808:808::1",
  ]) {
    assert.equal(isPublicAddress(address), true, address);
  }
});

test("a name is used only when every address it resolves to is public", () => {
  assert.equal(pickPublicAddress([]), null);
  assert.equal(pickPublicAddress(["93.184.216.34", "10.0.0.1"]), null);
  assert.equal(pickPublicAddress(["2606:2800:220:1::1", "fd00::1"]), null);
  assert.deepEqual(pickPublicAddress(["2606:2800:220:1::1", "93.184.216.34"]), {
    address: "93.184.216.34",
    family: 4,
  });
  assert.deepEqual(pickPublicAddress(["2606:2800:220:1::1"]), {
    address: "2606:2800:220:1::1",
    family: 6,
  });
});

test("the connection is pinned to the checked address, TLS stays on the name", async () => {
  const target = { host: "example.com", path: "/favicon.ico", address: "93.184.216.34", family: 4 };
  const options = pinnedRequestOptions(target, new AbortController().signal);
  assert.equal(options.host, "example.com");
  assert.equal(options.servername, "example.com");
  assert.equal(options.headers.host, "example.com");
  assert.equal(options.port, 443);
  assert.equal(options.agent, false);
  assert.equal(options.rejectUnauthorized, true);
  assert.equal(options.headers.cookie, undefined);
  // Both lookup shapes Node's net uses answer with the checked address, whatever the name.
  const one = await new Promise((resolve) =>
    options.lookup("rebound.example.com", {}, (error, address, family) => resolve({ error, address, family })),
  );
  assert.deepEqual(one, { error: null, address: "93.184.216.34", family: 4 });
  const all = await new Promise((resolve) =>
    pinnedLookup("2606:2800:220:1::1", 6)("x", { all: true }, (error, addresses) => resolve(addresses)),
  );
  assert.deepEqual(all, [{ address: "2606:2800:220:1::1", family: 6 }]);
  // Sanity: the real resolver signature is the one being mimicked.
  assert.equal(typeof lookup, "function");
});

/* A fake transport: records every hop and every cancelled body. */
function fakeTransport({ dns, responses, resolveDelay = 0 }) {
  const calls = { resolved: [], got: [], cancelled: [] };
  return {
    calls,
    resolve: async (host, signal) => {
      calls.resolved.push(host);
      if (resolveDelay === Infinity) return new Promise(() => {});
      if (resolveDelay) await new Promise((r) => setTimeout(r, resolveDelay));
      if (signal.aborted) throw signal.reason;
      return dns[host] ?? [];
    },
    get: async (target) => {
      calls.got.push(target);
      const spec = responses[`${target.host}${target.path}`];
      if (!spec) throw new Error(`no response for ${target.host}${target.path}`);
      const body = spec.body ?? (async function* () {})();
      return {
        status: spec.status,
        headers: spec.headers ?? {},
        body: typeof body === "function" ? body() : body,
        cancel: () => calls.cancelled.push(`${target.host}${target.path}`),
      };
    },
  };
}

const png = (bytes) =>
  async function* () {
    yield new Uint8Array(bytes);
  };

test("a public favicon is fetched from the pinned address", async () => {
  const t = fakeTransport({
    dns: { "site.com": ["93.184.216.34"] },
    responses: { "site.com/favicon.ico": { status: 200, headers: { "content-type": "image/png" }, body: png([1, 2, 3]) } },
  });
  const icon = await fetchIcon("site.com", t);
  assert.deepEqual([...icon.bytes], [1, 2, 3]);
  assert.equal(icon.type, "image/png");
  assert.deepEqual(t.calls.got, [{ host: "site.com", path: "/favicon.ico", address: "93.184.216.34", family: 4 }]);
});

test("a name that resolves to any private address is never connected to", async () => {
  for (const addresses of [["10.0.0.1"], ["93.184.216.34", "127.0.0.1"], ["169.254.169.254"], ["::ffff:7f00:1"], ["fd12::1"]]) {
    const t = fakeTransport({ dns: { "rebind.com": addresses }, responses: {} });
    assert.equal(await fetchIcon("rebind.com", t), null, addresses.join());
    assert.deepEqual(t.calls.got, [], addresses.join());
  }
});

test("every redirect hop is re-validated and its body cancelled", async () => {
  const t = fakeTransport({
    dns: { "site.com": ["93.184.216.34"], "cdn.site.com": ["93.184.216.35"], "evil.com": ["10.0.0.5"] },
    responses: {
      "site.com/favicon.ico": { status: 301, headers: { location: "https://cdn.site.com/i.ico?v=2" } },
      "cdn.site.com/i.ico?v=2": { status: 302, headers: { location: "https://evil.com/x" } },
    },
  });
  assert.equal(await fetchIcon("site.com", t), null);
  assert.deepEqual(t.calls.resolved, ["site.com", "cdn.site.com", "evil.com"]);
  // evil.com resolved to a private address: no connection was made to it.
  assert.deepEqual(t.calls.got.map((g) => `${g.host}@${g.address}`), ["site.com@93.184.216.34", "cdn.site.com@93.184.216.35"]);
  assert.deepEqual(t.calls.cancelled, ["site.com/favicon.ico", "cdn.site.com/i.ico?v=2"]);
});

test("redirects to IP literals, other schemes, ports or credentials are refused", async () => {
  for (const location of [
    "https://127.0.0.1/x", "https://2130706433/x", "https://0x7f.1/x", "https://[::1]/x",
    "http://site.com/x", "https://site.com:8443/x", "https://user:pw@site.com/x",
    "https://169.254.169.254/latest/meta-data/", "file:///etc/passwd", "https://localhost/x",
  ]) {
    const t = fakeTransport({
      dns: { "site.com": ["93.184.216.34"], localhost: ["127.0.0.1"] },
      responses: { "site.com/favicon.ico": { status: 302, headers: { location } } },
    });
    assert.equal(await fetchIcon("site.com", t), null, location);
    assert.equal(t.calls.got.length, 1, location);
    assert.deepEqual(t.calls.cancelled, ["site.com/favicon.ico"], location);
  }
});

test("too many redirects is a miss", async () => {
  const responses = {};
  for (let i = 0; i < 6; i += 1) {
    responses[`site.com/${i}`] = { status: 302, headers: { location: `/${i + 1}` } };
  }
  responses["site.com/favicon.ico"] = { status: 302, headers: { location: "/0" } };
  const t = fakeTransport({ dns: { "site.com": ["93.184.216.34"] }, responses });
  assert.equal(await fetchIcon("site.com", t), null);
  assert.equal(t.calls.got.length, 4); // the first request and three redirects
  assert.equal(t.calls.cancelled.length, 4);
});

test("rejected responses have their bodies cancelled", async () => {
  const cases = {
    "a.com/favicon.ico": { status: 404, headers: { "content-type": "image/png" }, body: png([1]) },
    "b.com/favicon.ico": { status: 200, headers: { "content-type": "image/svg+xml" }, body: png([1]) },
    "c.com/favicon.ico": { status: 200, headers: { "content-type": "image/png", "content-length": String(MAX_BYTES + 1) } },
    "d.com/favicon.ico": {
      status: 200,
      headers: { "content-type": "image/png" },
      body: async function* () {
        for (let i = 0; i < 100; i += 1) yield new Uint8Array(4096);
      },
    },
    "e.com/favicon.ico": { status: 302, headers: {} },
  };
  for (const key of Object.keys(cases)) {
    const host = key.split("/")[0];
    const t = fakeTransport({ dns: { [host]: ["93.184.216.34"] }, responses: { [key]: cases[key] } });
    assert.equal(await fetchIcon(host, t), null, key);
    assert.deepEqual(t.calls.cancelled, [key], key);
  }
});

test("DNS and HTTP share one deadline", async () => {
  // DNS that never answers.
  let t = fakeTransport({ dns: {}, responses: {}, resolveDelay: Infinity });
  let started = Date.now();
  assert.equal(await fetchIcon("slow.com", t, 50), null);
  assert.ok(Date.now() - started < 1000);

  // DNS takes most of the budget; the body then trickles past what is left.
  t = fakeTransport({
    dns: { "slow.com": ["93.184.216.34"] },
    resolveDelay: 40,
    responses: {
      "slow.com/favicon.ico": {
        status: 200,
        headers: { "content-type": "image/png" },
        body: async function* () {
          yield new Uint8Array([1]);
          await new Promise((r) => setTimeout(r, 30));
          yield new Uint8Array([2]);
          await new Promise(() => {});
        },
      },
    },
  });
  started = Date.now();
  assert.equal(await fetchIcon("slow.com", t, 60), null);
  assert.ok(Date.now() - started < 1000);
  assert.deepEqual(t.calls.cancelled, ["slow.com/favicon.ico"]);
});

test("a session is valid only when the API says so, and the answer is cached", async () => {
  let now = 0;
  const asked = [];
  const check = new SessionCheck(async (token) => {
    asked.push(token);
    return token === "good";
  }, () => now);
  assert.equal(await check.isValid(undefined), false);
  assert.equal(await check.isValid(""), false);
  assert.equal(await check.isValid("forged"), false);
  assert.equal(await check.isValid("good"), true);
  assert.equal(await check.isValid("good"), true);
  assert.deepEqual(asked, ["forged", "good"]);
  now += 61_000;
  assert.equal(await check.isValid("good"), true);
  assert.deepEqual(asked, ["forged", "good", "good"]);

  const failing = new SessionCheck(async () => {
    throw new Error("API down");
  });
  assert.equal(await failing.isValid("good"), false);
});

test("the API check sends only the session cookie and needs a 200", async () => {
  const seen = [];
  const fetcher = async (url, init) => {
    seen.push({ url, cookie: init.headers.cookie, redirect: init.redirect });
    return new Response(null, { status: url.includes("ok") ? 200 : 401 });
  };
  assert.equal(await verifySessionWithApi("http://api-ok", "dp_session", "tok", fetcher), true);
  assert.equal(await verifySessionWithApi("http://api-no", "dp_session", "tok", fetcher), false);
  assert.deepEqual(seen[0], { url: "http://api-ok/auth/me", cookie: "dp_session=tok", redirect: "manual" });
  // A token that would smuggle another cookie or header is refused without asking.
  assert.equal(await verifySessionWithApi("http://api-ok", "dp_session", "a; other=1", fetcher), false);
  assert.equal(await verifySessionWithApi("http://api-ok", "dp_session", "a\r\nx: y", fetcher), false);
  assert.equal(seen.length, 2);
});
