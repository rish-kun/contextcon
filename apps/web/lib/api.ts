/**
 * Minimal client for the DealProof FastAPI service.
 * NEXT_PUBLIC_API_URL is inlined at build time; when unset or empty it falls
 * back to the local API for development.
 */
const DEFAULT_API_URL = "http://localhost:8000";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL?.trim() || DEFAULT_API_URL
).replace(/\/+$/, "");

/** True for bodies we serialize as JSON ourselves: strings and plain objects. */
function isJsonBody(body: unknown): boolean {
  if (typeof body === "string") return true;
  if (body === null || typeof body !== "object") return false;
  const proto = Object.getPrototypeOf(body);
  return proto === Object.prototype || proto === null || Array.isArray(body);
}

export type ApiInit = Omit<RequestInit, "body"> & {
  body?: RequestInit["body"] | Record<string, unknown> | unknown[];
};

export async function apiFetch<T>(path: string, init?: ApiInit): Promise<T> {
  const url = `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init?.headers);
  let body = init?.body;

  if (body !== undefined && body !== null && isJsonBody(body)) {
    if (typeof body !== "string") body = JSON.stringify(body);
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...init,
    headers,
    body: body as BodyInit | null | undefined,
  });
  if (!response.ok) {
    throw new Error(`API ${response.status} ${response.statusText}: ${path}`);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<{ status: string }> {
  return apiFetch("/health");
}
