import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { ApiError } from "@/lib/api/client";

/** Forwards the reader's session cookie on server-side API calls. */
export async function sessionInit(): Promise<RequestInit> {
  const cookie = (await cookies()).toString();
  return cookie ? { headers: { cookie } } : {};
}

export type Loaded<T> = { ok: true; data: T } | { ok: false; status: number | null };

/**
 * Runs a server-side read. A missing case is a 404 page. Any other failure is returned,
 * so the tab can say it could not load instead of showing an empty case.
 */
export async function load<T>(read: (init: RequestInit) => Promise<T>): Promise<Loaded<T>> {
  try {
    return { ok: true, data: await read(await sessionInit()) };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return { ok: false, status: error instanceof ApiError ? error.status : null };
  }
}
