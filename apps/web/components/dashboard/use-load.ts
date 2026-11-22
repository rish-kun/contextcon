"use client";

import { useCallback, useEffect, useState } from "react";
import { describeError } from "@/components/app-shell";
import { getCase, type CaseDetail, type CaseSummary } from "@/lib/api/client";

export type Load<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };

/**
 * Runs one API call on mount and exposes its state plus a retry.
 * `load` must be a stable reference (a module-level function).
 */
export function useLoad<T>(load: () => Promise<T>, fallback: string): [Load<T>, () => void] {
  const [state, setState] = useState<Load<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setState({ status: "ready", data });
      },
      (error: unknown) => {
        if (!cancelled) setState({ status: "error", message: describeError(error, fallback) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, fallback, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return [state, retry];
}

/** How many rows get their full record loaded for claim counts and the criteria strip. */
const DETAIL_LIMIT = 12;

/**
 * The list endpoint carries a claim total but not the split by status, and the fit score
 * but not its criteria. Both come from each case's own record, loaded per row. A row whose
 * record has not arrived, or failed to, shows only what the list returned.
 */
export function useCaseDetails(cases: CaseSummary[]): Record<string, CaseDetail> {
  const [details, setDetails] = useState<Record<string, CaseDetail>>({});
  const key = cases
    .slice(0, DETAIL_LIMIT)
    .map((item) => `${item.id}@${item.updated_at}`)
    .join("|");

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    for (const entry of key.split("|")) {
      const id = entry.slice(0, entry.lastIndexOf("@"));
      getCase(id).then(
        (detail) => {
          if (!cancelled) setDetails((current) => ({ ...current, [id]: detail }));
        },
        () => {},
      );
    }
    return () => {
      cancelled = true;
    };
  }, [key]);

  return details;
}
