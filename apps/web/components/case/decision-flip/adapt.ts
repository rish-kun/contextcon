/**
 * Reads the DecisionFlip analysis off the case and puts names on its items. Pure
 * functions. Nothing here re-derives an outcome: the rules ran on the server and this
 * only words what they returned.
 */
import { type CaseDetail, isFixtureMode } from "@/lib/api/client";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import { CLAIM_STATUSES, type ClaimStatus, type Disposition } from "@/lib/types";
import { CATEGORY_LABEL } from "../adapt";
import { FIXTURE_DECISION_FLIP } from "./fixture";
import type { DecisionFlip, FlipItem, FlipOutcome, RequestPriority } from "./types";

type RequestItem = NonNullable<CaseDetail["request_list"]>["items"][number];

/**
 * The analysis for the case's latest assessment, or null when none was computed. The
 * `decision_flip` section of `GET /cases/{id}` is the source; in fixture mode the canned
 * analysis stands in until the fixtures carry the section themselves.
 */
export function readDecisionFlip(detail: CaseDetail): DecisionFlip | null {
  if (!detail.assessment) return null;
  const served = (detail as { decision_flip?: DecisionFlip | null }).decision_flip;
  const flip = served ?? (isFixtureMode ? (FIXTURE_DECISION_FLIP[detail.case.id] ?? null) : null);
  // An analysis of an older version says nothing about the current one.
  return flip && flip.assessment_version === detail.assessment.version ? flip : null;
}

export const isClaimStatus = (value: string): value is ClaimStatus =>
  (CLAIM_STATUSES as readonly string[]).includes(value);

const STATE_WORDS: Record<string, string> = {
  unknown: "Unknown",
  absent: "No claim made",
  not_assessed: "Not assessed",
  ambiguous: "Identity ambiguous",
  unresolved: "Identity unresolved",
};

/** Where the item stands today, in the product's words. */
export function stateLabel(item: FlipItem): string {
  if (isClaimStatus(item.current_state)) return CLAIM_STATUS_LABEL[item.current_state];
  return STATE_WORDS[item.current_state] ?? item.current_state.replaceAll("_", " ");
}

export interface NamedItem {
  /** "Funding", "Must-have", "Identity". */
  label: string;
  /** The claim in the seller's words, or the criterion. */
  text: string | null;
  /** The ledger number, for a claim. */
  claimNumber: number | null;
}

/** The item's name, from the read-time label when the API sent one, else from the case. */
export function nameItem(item: FlipItem, detail: CaseDetail): NamedItem {
  const claim = item.claim_id ? detail.claims.find((c) => c.id === item.claim_id) : undefined;
  const criterion = item.criterion_id
    ? detail.opportunity.criterion_results.find((c) => c.criterion_id === item.criterion_id)
    : undefined;
  const category = (claim?.category ?? item.check) as keyof typeof CATEGORY_LABEL | null | undefined;

  let label = item.label ?? null;
  if (!label) {
    if (item.kind === "identity") label = "Identity";
    else if (item.kind === "financial_inputs") label = "Financial inputs";
    else if (item.kind === "criterion") label = criterion?.kind === "must" ? "Must-have" : "Preference";
    else label = (category && CATEGORY_LABEL[category]) || "Required check";
  }
  const text =
    item.claim_text ??
    claim?.original_text ??
    criterion?.label ??
    (item.kind === "check_gap" ? "No claim was made on this" : null);
  return { label, text, claimNumber: claim?.number ?? null };
}

/** "would be Prioritise", or "stays Investigate further" when nothing moves. */
export function outcomeWords(outcome: FlipOutcome, current: Disposition): string {
  const name = DISPOSITION_LABEL[outcome.disposition];
  return outcome.disposition === current ? `stays ${name}` : `would be ${name}`;
}

/** "2 blockers to Prioritise". Null when the case has no target to move to. */
export function blockerLine(flip: DecisionFlip): string | null {
  if (flip.state !== "has_blockers" || !flip.target) return null;
  const count = flip.minimum_evidence?.item_ids.length ?? flip.items.filter((item) => item.decision_blocker).length;
  return `${count} ${count === 1 ? "blocker" : "blockers"} to ${DISPOSITION_LABEL[flip.target]}`;
}

/** The one-line reading of a case that has no blockers to list. */
export function stateLine(flip: DecisionFlip): string {
  const open = flip.items.length;
  switch (flip.state) {
    case "no_blockers":
      return open > 0 ? `Nothing open stands in the way · ${open} non-blocking` : "Nothing open stands in the way";
    case "disqualified":
      return "Deprioritise rests on verified evidence. No evidence request changes it";
    case "not_evidence_limited":
      return "More evidence will not change the disposition";
    default:
      return blockerLine(flip) ?? "";
  }
}

/**
 * Which group a requested document falls in. The API sets `group` on each item when the
 * list is built on an analysed version: the documents the screening cannot be completed
 * without, and the rest.
 */
export function requestPriority(item: RequestItem): RequestPriority {
  return item.group === "needed" ? "blocker" : "other";
}

/** The seller sees two groups: what the screening cannot finish without, and the rest. */
export const isNeeded = (priority: RequestPriority): boolean => priority !== "other";

export const PRIORITY_REASON: Record<RequestItem["priority_reason"], string> = {
  decision_blocker: "Settles a decision blocker",
  disqualifier_risk: "Settles a disqualifier risk",
  non_blocking: "Does not change the outcome",
  analyst_retry: "A check to re-run",
};
