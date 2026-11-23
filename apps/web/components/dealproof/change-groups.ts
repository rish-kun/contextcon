import type { AssessmentChange, ChangeCause, ClaimStatus } from "@/lib/types";

export type ClaimChange = Extract<AssessmentChange, { kind: "claim_status" }>;
export type DispositionChange = Extract<AssessmentChange, { kind: "disposition" }>;
export type ValueChange = Extract<AssessmentChange, { kind: "value" }>;

/** Several claims that took a status for one shared reason: drawn as one row that opens. */
export interface ClaimGroup {
  key: string;
  cause: Extract<ChangeCause, { kind: "policy" }>;
  changes: ClaimChange[];
  /** Every claim in the group had no status before. */
  allFirst: boolean;
  /** How many ended at each status, most decision-relevant first. Zero counts are left out. */
  counts: { status: ClaimStatus; count: number }[];
}

export interface OrganisedChanges {
  /** What the reader decides on: first. */
  disposition: DispositionChange[];
  /** The judgments and figures that moved. */
  judgments: ValueChange[];
  /** Claim changes with a cause of their own, listed one by one: contradicted and supported first. */
  claims: ClaimChange[];
  /** Claim changes that share a cause, each group collapsed to one row. */
  groups: ClaimGroup[];
}

/** A contradiction or a confirmation changes a decision; an open answer changes it least. */
const RELEVANCE: ClaimStatus[] = [
  "contradicted",
  "supported",
  "conflicting_evidence",
  "partially_corroborated",
  "cannot_verify",
  "not_checked",
];

const rank = (status: ClaimStatus) => RELEVANCE.indexOf(status);

/**
 * Orders a version's changes for reading and folds repeats. A scoring-policy update that
 * touched several claims is one group; a claim that moved on evidence, or for a reason
 * of its own, stays a row of its own so its source is seen.
 */
export function organiseChanges(changes: AssessmentChange[]): OrganisedChanges {
  const disposition: DispositionChange[] = [];
  const judgments: ValueChange[] = [];
  const single: ClaimChange[] = [];
  const byPolicy = new Map<string, ClaimChange[]>();

  for (const change of changes) {
    if (change.kind === "disposition") disposition.push(change);
    else if (change.kind === "value") judgments.push(change);
    else if (change.cause?.kind === "policy" && change.evidence.length === 0) {
      const key = `${change.cause.from}→${change.cause.to}`;
      byPolicy.set(key, [...(byPolicy.get(key) ?? []), change]);
    } else single.push(change);
  }

  const groups: ClaimGroup[] = [];
  for (const [key, members] of byPolicy) {
    // One claim is not a repeat: it reads better as its own row.
    if (members.length < 2) {
      single.push(...members);
      continue;
    }
    const sorted = [...members].sort((a, b) => rank(a.after) - rank(b.after));
    groups.push({
      key,
      cause: members[0].cause as ClaimGroup["cause"],
      changes: sorted,
      allFirst: members.every((change) => change.before === null),
      counts: RELEVANCE.map((status) => ({
        status,
        count: members.filter((change) => change.after === status).length,
      })).filter((entry) => entry.count > 0),
    });
  }

  return {
    disposition,
    judgments,
    claims: single.sort((a, b) => rank(a.after) - rank(b.after)),
    groups,
  };
}

/**
 * Policy versions are dated: "2026-11-22.2". Two from the same month differ only in the
 * tail, so the pair reads "22.2 → 22.3"; anything else is shown whole.
 */
export function shortPolicyPair(from: string, to: string): [string, string] {
  const shape = /^(\d{4}-\d{2}-)(\d{2}\.\d+)$/;
  const a = shape.exec(from);
  const b = shape.exec(to);
  return a && b && a[1] === b[1] ? [a[2], b[2]] : [from, to];
}
