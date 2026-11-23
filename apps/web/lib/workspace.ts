"use client";

import { getWorkspace, type CaseSummary } from "@/lib/api/client";
import { type Load, useLoad } from "@/lib/use-load";
import type { CaseRecord } from "@/lib/workspace-state";

/**
 * The book of work in one read (`GET /workspace`): every case's list row and the part of
 * its record that the screens spanning cases read (Overview, Pipeline, Signals,
 * Approvals, Companies, the app shell). The full record of one case is `getCase`. The
 * states derived from a record are in `workspace-state.ts`.
 */
const TTL_MS = 20_000;

export interface Workspace {
  /** Every case, newest update first. */
  cases: CaseSummary[];
  /** Each case's record, by case id. */
  records: Record<string, CaseRecord>;
  loadedAt: string;
}

let cache: { at: number; promise: Promise<Workspace> } | null = null;

async function read(): Promise<Workspace> {
  const { cases, records } = await getWorkspace();
  return {
    cases: [...cases].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    records: Object.fromEntries(records.map((record) => [record.case_id, record])),
    loadedAt: new Date().toISOString(),
  };
}

/** One read shared by every screen for a few seconds, so moving between them does not refetch. */
export function loadWorkspace(force = false): Promise<Workspace> {
  if (!force && cache && Date.now() - cache.at < TTL_MS) return cache.promise;
  const promise = read();
  cache = { at: Date.now(), promise };
  promise.catch(() => {
    if (cache?.promise === promise) cache = null;
  });
  return promise;
}

export function useWorkspace(): [Load<Workspace>, () => void] {
  const [state, retry] = useLoad("workspace", () => loadWorkspace(), "The cases were not returned");
  return [
    state,
    () => {
      cache = null;
      retry();
    },
  ];
}
