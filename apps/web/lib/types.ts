/**
 * Shared data shapes for the DealProof web app.
 *
 * These mirror what the API is expected to return (see
 * docs/superpowers/specs/2026-11-22-dealproof-v1-design.md), so field names are
 * snake_case and enums are the backend's string values. Display wording lives in
 * lib/labels.ts, never here.
 *
 * Dates: `as_of` is the date of the underlying fact and may be a full date
 * (`2026-10-14`), a month (`2026-10`), a year (`2014`) or null when unknown.
 * `retrieved_at`, `created_at` and other `*_at` fields are ISO 8601 timestamps.
 */

/* ───────────────────────── Provenance ───────────────────────── */

/** Reliability class of a source. Decides which questions it is strong on. */
export const RELIABILITY_CLASSES = [
  "registry",
  "registry_mirror",
  "audited_statement",
  "counterparty_confirmation",
  "company_announcement",
  "professional_profile_signal",
  "news",
  "seller_document",
  "seller_statement",
  "data_provider",
] as const;
export type ReliabilityClass = (typeof RELIABILITY_CLASSES)[number];

export interface Source {
  id?: string;
  /** Where it came from: a Crustdata endpoint, a web page, an uploaded document, typed by a user. */
  provider: string;
  /** Short human name shown on the chip: "Registry mirror", "Seller deck p. 7". */
  label: string;
  /** Public URL, when there is one. */
  url?: string | null;
  /** Request parameters, when the source is an API call and not a page. */
  request?: string | null;
  /** When DealProof fetched it. ISO timestamp. */
  retrieved_at: string;
  /** Date of the underlying fact, not the retrieval. Null when unknown. */
  as_of: string | null;
  reliability: ReliabilityClass;
  /** The source's own class in words, when it is finer than `reliability`: "Funding database". */
  class_label?: string | null;
  /** What that class can and cannot settle. Replaces the default note for `reliability`. */
  class_note?: string | null;
}

/** One piece of evidence: a source plus exactly what was taken from it. */
export interface Evidence {
  id?: string;
  source: Source;
  /** The exact words quoted from the source. */
  quote?: string | null;
  /** For structured sources: the field path and the value read from it. */
  field_path?: string | null;
  value?: string | null;
  /** The entity this evidence was attached to, and the identity key that justified it. */
  attached_to?: {
    entity_name: string;
    /** For example "domain + registration number" or "company id + name". */
    matched_on: string;
  } | null;
}

/* ───────────────────────── Claims ───────────────────────── */

/** Fixed display order: Not checked is always last and always set apart. */
export const CLAIM_STATUSES = [
  "supported",
  "partially_corroborated",
  "conflicting_evidence",
  "contradicted",
  "cannot_verify",
  "not_checked",
] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

/** Every status except Not checked counts as settled. */
export type SettledClaimStatus = Exclude<ClaimStatus, "not_checked">;

export const NOT_CHECKED_REASONS = [
  "budget_reached",
  "source_unavailable",
  "step_failed",
  "identity_unresolved",
] as const;
export type NotCheckedReason = (typeof NOT_CHECKED_REASONS)[number];

export type EstimateKind = "estimate" | "signal";

/** Marks a value that is inferred or suggestive, not a recorded fact. */
export interface EstimateMeta {
  kind: EstimateKind;
  /** Plain-words basis: "from professional profiles, not a payroll count". */
  basis: string;
}

/** One statement on the "The record shows" side of the ledger. */
export interface RecordStatement {
  text: string;
  /** Required. A statement without evidence is not rendered. */
  evidence: Evidence[];
  /** Set when the value in `text` is an estimate or a signal. */
  estimate?: EstimateMeta | null;
  /** For Partially corroborated: which half of the claim this statement speaks to. */
  part?: "supported" | "not_supported" | null;
}

export interface Claim {
  id: string;
  /** Position in the ledger, 1-based. */
  number: number;
  /** The claim in the seller's words. */
  text: string;
  /** "Identity", "Team size", "Dated events", "Funding", "Customers". */
  category: string;
  /** Where the claim was made: a document and page, or typed by a named person. */
  stated_in: Evidence;
  status: ClaimStatus;
  /** Required when status is not_checked. */
  not_checked_reason?: NotCheckedReason | null;
  /** What the record shows. Empty when the claim was not checked. */
  record: RecordStatement[];
  /** A sentence of context: why the evidence falls short. */
  note?: string | null;
  /**
   * Names of the sources that were searched or read for this claim. Empty or absent when
   * none is on record; a Cannot verify row then says that no public source was searched.
   */
  searched?: string[] | null;
  /** The document that would settle the claim. Feeds the request list. */
  what_would_settle?: string | null;
  /** Estimated credit cost of running the check, for Not checked claims that can be retried. */
  retry_credits_estimate?: number | null;
  /** The assessment version in which this claim's status last changed, when it is the current one. */
  changed_in_version?: number | null;
}

export type ClaimStatusCounts = Record<ClaimStatus, number>;

/* ───────────────────────── Identity ───────────────────────── */

export interface IdentityKey {
  /** "domain", "legal_name", "registration_number", "registered_city", "founded_year". */
  key: string;
  label: string;
  value: string;
  evidence: Evidence[];
}

export interface IdentityCandidate {
  id: string;
  name: string;
  matching: IdentityKey[];
  differing: IdentityKey[];
}

export type Identity =
  | { state: "confirmed"; entity_name: string; keys: IdentityKey[] }
  | { state: "unresolved"; candidates: IdentityCandidate[] };

/* ───────────────────────── Fit ───────────────────────── */

export type CriterionKind = "must" | "preference";
export type CriterionVerdict = "met" | "not_met" | "unknown";

export interface CriterionResult {
  id: string;
  label: string;
  kind: CriterionKind;
  /** Relative weight. Sets the width of the cell on the strip. */
  weight: number;
  verdict: CriterionVerdict;
  /** Present when the verdict is met or not_met. */
  evidence?: Evidence[];
}

export interface FitResult {
  /** 0 to 100. Null when nothing could be assessed. */
  fit: number | null;
  /** Weighted share of criteria that could be assessed, 0 to 1. */
  assessable_share: number;
  criteria: CriterionResult[];
}

/* ───────────────────────── The five judgments ───────────────────────── */

export const DISPOSITIONS = [
  "prioritise",
  "investigate_further",
  "deprioritise",
  "cannot_assess",
] as const;
export type Disposition = (typeof DISPOSITIONS)[number];

export interface DispositionReason {
  text: string;
  evidence?: Evidence[];
}

export interface DispositionResult {
  disposition: Disposition;
  /** One to three lines. A stamp is never shown without them. */
  reasons: DispositionReason[];
  /** Claim numbers the disposition rests on. */
  rests_on_claims?: number[];
  policy_version: string;
}

export interface EvidenceSufficiency {
  /** Required checks that reached a settled status. Not checked is excluded. */
  settled: number;
  required: number;
  counts: ClaimStatusCounts;
  /** Named gaps: "payroll", "lender statement", "occupancy". */
  gaps: string[];
}

/** One operating indicator. Never a score. */
export interface BusinessSignal {
  id: string;
  text: string;
  /** Null for a dated, recorded event; otherwise how the value is marked. */
  estimate?: EstimateMeta | null;
  evidence: Evidence[];
}

export interface FinancialFigure {
  label: string;
  value: string;
  /** The stated assumption the figure depends on. */
  assumption?: string | null;
  evidence: Evidence[];
}

export type FinancialAssessment =
  | { state: "not_assessed"; reason: string; would_need: string[] }
  | { state: "assessed"; figures: FinancialFigure[] };

/** An immutable assessment version. Five judgments, kept separate, no total. */
export interface Assessment {
  version: number;
  policy_version: string;
  created_at: string;
  fit: FitResult;
  sufficiency: EvidenceSufficiency;
  business: BusinessSignal[];
  financial: FinancialAssessment;
  disposition: DispositionResult;
}

/* ───────────────────────── Version history ───────────────────────── */

export interface AssessmentVersionMeta {
  version: number;
  created_at: string;
  /** What produced it: "initial screening", `after "Lease agreement.pdf" from seller`. */
  trigger: string;
}

/**
 * Why a claim's status is what it is in this version, as a kind the page can group by.
 * `stated` is a cause the API gave in its own words.
 */
export type ChangeCause =
  | { kind: "policy"; from: string; to: string }
  /** New evidence arrived. The sources are the change's own `evidence`. */
  | { kind: "evidence" }
  | { kind: "evidence_removed"; sources: string }
  | { kind: "stated"; text: string };

export type AssessmentChange =
  | {
      kind: "claim_status";
      claim_number: number;
      claim_text: string;
      /** Null when the claim had no status in the earlier version: this is its first. */
      before: ClaimStatus | null;
      after: ClaimStatus;
      /** Why it changed. A change with no stated cause is a bug. */
      reason: string;
      /** The same cause, typed. Absent on changes that only carry `reason`. */
      cause?: ChangeCause;
      evidence: Evidence[];
    }
  | {
      kind: "disposition";
      before: Disposition;
      after: Disposition;
      reason: string;
      evidence?: Evidence[];
    }
  | {
      /** A judgment or derived figure that moved because something above it did. */
      kind: "value";
      label: string;
      /** Null when there was no earlier value to compare. */
      before: string | null;
      after: string;
      reason?: string | null;
      evidence?: Evidence[];
    };

export interface AssessmentDiff {
  from_version: number;
  to_version: number;
  changes: AssessmentChange[];
  unchanged_claims: number;
}

/* ───────────────────────── Runs ───────────────────────── */

export type RunKind =
  | "discover"
  | "investor_discover"
  | "verify"
  | "evaluate"
  | "recheck"
  | "org_research";

export type RunStatus = "running" | "finished" | "failed";

export type StepStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "skipped_budget";

export interface RunStep {
  id: string;
  label: string;
  status: StepStatus;
  /** Live sub-line while running: "claim 7 of 12 · searching dated announcements". */
  detail?: string | null;
  /** One-line result when done: "matched on domain + registration number". */
  result?: string | null;
  /** Crustdata credits spent by this step. Null when the step used none. */
  credits_used?: number | null;
  /** Model usage in US dollars. Null when the step called no model. */
  model_usd?: number | null;
  /** True when a resumed run replayed this step from the request cache. */
  from_cache?: boolean;
  /** The reason, when status is failed. */
  error?: string | null;
}

export interface Run {
  id: string;
  kind: RunKind;
  /** What the run is about: a company, a thesis. */
  subject: string;
  status: RunStatus;
  steps: RunStep[];
  elapsed_seconds: number;
  credits_used: number;
  credit_budget: number;
  /** Set when the run picked up after an interruption. */
  resumed_at?: string | null;
  /** Checks skipped by the end of the run, which become Not checked claims. */
  checks_not_run?: number;
}

/* ───────────────────────── Cost ───────────────────────── */

export interface CostLine {
  id: string;
  run_label: string;
  step_label: string;
  credits: number | null;
  model_usd: number | null;
  from_cache?: boolean;
  at: string;
}

/** Credits and model dollars are two currencies. They are never added together. */
export interface CaseCost {
  credits_used: number;
  credit_budget: number;
  model_usd: number;
  /** Checks skipped because the budget was reached. */
  checks_not_run?: number;
  lines: CostLine[];
}

/* ───────────────────────── Request and approval ───────────────────────── */

export type RequestStatus =
  | "draft"
  | "approved"
  | "sent"
  | "suppressed_test_mode"
  | "failed";

export interface RequestedDocument {
  id: string;
  name: string;
  /** The claim this document would settle. */
  claim_number: number;
}

export interface NamedUser {
  id?: string;
  name: string;
}

export interface SellerRequest {
  id: string;
  status: RequestStatus;
  documents: RequestedDocument[];
  /** Typed by a person. DealProof never suggests an address. */
  recipient: string | null;
  subject: string;
  body: string;
  approver: NamedUser | null;
  approved_at?: string | null;
  sent_at?: string | null;
  /** The provider's reason, when status is failed. */
  failure_reason?: string | null;
}
