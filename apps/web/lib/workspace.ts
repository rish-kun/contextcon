"use client";

import {
  getCase,
  listCases,
  type CaseDetail,
  type CaseSummary,
} from "@/lib/api/client";
import { type Load, useLoad } from "@/lib/use-load";
import { CLAIM_STATUSES, type ClaimStatusCounts } from "@/lib/types";

/**
 * The book of work, composed in the browser: the case list plus each case's own record
 * for the most recently updated cases. There is no aggregate endpoint yet, so screens
 * that span cases (Overview, Pipeline, Signals, Approvals, Compare) read from here and
 * say how many cases they cover. Wanted from the API later: `GET /signals`,
 * `GET /approvals` and status counts on `CaseSummary`.
 */
export const WORKSPACE_DETAIL_LIMIT = 20;
const TTL_MS = 20_000;

export interface Workspace {
  /** Every case, newest update first. */
  cases: CaseSummary[];
  /** Full records, by case id, for the first `WORKSPACE_DETAIL_LIMIT` cases that loaded. */
  details: Record<string, CaseDetail>;
  /** Cases whose record was not read because of the limit. */
  beyondLimit: number;
  /** Cases within the limit whose record failed to load. */
  failed: number;
  loadedAt: string;
}

let cache: { at: number; promise: Promise<Workspace> } | null = null;

async function read(): Promise<Workspace> {
  const cases = [...(await listCases())].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const within = cases.slice(0, WORKSPACE_DETAIL_LIMIT);
  const settled = await Promise.allSettled(within.map((item) => getCase(item.id)));
  const details: Record<string, CaseDetail> = {};
  let failed = 0;
  settled.forEach((result, index) => {
    if (result.status === "fulfilled") details[within[index].id] = result.value;
    else failed += 1;
  });
  return {
    cases,
    details,
    beyondLimit: cases.length - within.length,
    failed,
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

/** "from the 20 most recently updated cases", for a panel that could not read them all. */
export function coverageNote(workspace: Workspace): string | null {
  const read = Object.keys(workspace.details).length;
  if (workspace.beyondLimit === 0 && workspace.failed === 0) return null;
  return `from ${read} of ${workspace.cases.length} cases, most recently updated first`;
}

/* ───────────────────────── Derived states ───────────────────────── */

export function claimCounts(detail: CaseDetail | undefined): ClaimStatusCounts | null {
  if (!detail) return null;
  const counts = Object.fromEntries(CLAIM_STATUSES.map((status) => [status, 0])) as ClaimStatusCounts;
  for (const claim of detail.claims) counts[claim.status] += 1;
  return counts;
}

export type RequestState = "none" | "draft" | "approved" | "sending" | "sent" | "suppressed" | "failed" | "unknown";

export const REQUEST_STATE_LABEL: Record<RequestState, string> = {
  none: "No request",
  draft: "Draft · awaiting approval",
  approved: "Approved · not sent yet",
  sending: "Sending",
  sent: "Sent once",
  suppressed: "Suppressed (test mode) · not sent",
  failed: "Failed · not sent",
  unknown: "Unknown · not confirmed",
};

/**
 * Where a case's seller request stands. A request list with documents and no saved
 * message is a draft too: DealProof has written it and no one has approved it.
 */
export function requestState(detail: CaseDetail | undefined): RequestState {
  if (!detail) return "none";
  const status = detail.message?.status;
  if (!status) return (detail.request_list?.items.length ?? 0) > 0 ? "draft" : "none";
  return status === "suppressed_test_mode" ? "suppressed" : status;
}

export interface Attention {
  /** What is waiting, in words. */
  what: string;
  /** Path under the case to go to. Empty for the overview. */
  segment: string;
}

/** Everything about a case that is waiting on a person, most pressing first. */
export function attention(item: CaseSummary, detail: CaseDetail | undefined): Attention[] {
  const out: Attention[] = [];
  if (item.identity_state !== "confirmed") {
    const candidates = detail?.identity.candidates.length ?? 0;
    out.push({
      what: `Identity ${item.identity_state === "ambiguous" ? "ambiguous" : "unresolved"}${candidates ? ` · ${candidates} ${candidates === 1 ? "candidate" : "candidates"}` : ""}`,
      segment: "identity",
    });
  }
  if (item.status === "failed") out.push({ what: "Verification did not finish", segment: "cost" });
  const request = requestState(detail);
  if (request === "draft") out.push({ what: "Request awaiting approval", segment: "request" });
  if (request === "approved") out.push({ what: "Request approved, not sent yet", segment: "request" });
  if (request === "failed") out.push({ what: "Request failed · not sent", segment: "request" });
  if (request === "unknown") out.push({ what: "Send result unknown", segment: "request" });
  const notChecked = claimCounts(detail)?.not_checked ?? 0;
  if (notChecked > 0) {
    out.push({
      what: notChecked === 1 ? "1 check was not run" : `${notChecked} checks were not run`,
      segment: "claims?status=not_checked",
    });
  }
  return out;
}

export const PIPELINE_COLUMNS = ["identity", "verifying", "failed", "assessed", "drafted", "sent"] as const;
export type PipelineColumn = (typeof PIPELINE_COLUMNS)[number];

export const PIPELINE_LABEL: Record<PipelineColumn, string> = {
  identity: "Identity",
  verifying: "Verifying",
  failed: "Failed",
  assessed: "Assessed",
  drafted: "Request drafted",
  sent: "Request sent",
};

/** The column a case sits in. DealProof decides it from the record; nobody drags a card. */
export function pipelineColumn(item: CaseSummary, detail: CaseDetail | undefined): PipelineColumn {
  if (item.identity_state !== "confirmed") return "identity";
  if (item.status === "verifying") return "verifying";
  if (item.status === "failed") return "failed";
  const request = requestState(detail);
  if (request === "sent" || request === "suppressed") return "sent";
  if (request !== "none") return "drafted";
  return "assessed";
}
