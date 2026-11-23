"use client";

import { getWorkspace, type CaseSummary } from "@/lib/api/client";
import { onSessionChange } from "@/lib/api/session-scope";
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

/**
 * One cached read, owned by the account it was made for. The API gives the browser no
 * workspace id, and a user belongs to one workspace, so the user id names both.
 */
let cache: { owner: string; at: number; promise: Promise<Workspace> } | null = null;
/** The signed-in user, set by the shell once `GET /auth/me` has answered. */
let owner: string | null = null;

/** Drop the cached cases. Nothing read before this call is served after it. */
export function clearWorkspaceCache(): void {
  cache = null;
}

/**
 * Name the account the cache may serve, or null when nobody is signed in. A change of
 * account drops the cache: sign-out and sign-in are client navigations, so this module
 * outlives them, and one account's cases must never reach the next account in the tab.
 */
export function setWorkspaceOwner(userId: string | null): void {
  if (owner === userId) return;
  owner = userId;
  cache = null;
}

// Every sign-in, sign-out and sign-up, whether or not the shell is mounted to see it.
onSessionChange(() => {
  owner = null;
  cache = null;
});

async function read(): Promise<Workspace> {
  const { cases, records } = await getWorkspace();
  return {
    cases: [...cases].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    records: Object.fromEntries(records.map((record) => [record.case_id, record])),
    loadedAt: new Date().toISOString(),
  };
}

/**
 * One read shared by every screen for a few seconds, so moving between them does not
 * refetch. Shared only within one account: with no known owner the read is not cached,
 * and a cached read is served only to the account it was made for.
 */
export function loadWorkspace(force = false): Promise<Workspace> {
  const reader = owner;
  if (reader === null) return read();
  if (!force && cache && cache.owner === reader && Date.now() - cache.at < TTL_MS) return cache.promise;
  const promise = read();
  cache = { owner: reader, at: Date.now(), promise };
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
      clearWorkspaceCache();
      retry();
    },
  ];
}
