/**
 * The DecisionFlip analysis as the API returns it (docs/design/iterations/F-decisionflip.md
 * §7.1 with the B1 amendments, `DecisionFlipAnalysis` in apps/api/app/domain/types.py).
 * Typed here until the `decision_flip` section is in the generated schema; the shapes are
 * the rules module's own, so the switch is a change of import and nothing else.
 */
import type { ClaimStatus, Disposition } from "@/lib/types";

export type FlipItemKind = "claim" | "check_gap" | "criterion" | "identity" | "financial_inputs";
export type FlipItemClass = "decision_blocker" | "disqualifier_risk" | "non_blocking";
export type FlipState = "has_blockers" | "no_blockers" | "disqualified" | "not_evidence_limited";
export type FlipEffort = "low" | "medium" | "high";
export type FlipAction =
  | "request_documents"
  | "resolve_identity"
  | "rerun_checks"
  | "analyst_follow_up"
  | "review_disqualifier"
  | "none";

/** The disposition the rules give with one or more items forced. Never verified. */
export interface FlipOutcome {
  hypothetical: true;
  disposition: Disposition;
  rule: string;
  reasons: string[];
  changes_disposition: boolean;
}

export interface FlipItem {
  /** "claim:<id>", "check:<category>", "criterion:<id>", "identity" or "financial_inputs". */
  id: string;
  kind: FlipItemKind;
  claim_id?: string | null;
  criterion_id?: string | null;
  check?: string | null;
  /** A claim status, "unknown" for a criterion, "absent", an identity state, "not_assessed". */
  current_state: ClaimStatus | string;
  classification: FlipItemClass;
  decision_blocker: boolean;
  disqualifier_risk: boolean;
  required_in_every_path: boolean;
  flips_alone: boolean;
  locks_target: boolean;
  seller_resolvable: boolean;
  analyst_retry: boolean;
  depends_on: string[];
  settle_with: string[];
  if_supported: FlipOutcome | null;
  if_contradicted: FlipOutcome | null;
  est_effort: FlipEffort;
  /** Criteria and financial items: what to obtain, with both branches stated. */
  conditional_action?: string | null;
  /** Added on read from the claims and criteria rows; absent in the stored document. */
  label?: string | null;
  claim_text?: string | null;
}

export interface FlipDocument {
  document: string;
  item_ids: string[];
  seller_resolvable: boolean;
}

export interface FlipSet {
  hypothetical: true;
  item_ids: string[];
  documents: FlipDocument[];
  outcome: FlipOutcome;
}

export interface FlipNextAction {
  action: FlipAction;
  text: string;
  item_ids: string[];
  documents: string[];
  /** The conditional sentences, both branches, for criteria and financial items in the set. */
  conditions: string[];
}

export interface DecisionFlip {
  hypothetical: true;
  case_id: string;
  assessment_version: number;
  policy_version: string;
  inputs_hash: string;
  flip_version: string;
  analysis_key: string;
  state: FlipState;
  current: Disposition;
  current_rule: string;
  current_reasons: string[];
  target: Disposition | null;
  ceiling: FlipOutcome;
  items: FlipItem[];
  minimal_sets: FlipSet[];
  minimum_evidence: FlipSet | null;
  worst_if_contradicted: FlipOutcome | null;
  next_best_action: FlipNextAction;
  search: "exhaustive" | "greedy";
  greedy: boolean;
  evaluations: number;
  selection_basis: string;
  selection_label: string;
  /** Added on read: the request list built for this version, if it has blocker items. */
  request?: { request_list_id: string; status: string; blocker_items: number } | null;
}

/** How a requested document ranks against the analysis (F §3). */
export type RequestPriority = "blocker" | "blocker_alt" | "risk" | "other";
