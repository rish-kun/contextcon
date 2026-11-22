/**
 * The favicon proxy behind `app/api/favicon/route.ts`: who may ask it, which hosts it may
 * ask, and how it asks them. Kept out of the route, and free of `@/` imports, so all of it
 * runs under `node --test` (`favicon-proxy.test.mjs`, `run.test.mjs`).
 *
 * The fetch is built so that a name cannot point somewhere else between the check and the
 * connection (DNS rebinding), and so that no redirect can lead it anywhere private:
 * - Each hop's name is resolved once. Every address it resolves to must be public, and the
 *   connection goes to one of those addresses, pinned through the socket's `lookup`. TLS
 *   still checks the certificate against the host name (SNI and `servername`).
 * - Every redirect hop goes through the same checks: https, port 443, a public name, a
 *   fresh resolution and a fresh pinned connection.
 * - DNS, connect, headers and body all run under one deadline.
 * - Every response that is not used is destroyed, so its body is never read.
 *
 * This uses `node:https` with a pinned `lookup` rather than an undici `Agent`: the
 * undici package is not a dependency here, and Node's built-in fetch exposes no way to
 * pass it a connector. The effect is the same: one DNS answer, one checked IP, TLS on the
 * name.
 */
import { Resolver } from "node:dns/promises";
import type { IncomingHttpHeaders, IncomingMessage } from "node:http";
import { request as httpsRequest } from "node:https";
import type { RequestOptions } from "node:https";
import { isIP } from "node:net";
import type { LookupFunction } from "node:net";

/* ───────────────────────── Switch ───────────────────────── */

/**
 * The proxy is off unless `FAVICON_PROXY_ENABLED` is exactly `true` (server-only env).
 * Off, the route answers 404 to everything and the ticker shows source-class glyphs.
 */
export function faviconProxyEnabled(env: Record<string, string | undefined>): boolean {
  return env.FAVICON_PROXY_ENABLED?.trim().toLowerCase() === "true";
}

/* ───────────────────────── Host names ───────────────────────── */

/** Names that never resolve on the public internet, or must not be asked. */
const RESERVED_SUFFIXES = [
  ".example",
  ".test",
  ".invalid",
  ".localhost",
  ".local",
  ".internal",
  ".lan",
  ".home",
  ".corp",
  ".onion",
  ".arpa",
];

/** Dotted labels whose last label starts with a letter: no IP literal, in any notation, fits. */
const HOST_PATTERN =
  /^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$/;

/**
 * A URL parser reads a host whose last label is a number (`2130706433`, `0x7f.1`,
 * `0177.0.0.1`, `127.1`) as an IPv4 address. Such names are refused outright.
 */
function endsInNumber(host: string): boolean {
  const last = host.split(".").at(-1) ?? "";
  return /^(?:\d+|0x[0-9a-f]*)$/.test(last);
}

/** A public host name in its canonical form, or null. No IP literals, no single labels. */
export function publicHost(input: string | null | undefined): string | null {
  if (!input) return null;
  const host = input.trim().toLowerCase().replace(/\.$/, "");
  if (!HOST_PATTERN.test(host) || isIP(host) !== 0 || endsInNumber(host)) return null;
  if (RESERVED_SUFFIXES.some((suffix) => host === suffix.slice(1) || host.endsWith(suffix))) {
    return null;
  }
  return host;
}

/* ───────────────────────── Addresses ───────────────────────── */

function ipv4Value(address: string): number | null {
  const parts = address.split(".");
  if (parts.length !== 4 || !parts.every((part) => /^(?:0|[1-9]\d{0,2})$/.test(part))) return null;
  const octets = parts.map(Number);
  if (octets.some((octet) => octet > 255)) return null;
  return ((octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]) >>> 0;
}

/** Ranges that are not globally routable (RFC 6890 and friends), as [base, prefix]. */
const IPV4_BLOCKED: [string, number][] = [
  ["0.0.0.0", 8], // "this network"
  ["10.0.0.0", 8],
  ["100.64.0.0", 10], // carrier-grade NAT
  ["127.0.0.0", 8],
  ["169.254.0.0", 16], // link-local, cloud metadata (169.254.169.254)
  ["172.16.0.0", 12],
  ["192.0.0.0", 24], // IETF protocol assignments
  ["192.0.2.0", 24], // documentation
  ["192.88.99.0", 24], // 6to4 relay anycast
  ["192.168.0.0", 16],
  ["198.18.0.0", 15], // benchmarking
  ["198.51.100.0", 24], // documentation
  ["203.0.113.0", 24], // documentation
  ["224.0.0.0", 4], // multicast
  ["240.0.0.0", 4], // reserved, broadcast
];

function ipv4Public(value: number): boolean {
  return IPV4_BLOCKED.every(([base, prefix]) => {
    const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
    return ((value & mask) >>> 0) !== ((ipv4Value(base) ?? 0) & mask) >>> 0;
  });
}

/** The eight 16-bit words of an IPv6 address, or null. Accepts `::` and a dotted tail. */
function ipv6Words(address: string): number[] | null {
  let text = address.toLowerCase();
  const tail: number[] = [];
  const dotted = /^(.*:)(\d+\.\d+\.\d+\.\d+)$/.exec(text);
  if (dotted) {
    const value = ipv4Value(dotted[2]);
    if (value === null) return null;
    tail.push(value >>> 16, value & 0xffff);
    text = dotted[1].endsWith("::") ? dotted[1] : dotted[1].slice(0, -1);
  }
  const halves = text.split("::");
  if (halves.length > 2) return null;
  const parse = (part: string) => (part === "" ? [] : part.split(":"));
  const head = parse(halves[0]);
  const rest = halves.length === 2 ? parse(halves[1]) : [];
  if (![...head, ...rest].every((word) => /^[0-9a-f]{1,4}$/.test(word))) return null;
  const known = head.length + rest.length + tail.length;
  if (halves.length === 1 ? known !== 8 : known > 7) return null;
  const zeros = new Array<number>(8 - known).fill(0);
  return [
    ...head.map((word) => parseInt(word, 16)),
    ...(halves.length === 2 ? zeros : []),
    ...rest.map((word) => parseInt(word, 16)),
    ...tail,
  ];
}

function ipv6Public(words: number[]): boolean {
  const embedded = (hi: number, lo: number) => ipv4Public(((hi << 16) | lo) >>> 0);
  if (words.slice(0, 5).every((word) => word === 0)) {
    // ::ffff:a.b.c.d (IPv4-mapped) is the IPv4 address; ::, ::1, ::a.b.c.d and the rest of
    // ::/80 are not public.
    return words[5] === 0xffff && embedded(words[6], words[7]);
  }
  // 64:ff9b::/96 (NAT64) reaches the embedded IPv4 address.
  if (words[0] === 0x64 && words[1] === 0xff9b && words.slice(2, 6).every((w) => w === 0)) {
    return embedded(words[6], words[7]);
  }
  // 2002::/16 (6to4) reaches the IPv4 address in words 1 and 2.
  if (words[0] === 0x2002) return embedded(words[1], words[2]);
  // 2001::/23 holds Teredo, ORCHID and other protocol assignments; 2001:db8::/32 and
  // 3fff::/20 are documentation.
  if (words[0] === 0x2001 && (words[1] < 0x200 || words[1] === 0xdb8)) return false;
  if (words[0] === 0x3fff && words[1] < 0x1000) return false;
  // Only global unicast (2000::/3). Unique local (fc00::/7), link-local (fe80::/10),
  // multicast and everything else fall outside it.
  return (words[0] & 0xe000) === 0x2000;
}

/**
 * True for a globally routable address. Private, loopback, link-local, CGNAT, metadata,
 * documentation and multicast ranges are not, in IPv4 or IPv6, including IPv4 addresses
 * carried inside IPv6 (mapped, NAT64, 6to4). Anything that is not a plain address is not.
 */
export function isPublicAddress(address: string): boolean {
  if (address.includes("%")) return false; // a zone: link-local by definition
  const kind = isIP(address);
  if (kind === 4) {
    const value = ipv4Value(address);
    return value !== null && ipv4Public(value);
  }
  if (kind === 6) {
    const words = ipv6Words(address);
    return words !== null && ipv6Public(words);
  }
  return false;
}

export interface PinnedAddress {
  address: string;
  family: 4 | 6;
}

/** The address to connect to: null unless every one is public. IPv4 first. */
export function pickPublicAddress(addresses: readonly string[]): PinnedAddress | null {
  if (addresses.length === 0 || !addresses.every(isPublicAddress)) return null;
  const address = addresses.find((entry) => isIP(entry) === 4) ?? addresses[0];
  return { address, family: isIP(address) === 6 ? 6 : 4 };
}

/* ───────────────────────── Fetching ───────────────────────── */

export const MAX_BYTES = 64 * 1024;
export const TIMEOUT_MS = 3000;
export const MAX_REDIRECTS = 3;

/** SVG is left out on purpose: it can carry script, and this route serves from our origin. */
export const IMAGE_TYPES: ReadonlySet<string> = new Set([
  "image/x-icon",
  "image/vnd.microsoft.icon",
  "image/png",
  "image/gif",
  "image/jpeg",
  "image/webp",
]);

export interface Icon {
  bytes: Uint8Array<ArrayBuffer>;
  type: string;
}

/** One hop: the checked name, the path, and the checked address to connect to. */
export interface PinnedTarget extends PinnedAddress {
  host: string;
  path: string;
}

export interface UpstreamResponse {
  status: number;
  headers: IncomingHttpHeaders;
  body: AsyncIterable<Uint8Array>;
  /** Drop the connection without reading the body. Safe to call more than once. */
  cancel(): void;
}

export interface FaviconTransport {
  /** Every address of `host`. Must stop when `signal` aborts. */
  resolve(host: string, signal: AbortSignal): Promise<string[]>;
  /** GET `https://host/path`, connected to `address` only. */
  get(target: PinnedTarget, signal: AbortSignal): Promise<UpstreamResponse>;
}

/** A socket `lookup` that answers every name with the one checked address. */
export function pinnedLookup(address: string, family: 4 | 6): LookupFunction {
  return ((_hostname: string, options: { all?: boolean }, callback: (...args: unknown[]) => void) => {
    if (options?.all) callback(null, [{ address, family }]);
    else callback(null, address, family);
  }) as unknown as LookupFunction;
}

/** Request options for one pinned hop: TLS on the name, the socket on the address. */
export function pinnedRequestOptions(target: PinnedTarget, signal: AbortSignal): RequestOptions {
  return {
    protocol: "https:",
    host: target.host,
    servername: target.host,
    port: 443,
    path: target.path,
    method: "GET",
    // Fresh headers: nothing from the reader's request is passed on.
    headers: { host: target.host, accept: "image/*", "user-agent": "favicon-fetch" },
    lookup: pinnedLookup(target.address, target.family),
    family: target.family,
    // No shared pool: a socket is never reused for another name or address.
    agent: false,
    rejectUnauthorized: true,
    signal,
  };
}

function normalizedAddress(address: string | undefined): string {
  return (address ?? "").toLowerCase().replace(/^::ffff:(?=\d+\.\d+\.\d+\.\d+$)/, "");
}

function wrap(response: IncomingMessage): UpstreamResponse {
  return {
    status: response.statusCode ?? 0,
    headers: response.headers,
    body: response,
    cancel: () => {
      if (!response.destroyed) response.destroy();
    },
  };
}

async function resolveAll(host: string, signal: AbortSignal): Promise<string[]> {
  const resolver = new Resolver({ timeout: TIMEOUT_MS, tries: 1 });
  const onAbort = () => resolver.cancel();
  signal.addEventListener("abort", onAbort, { once: true });
  try {
    const [v4, v6] = await Promise.allSettled([resolver.resolve4(host), resolver.resolve6(host)]);
    return [
      ...(v4.status === "fulfilled" ? v4.value : []),
      ...(v6.status === "fulfilled" ? v6.value : []),
    ];
  } finally {
    signal.removeEventListener("abort", onAbort);
  }
}

function pinnedGet(target: PinnedTarget, signal: AbortSignal): Promise<UpstreamResponse> {
  return new Promise((resolve, reject) => {
    const request = httpsRequest(pinnedRequestOptions(target, signal), (response) => {
      // The lookup is pinned; this only proves it.
      if (normalizedAddress(response.socket?.remoteAddress) !== normalizedAddress(target.address)) {
        response.destroy();
        reject(new Error("connected to an address that was not checked"));
        return;
      }
      resolve(wrap(response));
    });
    request.on("error", reject);
    request.end();
  });
}

export const nodeTransport: FaviconTransport = { resolve: resolveAll, get: pinnedGet };

/** Settles with `work`, or rejects as soon as `signal` aborts. */
function beforeDeadline<T>(work: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(signal.reason);
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(signal.reason);
    signal.addEventListener("abort", onAbort, { once: true });
    work.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

function header(headers: IncomingHttpHeaders, name: string): string {
  const value = headers[name];
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Reads the body up to the size limit, before the deadline. Null when it is larger. */
async function readCapped(
  response: UpstreamResponse,
  signal: AbortSignal,
): Promise<Uint8Array<ArrayBuffer> | null> {
  const declared = Number(header(response.headers, "content-length") || NaN);
  if (Number.isFinite(declared) && declared > MAX_BYTES) return null;
  const iterator = response.body[Symbol.asyncIterator]();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await beforeDeadline(iterator.next(), signal);
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BYTES) return null;
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

/** The next hop's checked name and path, or null when the URL may not be asked. */
function hopTarget(url: URL): { host: string; path: string } | null {
  if (url.protocol !== "https:" || url.port !== "" || url.username || url.password) return null;
  const host = publicHost(url.hostname);
  return host ? { host, path: `${url.pathname}${url.search}` } : null;
}

/**
 * `https://<host>/favicon.ico`, following at most three redirects, every hop checked and
 * pinned. Null on any miss: a refused hop, a private address, a bad status or type, a body
 * over the limit, or the deadline.
 */
export async function fetchIcon(
  host: string,
  transport: FaviconTransport = nodeTransport,
  timeoutMs: number = TIMEOUT_MS,
): Promise<Icon | null> {
  const signal = AbortSignal.timeout(timeoutMs);
  let url: URL;
  try {
    url = new URL(`https://${host}/favicon.ico`);
  } catch {
    return null;
  }
  let current: UpstreamResponse | null = null;
  try {
    for (let hop = 0; hop <= MAX_REDIRECTS; hop += 1) {
      const next = hopTarget(url);
      if (!next) return null;
      const pinned = pickPublicAddress(
        await beforeDeadline(transport.resolve(next.host, signal), signal),
      );
      if (!pinned) return null;
      current = await beforeDeadline(transport.get({ ...next, ...pinned }, signal), signal);
      const response = current;
      if (response.status >= 300 && response.status < 400) {
        const location = header(response.headers, "location");
        response.cancel();
        current = null;
        if (!location) return null;
        url = new URL(location, url);
        continue;
      }
      if (response.status < 200 || response.status >= 300) return null;
      const type = header(response.headers, "content-type").split(";")[0].trim().toLowerCase();
      if (!IMAGE_TYPES.has(type)) return null;
      const bytes = await readCapped(response, signal);
      return bytes ? { bytes, type } : null;
    }
    return null;
  } catch {
    /* deadline, DNS, TLS, a refused socket or a malformed redirect: a miss */
    return null;
  } finally {
    // Whatever was not read to the end is dropped here: rejected statuses and types, a
    // body over the limit, a deadline mid-body. A fully read body is already closed.
    current?.cancel();
  }
}

/* ───────────────────────── Sessions ───────────────────────── */

const SESSION_OK_TTL_MS = 60 * 1000;
const SESSION_BAD_TTL_MS = 10 * 1000;
const SESSION_MAX_ENTRIES = 1000;

/**
 * Whether a session token belongs to a signed-in reader, asked of the API and remembered
 * briefly so a page of favicons costs one check, not one per icon. Tokens are keyed as
 * given (they are only held in this process's memory) and the map is bounded.
 */
export class SessionCheck {
  private readonly cache = new Map<string, { ok: boolean; expires: number }>();
  private readonly inFlight = new Map<string, Promise<boolean>>();
  private readonly verify: (token: string) => Promise<boolean>;
  private readonly now: () => number;

  constructor(verify: (token: string) => Promise<boolean>, now: () => number = () => Date.now()) {
    this.verify = verify;
    this.now = now;
  }

  async isValid(token: string | null | undefined): Promise<boolean> {
    if (!token) return false;
    const cached = this.cache.get(token);
    if (cached && cached.expires > this.now()) return cached.ok;
    const pending = this.inFlight.get(token);
    if (pending) return pending;
    const work = this.verify(token)
      .catch(() => false)
      .then((ok) => {
        if (this.cache.size >= SESSION_MAX_ENTRIES) {
          const oldest = this.cache.keys().next().value;
          if (oldest !== undefined) this.cache.delete(oldest);
        }
        this.cache.delete(token);
        this.cache.set(token, {
          ok,
          expires: this.now() + (ok ? SESSION_OK_TTL_MS : SESSION_BAD_TTL_MS),
        });
        this.inFlight.delete(token);
        return ok;
      });
    this.inFlight.set(token, work);
    return work;
  }
}

/** Asks `GET {apiBase}/auth/me` with only the session cookie. True only on a 200. */
export async function verifySessionWithApi(
  apiBase: string,
  cookieName: string,
  token: string,
  fetcher: typeof fetch = fetch,
): Promise<boolean> {
  if (!/^[\x21-\x7e]+$/.test(token) || token.includes(";")) return false;
  const response = await fetcher(`${apiBase}/auth/me`, {
    method: "GET",
    headers: { cookie: `${cookieName}=${token}`, accept: "application/json" },
    redirect: "manual",
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  await response.body?.cancel();
  return response.status === 200;
}
