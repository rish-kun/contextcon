/**
 * States derived from a case's workspace record (`GET /workspace`), shared by the screens
 * that span cases. Kept free of value imports so `node --test` can run
 * `workspace-state.test.mjs` directly.
 */
import type { CaseSummary, ClaimOut, WorkspaceCaseOut } from "@/lib/api/client";
import type { ClaimStatusCounts } from "@/lib/types";

/** What the cross-case screens know about one case beyond its list row. */
export type CaseRecord = WorkspaceCaseOut;

/** Claims by status, from the record's counts. */
export function claimCounts(record: CaseRecord | undefined): ClaimStatusCounts | null {
  if (!record) return null;
  const { supported, partially_corroborated, conflicting_evidence, contradicted, cannot_verify, not_checked } =
    record.claim_counts;
  return { supported, partially_corroborated, conflicting_evidence, contradicted, cannot_verify, not_checked };
}

/** Claims by status, counted from a full case record's claims. */
export function countClaims(claims: Pick<ClaimOut, "status">[]): ClaimStatusCounts {
  const counts: ClaimStatusCounts = {
    supported: 0,
    partially_corroborated: 0,
    conflicting_evidence: 0,
    contradicted: 0,
    cannot_verify: 0,
    not_checked: 0,
  };
  for (const claim of claims) counts[claim.status] += 1;
  return counts;
}

/** How many claims the record holds, of any status. */
export function claimTotal(record: CaseRecord | undefined): number {
  const counts = claimCounts(record);
  return counts ? Object.values(counts).reduce((sum, n) => sum + n, 0) : 0;
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
export function requestState(record: CaseRecord | undefined): RequestState {
  if (!record) return "none";
  const status = record.message?.status;
  if (!status) return (record.request_list?.items.length ?? 0) > 0 ? "draft" : "none";
  return status === "suppressed_test_mode" ? "suppressed" : status;
}

export interface Attention {
  /** What is waiting, in words. */
  what: string;
  /** Path under the case to go to. Empty for the overview. */
  segment: string;
}

/** Everything about a case that is waiting on a person, most pressing first. */
export function attention(item: CaseSummary, record: CaseRecord | undefined): Attention[] {
  const out: Attention[] = [];
  if (item.identity_state !== "confirmed") {
    const candidates = record?.identity_candidates ?? 0;
    out.push({
      what: `Identity ${item.identity_state === "ambiguous" ? "ambiguous" : "unresolved"}${candidates ? ` · ${candidates} ${candidates === 1 ? "candidate" : "candidates"}` : ""}`,
      segment: "identity",
    });
  }
  if (item.status === "failed") out.push({ what: "Verification did not finish", segment: "cost" });
  const request = requestState(record);
  if (request === "draft") out.push({ what: "Request awaiting approval", segment: "request" });
  if (request === "approved") out.push({ what: "Request approved, not sent yet", segment: "request" });
  if (request === "failed") out.push({ what: "Request failed · not sent", segment: "request" });
  if (request === "unknown") out.push({ what: "Send result unknown", segment: "request" });
  const notChecked = claimCounts(record)?.not_checked ?? 0;
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
export function pipelineColumn(item: CaseSummary, record: CaseRecord | undefined): PipelineColumn {
  if (item.identity_state !== "confirmed") return "identity";
  if (item.status === "verifying") return "verifying";
  if (item.status === "failed") return "failed";
  const request = requestState(record);
  if (request === "sent" || request === "suppressed") return "sent";
  if (request !== "none") return "drafted";
  return "assessed";
}

/**
 * The list row with disposition and fit filled from the case's latest assessment when the
 * list did not carry them, so a board never shows less than the case page does.
 */
export function withAssessment(item: CaseSummary, record: CaseRecord | undefined): CaseSummary {
  if (!record) return item;
  const assessment = record.assessment;
  return {
    ...item,
    disposition: item.disposition ?? assessment?.disposition ?? null,
    fit_state: item.fit_state ?? assessment?.fit_state ?? record.opportunity.fit_state ?? null,
    fit: item.fit ?? assessment?.fit ?? record.opportunity.fit ?? null,
    assessable_pct: item.assessable_pct ?? assessment?.assessable_pct ?? record.opportunity.assessable_pct ?? null,
  };
}
