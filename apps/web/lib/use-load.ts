"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";

export type Load<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string; code: number | null };

/** The reason a call failed, in the reader's words. */
export function loadErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has ended";
    if (error.status === 502 || error.status === 503 || error.status === 504) {
      return "The DealProof API did not respond. Nothing was changed";
    }
    if (typeof error.detail === "string" && error.detail.trim()) return error.detail;
    return fallback;
  }
  return "The request did not reach DealProof. Check your connection and try again";
}

/**
 * Loads one thing by key and exposes its state plus a retry. The last good copy stays on
 * screen while a retry is in flight, so a refresh never blanks the page. `load` may be an
 * inline function: it is re-run only when `key` changes or on retry.
 */
export function useLoad<T>(key: string, load: () => Promise<T>, fallback: string): [Load<T>, () => void] {
  const [state, setState] = useState<{ key: string; load: Load<T> }>({ key, load: { status: "loading" } });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setState({ key, load: { status: "ready", data } });
      },
      (error: unknown) => {
        if (cancelled) return;
        setState({
          key,
          load: {
            status: "error",
            message: loadErrorMessage(error, fallback),
            code: error instanceof ApiError ? error.status : null,
          },
        });
      },
    );
    return () => {
      cancelled = true;
    };
    // `load` is deliberately left out: callers pass inline functions, and the key names the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt, fallback]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return [state.key === key ? state.load : { status: "loading" }, retry];
}
