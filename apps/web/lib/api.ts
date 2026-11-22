/**
 * Minimal client for the DealProof FastAPI service.
 * NEXT_PUBLIC_API_URL is inlined at build time; it defaults to the local API.
 */
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`API ${response.status} ${response.statusText}: ${path}`);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<{ status: string }> {
  return apiFetch("/health");
}
