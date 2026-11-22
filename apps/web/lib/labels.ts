/**
 * The product's own terms, used exactly and never varied.
 * Components read wording from here so a status is spelled one way everywhere.
 */
import type {
  ClaimStatus,
  CriterionVerdict,
  Disposition,
  EstimateKind,
  NotCheckedReason,
  ReliabilityClass,
  RequestStatus,
  RunKind,
  StepStatus,
} from "./types";

export const CLAIM_STATUS_LABEL: Record<ClaimStatus, string> = {
  supported: "Supported",
  partially_corroborated: "Partially corroborated",
  conflicting_evidence: "Conflicting evidence",
  contradicted: "Contradicted",
  cannot_verify: "Cannot verify",
  not_checked: "Not checked",
};

export const CLAIM_STATUS_MEANING: Record<ClaimStatus, string> = {
  supported: "Adequate evidence directly supports the claim",
  partially_corroborated: "Evidence supports part of the claim, not all of it",
  conflicting_evidence: "Relevant sources disagree with each other",
  contradicted: "Reliable evidence directly conflicts with the precise claim",
  cannot_verify:
    "Available evidence cannot settle the question. A named document would",
  not_checked: "The check was not run",
};

/** The rule behind each status in a few words, for places with room for one short line. */
export const CLAIM_STATUS_RULE: Record<ClaimStatus, string> = {
  supported: "An adequate source agrees",
  partially_corroborated: "Evidence backs part of it",
  conflicting_evidence: "Sources disagree",
  contradicted: "A reliable source conflicts",
  cannot_verify: "No adequate source reached",
  not_checked: "The check was not run",
};

export const NOT_CHECKED_REASON_LABEL: Record<NotCheckedReason, string> = {
  budget_reached: "budget reached",
  source_unavailable: "source unavailable",
  step_failed: "step failed",
  identity_unresolved: "identity unresolved",
};

export const NOT_CHECKED_REASON_DETAIL: Record<NotCheckedReason, string> = {
  budget_reached: "No search was run for this claim",
  source_unavailable: "The source did not respond, so nothing was read",
  step_failed: "The step stopped with an error before it reached this claim",
  identity_unresolved: "Checks wait until the legal entity is confirmed",
};

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  prioritise: "Prioritise",
  investigate_further: "Investigate further",
  deprioritise: "Deprioritise",
  cannot_assess: "Cannot assess",
};

export const DISPOSITION_MEANING: Record<Disposition, string> = {
  prioritise:
    "Strong fit, and the required checks are satisfied within what DealProof covers",
  investigate_further: "Attractive, but important evidence is incomplete",
  deprioritise:
    "A requirement you set has verifiably failed, or the fit is poor on good evidence",
  cannot_assess:
    "Identity or other essential information is too uncertain to judge",
};

export const ESTIMATE_LABEL: Record<EstimateKind, string> = {
  estimate: "Estimate",
  signal: "Signal",
};

export const RELIABILITY_LABEL: Record<ReliabilityClass, string> = {
  registry: "Registry record",
  registry_mirror: "Registry mirror",
  audited_statement: "Audited statement",
  counterparty_confirmation: "Counterparty confirmation",
  company_announcement: "Company announcement",
  professional_profile_signal: "Professional-profile signal",
  news: "News report",
  seller_document: "Seller document",
  seller_statement: "Seller statement",
  data_provider: "Data provider record",
};

/** What each class is strong and weak on, shown in the evidence popover. */
export const RELIABILITY_NOTE: Record<ReliabilityClass, string> = {
  registry:
    "Strong on incorporation, registered office and filings. Says nothing about trading or scale",
  registry_mirror:
    "A third party's copy of registry records. Strong on incorporation and filings as of its last sync. It can lag the official register",
  audited_statement:
    "Strong on past revenue and balances for the period audited. Silent on anything after it",
  counterparty_confirmation:
    "Strong on the relationship it confirms. Covers only that counterparty",
  company_announcement:
    "Shows that the company announced something, not that it happened",
  professional_profile_signal:
    "A signal from self-reported profiles. Not a payroll count, and thin for site staff",
  news: "Shows that something was reported. Accuracy depends on the outlet's own sources",
  seller_document:
    "The seller's own document. Evidence of what the seller states, not independent proof",
  seller_statement:
    "What the seller said. It is the claim under review, not evidence for it",
  data_provider:
    "A compiled record from a data provider. Dated, but second-hand: not the registry or the filing itself",
};

export const VERDICT_LABEL: Record<CriterionVerdict, string> = {
  met: "Met",
  not_met: "Not met",
  unknown: "Unknown · could not assess",
};

export const RUN_KIND_LABEL: Record<RunKind, string> = {
  discover: "Discover",
  investor_discover: "Find investors",
  verify: "Verify",
  evaluate: "Evaluate",
  recheck: "Recheck",
  org_research: "Research",
};

export const STEP_STATUS_LABEL: Record<StepStatus, string> = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  failed: "Failed",
  skipped_budget: "Skipped · budget reached",
};

export const REQUEST_STATUS_LABEL: Record<RequestStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  sent: "Sent once",
  suppressed_test_mode: "Suppressed (test mode) · not sent",
  failed: "Failed · not sent",
};
