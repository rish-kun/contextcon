/**
 * Which hosts the favicon proxy (`app/api/favicon/route.ts`) may ask. Kept apart from the
 * route so the rules can be tested on their own (`favicon-rules.test.mjs`).
 */
import { isIP } from "node:net";

/**
 * The proxy is off unless `FAVICON_PROXY_ENABLED` is exactly `true` (server-only env).
 * Off, the route answers 404 to everything and the ticker shows source-class glyphs.
 */
export function faviconProxyEnabled(env: Record<string, string | undefined>): boolean {
  return env.FAVICON_PROXY_ENABLED?.trim().toLowerCase() === "true";
}

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

const HOST_PATTERN =
  /^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$/;

/** A public host name in its canonical form, or null. No IP literals, no single labels. */
export function publicHost(input: string | null | undefined): string | null {
  if (!input) return null;
  const host = input.trim().toLowerCase().replace(/\.$/, "");
  if (!HOST_PATTERN.test(host) || isIP(host) !== 0) return null;
  if (RESERVED_SUFFIXES.some((suffix) => host.endsWith(suffix))) return null;
  return host;
}

/** True for a globally routable address. Private, loopback, link-local and metadata ranges are not. */
export function isPublicAddress(address: string): boolean {
  const kind = isIP(address);
  if (kind === 4) {
    const [a, b] = address.split(".").map(Number);
    if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
    if (a === 100 && b >= 64 && b <= 127) return false; // carrier-grade NAT
    if (a === 169 && b === 254) return false; // link-local, cloud metadata
    if (a === 172 && b >= 16 && b <= 31) return false;
    if (a === 192 && (b === 168 || b === 0)) return false;
    if (a === 198 && (b === 18 || b === 19)) return false;
    return true;
  }
  if (kind === 6) {
    const lower = address.toLowerCase();
    if (lower === "::" || lower === "::1") return false;
    const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(lower);
    if (mapped) return isPublicAddress(mapped[1]);
    // Global unicast is 2000::/3. Unique local, link-local and multicast fall outside it.
    return /^[23]/.test(lower);
  }
  return false;
}
