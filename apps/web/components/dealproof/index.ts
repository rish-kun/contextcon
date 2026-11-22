/**
 * DealProof domain components. Import from "@/components/dealproof".
 * Some names in the design direction differ from the file names; both are exported.
 */
export * from "./approval-block";
export * from "./blocks";
export * from "./claim-ledger";
export * from "./cost-readout";
export * from "./criteria-strip";
export * from "./disposition-stamp";
export * from "./estimate-label";
export * from "./glyphs";
export * from "./identity-badge";
export * from "./judgment-panel";
export * from "./number-tween";
export * from "./run-progress";
export * from "./source-line";
export * from "./status-mark";
export * from "./version-diff";

// Names used in docs/design/design-direction.md, section 8.
export { ClaimLedgerRow as ClaimRow } from "./claim-ledger";
export { CriteriaStrip as FitReadout } from "./criteria-strip";
export { EstimateLabel as EstimateValue } from "./estimate-label";
export { IdentityBadge as IdentityBand } from "./identity-badge";
export { RunProgress as RunPanel } from "./run-progress";
export { VersionDiff as AssessmentDiffView } from "./version-diff";
