/**
 * Maps API shapes (`@/lib/api/client`) onto the shapes the shared DealProof components
 * take (`@/lib/types`). Pure functions, safe on the server and in the browser.
 *
 * Nothing here invents a fact. Where the API leaves something out (a key with no
 * evidence, a reason with no code) the mapped value stays empty and the page says so.
 */
import type {
  AssessmentVersionOut,
  CaseCostOut,
  CaseDetail,
  ClaimOut,
  DiffLineOut,
  EvidenceOut,
  IdentityOut,
  RunOut,
  Schemas,
  SourceRef,
  StepOut,
} from "@/lib/api/client";
import type {
  Assessment,
  AssessmentChange,
  AssessmentDiff,
  AssessmentVersionMeta,
  CaseCost,
  Claim,
  ClaimStatus,
  ClaimStatusCounts,
  Disposition,
  EstimateMeta,
  Evidence,
  FitResult,
  Identity,
  IdentityKey,
  ReliabilityClass,
  Run,
  RunStep,
} from "@/lib/types";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import { CLAIM_STATUSES, DISPOSITIONS } from "@/lib/types";

export type SourceClass = Schemas["SourceClass"];
export type CompanyType = Schemas["CompanyType"];
type ClaimCategory = Schemas["ClaimCategory"];
type IdentityKeyOut = Schemas["IdentityKeyOut"];
type OpportunityOut = Schemas["OpportunityOut"];

/** Any sourced value: FactStr, FactInt, FactFloat, FactStrList. */
export interface AnyFact {
  source: SourceRef;
  evidence_id: string | null;
  as_of: string | null;
  is_estimate: boolean;
  estimate_kind: Schemas["EstimateKind"] | null;
  estimate_basis: string | null;
}

const RELIABILITY: Record<SourceClass, ReliabilityClass> = {
  registry: "registry",
  registry_mirror: "registry_mirror",
  audited_statement: "audited_statement",
  counterparty_confirmation: "counterparty_confirmation",
  company_announcement: "company_announcement",
  news: "news",
  professional_profile_signal: "professional_profile_signal",
  data_provider: "data_provider",
  seller_document: "seller_document",
  seller_statement: "seller_statement",
};

/** The source class in the product's words, at full precision (a mirror is not the registry). */
export const SOURCE_CLASS_LABEL: Record<SourceClass, string> = {
  registry: "Official registry",
  registry_mirror: "Registry mirror",
  audited_statement: "Audited statement",
  counterparty_confirmation: "Counterparty confirmation",
  company_announcement: "Company announcement",
  news: "News report",
  professional_profile_signal: "Professional-profile signal",
  data_provider: "Data provider record",
  seller_document: "Seller document",
  seller_statement: "Seller statement",
};

export const COMPANY_TYPE_LABEL: Record<CompanyType, string> = {
  startup: "Startup",
  established: "Established company",
};

export const CATEGORY_LABEL: Record<ClaimCategory, string> = {
  identity_incorporation: "Identity",
  location: "Location",
  team_size: "Team size",
  leadership_history: "Leadership",
  funding: "Funding",
  dated_event: "Dated events",
  customer_partnership: "Customers",
  financials: "Financials",
  debt_security: "Debt and security",
  litigation: "Litigation",
  compliance: "Certifications",
  intellectual_property: "Trademarks and IP",
  other: "Other",
};

const isUrl = (value: string) => /^https?:\/\//i.test(value);

function toSource(source: SourceRef, asOf: string | null): Evidence["source"] {
  const url = isUrl(source.url_or_endpoint) ? source.url_or_endpoint : null;
  return {
    id: source.source_id,
    provider: source.provider,
    label: source.label,
    url,
    request: url ? null : source.url_or_endpoint,
    retrieved_at: source.retrieved_at,
    as_of: asOf,
    reliability: RELIABILITY[source.source_class],
  };
}

function valueText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function toEvidence(evidence: EvidenceOut): Evidence {
  return {
    id: evidence.evidence_id,
    source: toSource(evidence.source, evidence.as_of),
    quote: evidence.deleted ? null : evidence.quote,
    field_path: evidence.field_path,
    value: valueText(evidence.value),
    attached_to: evidence.attached_to
      ? {
          entity_name: evidence.attached_to.entity_name,
          matched_on: evidence.attached_to.matched_on.map(humanKey).join(" + "),
        }
      : null,
  };
}

/** The source line of a sourced value. */
export function factEvidence(fact: AnyFact): Evidence[] {
  return [{ id: fact.evidence_id ?? undefined, source: toSource(fact.source, fact.as_of) }];
}

/** A bare source reference with the date of the fact it backs. */
export function sourceEvidence(source: SourceRef, asOf: string | null): Evidence[] {
  return [{ source: toSource(source, asOf) }];
}

export function factEstimate(fact: AnyFact): EstimateMeta | null {
  if (!fact.is_estimate) return null;
  return {
    kind: fact.estimate_kind ?? "estimate",
    basis: fact.estimate_basis ?? "basis not recorded",
  };
}

/** "crustdata_company_id" reads as "company id", "hq_city" as "HQ city". */
export function humanKey(key: string): string {
  const known: Record<string, string> = {
    crustdata_company_id: "company id",
    cin: "registration number",
    hq_city: "HQ city",
    founded_year: "founded year",
    profile_url: "profile URL",
    legal_name: "legal name",
  };
  return known[key] ?? key.replaceAll("_", " ");
}

/* ───────────────────────── Claims ───────────────────────── */

function statedIn(claim: ClaimOut): Evidence {
  const stated = claim.stated_in;
  const typed = claim.origin === "typed";
  const label = typed
    ? `Typed by ${stated.typed_by_name ?? "a user"}`
    : `${stated.filename ?? "Seller document"}${stated.page != null ? ` p. ${stated.page}` : ""}`;
  return {
    id: `stated-${claim.id}`,
    source: {
      provider: typed ? "user" : "upload",
      label,
      retrieved_at: stated.typed_at ?? "",
      as_of: stated.typed_at ? stated.typed_at.slice(0, 10) : null,
      reliability: typed ? "seller_statement" : "seller_document",
    },
    quote: stated.quote,
  };
}

const KNOWN_REASONS = ["budget_reached", "source_unavailable", "step_failed", "identity_unresolved"];

/**
 * The API's finding sentence, made fit to sit in a row that already shows the status and
 * what would settle the claim: "Cannot verify. legal_name: no adequate source was found.
 * Would settle it: Certificate of incorporation." reads "Legal name: no adequate source
 * was found."
 */
export function findingText(claim: Pick<ClaimOut, "reason" | "status">): string {
  const text = claim.reason
    .replace(new RegExp(`^${CLAIM_STATUS_LABEL[claim.status]}\\.\\s+`), "")
    .replace(/\s*Would settle it:.*$/, "")
    // Component keys are field names: "hq_city: " reads "Hq city: ".
    .replace(/(^|\.\s+)([a-z][a-z_]*):\s/g, (_, lead: string, key: string) => {
      const words = key.replace(/_/g, " ");
      return `${lead}${words.charAt(0).toUpperCase()}${words.slice(1)}: `;
    })
    .trim();
  return text || claim.reason;
}

export function toClaim(claim: ClaimOut): Claim {
  const evidence = claim.evidence.map(toEvidence);
  const reason = claim.not_checked_reason;
  const finding = findingText(claim);
  return {
    id: claim.id,
    number: claim.number,
    text: claim.original_text,
    category: CATEGORY_LABEL[claim.category] ?? claim.category,
    stated_in: statedIn(claim),
    status: claim.status,
    not_checked_reason: reason && KNOWN_REASONS.includes(reason) ? reason : null,
    // The API states one finding per claim, resting on all of its evidence.
    record: evidence.length > 0 ? [{ text: finding, evidence }] : [],
    // With no evidence attached, the finding still says why: it is the row's note.
    note: evidence.length === 0 && claim.status !== "not_checked" ? finding : undefined,
    what_would_settle: claim.settle_with,
    changed_in_version: claim.changed_in_version,
  };
}

export function statusCounts(claims: { status: ClaimStatus }[]): ClaimStatusCounts {
  const counts = Object.fromEntries(CLAIM_STATUSES.map((s) => [s, 0])) as ClaimStatusCounts;
  for (const claim of claims) counts[claim.status] += 1;
  return counts;
}

/**
 * The ledger in one line: "3 checked · 0 supported · 3 need evidence". A claim that was
 * checked and could not be settled is never counted as resolved, and a check that did
 * not run is counted apart.
 */
export function claimTally(counts: ClaimStatusCounts): string {
  const total = CLAIM_STATUSES.reduce((sum, status) => sum + counts[status], 0);
  const open = counts.partially_corroborated + counts.conflicting_evidence + counts.cannot_verify;
  return [
    `${total - counts.not_checked} checked`,
    `${counts.supported} supported`,
    counts.contradicted > 0 ? `${counts.contradicted} contradicted` : null,
    open > 0 ? `${open} need evidence` : null,
    counts.not_checked > 0 ? `${counts.not_checked} not checked` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/* ───────────────────────── Identity ───────────────────────── */

function toKey(key: IdentityKeyOut): IdentityKey {
  return { key: key.key, label: key.label, value: key.value, evidence: key.evidence.map(toEvidence) };
}

export function toIdentity(identity: IdentityOut): Identity {
  if (identity.state === "confirmed") {
    return {
      state: "confirmed",
      entity_name: identity.entity_name ?? "",
      keys: identity.keys.map(toKey),
    };
  }
  return {
    state: "unresolved",
    candidates: identity.candidates.map((candidate) => ({
      id: String(candidate.crustdata_company_id),
      name: candidate.name,
      matching: candidate.matching.map(toKey),
      differing: candidate.differing.map(toKey),
    })),
  };
}

/* ───────────────────────── Fit and assessment ───────────────────────── */

const lowerFirst = (c: string) => c.toLowerCase();

const VERDICT = { pass: "met", fail: "not_met", unknown: "unknown" } as const;

export function toFit(
  fit: Pick<OpportunityOut, "fit" | "assessable_pct" | "criterion_results">,
): FitResult {
  return {
    fit: fit.fit,
    assessable_share: fit.assessable_pct / 100,
    criteria: fit.criterion_results.map((result) => ({
      id: result.criterion_id,
      label: result.label,
      kind: result.kind,
      weight: result.weight,
      verdict: VERDICT[result.state],
      evidence: result.evidence.map(toEvidence),
    })),
  };
}

/** The ledger numbers of the given claim ids, ascending. */
export function claimNumbers(ids: string[], claims: ClaimOut[]): number[] {
  return ids
    .map((id) => claims.find((claim) => claim.id === id)?.number)
    .filter((number): number is number => number !== undefined)
    .sort((a, b) => a - b);
}

export function toAssessment(version: AssessmentVersionOut, claims: ClaimOut[]): Assessment {
  const j = version.judgments;
  const restsOn = [
    ...new Set(claimNumbers(j.screening_disposition.reasons.flatMap((reason) => reason.claim_ids), claims)),
  ];

  return {
    version: version.version,
    policy_version: version.policy_version,
    created_at: version.created_at,
    fit: toFit(j.opportunity_fit),
    sufficiency: {
      settled: j.evidence_sufficiency.settled.length,
      required: j.evidence_sufficiency.required_categories.length,
      // The required checks as this version recorded them, not the claims' current
      // statuses, so an older version keeps the numbers it was assessed on.
      counts: statusCounts(
        [...j.evidence_sufficiency.settled, ...j.evidence_sufficiency.gaps].flatMap((item) =>
          item.status ? [{ status: item.status }] : [],
        ),
      ),
      gaps: j.evidence_sufficiency.gaps.map((gap) => CATEGORY_LABEL[gap.category].toLowerCase()),
    },
    business: j.business_assessment.signals.map((signal, index) => ({
      id: `${signal.label}-${index}`,
      text: `${signal.label}: ${signal.fact.value}`,
      estimate: factEstimate(signal.fact),
      evidence: factEvidence(signal.fact),
    })),
    financial: j.financial_assessment.assessed
      ? {
          state: "assessed",
          figures: j.financial_assessment.figures.map((figure) => ({
            label: figure.label,
            value: figure.fact.value,
            assumption: figure.assumption,
            evidence: factEvidence(figure.fact),
          })),
        }
      : {
          state: "not_assessed",
          // Both follow "Not assessed · " and "Would need: " mid-sentence.
          reason: (j.financial_assessment.reason ?? "No reliable financial inputs").replace(/^./, lowerFirst),
          would_need: j.financial_assessment.would_need.length
            ? j.financial_assessment.would_need.map((item) => item.replace(/^./, lowerFirst))
            : ["audited financial statements"],
        },
    disposition: {
      disposition: j.screening_disposition.disposition,
      reasons: j.screening_disposition.reasons.map((reason) => ({ text: reason.text })),
      rests_on_claims: restsOn,
      policy_version: version.policy_version,
    },
  };
}

const JUDGMENT_LABEL: Record<string, string> = {
  opportunity_fit: "Opportunity fit",
  evidence_sufficiency: "Evidence sufficiency",
  business_assessment: "Business assessment",
  financial_assessment: "Financial assessment",
  screening_disposition: "Screening disposition",
};

const isClaimStatus = (value: string | null): value is ClaimStatus =>
  value !== null && (CLAIM_STATUSES as readonly string[]).includes(value);
const isDisposition = (value: string | null): value is Disposition =>
  value !== null && (DISPOSITIONS as readonly string[]).includes(value);

function toChange(line: DiffLineOut, claims: ClaimOut[]): AssessmentChange {
  const evidence = line.evidence.map(toEvidence);

  if (line.kind === "claim" && isClaimStatus(line.before) && isClaimStatus(line.after)) {
    const claim = claims.find((item) => item.id === line.subject_id);
    return {
      kind: "claim_status",
      claim_number: claim?.number ?? 0,
      claim_text: line.subject,
      before: line.before,
      after: line.after,
      reason: line.because,
      evidence,
    };
  }
  if (line.kind === "disposition" && isDisposition(line.before) && isDisposition(line.after)) {
    return { kind: "disposition", before: line.before, after: line.after, reason: line.because, evidence };
  }

  // A judgment that moved, or a claim or disposition with no earlier value to compare.
  const words = (value: string | null): string => {
    if (value === null) return "not in the earlier version";
    if (isClaimStatus(value)) return CLAIM_STATUS_LABEL[value];
    if (isDisposition(value)) return DISPOSITION_LABEL[value];
    return line.subject === "evidence_sufficiency" && /^\d+$/.test(value)
      ? `${value}% of required checks settled`
      : value;
  };
  return {
    kind: "value",
    label:
      line.kind === "claim" ? `Claim: “${line.subject}”` : (JUDGMENT_LABEL[line.subject] ?? line.subject),
    before: words(line.before),
    after: words(line.after),
    reason: line.because,
    evidence,
  };
}

/**
 * The "what changed" list of a version, in the shape `VersionDiff` and the change timeline
 * draw. Null for version 1. A line with no earlier value to compare is kept as a value
 * change, in words.
 */
export function toDiff(version: AssessmentVersionOut, claims: ClaimOut[]): AssessmentDiff | null {
  const lines = version.diff_from_previous;
  if (!lines || version.version < 2) return null;
  const changed = new Set(lines.filter((l) => l.kind === "claim").map((l) => l.subject_id));
  return {
    from_version: version.version - 1,
    to_version: version.version,
    changes: lines.map((line) => toChange(line, claims)),
    unchanged_claims: claims.filter((c) => !changed.has(c.id)).length,
  };
}

/** `initial screening`, or `after "Lease agreement.pdf" from seller`. */
export function triggerLabel(trigger: string): string {
  if (/^initial\b/i.test(trigger)) return "initial screening";
  const fromSeller = /^seller documents?\s+(.+)$/i.exec(trigger);
  if (fromSeller) return `after "${fromSeller[1]}" from seller`;
  return trigger;
}

export function toVersionMeta(version: AssessmentVersionOut): AssessmentVersionMeta {
  return {
    version: version.version,
    created_at: version.created_at,
    trigger: triggerLabel(version.trigger),
  };
}


/* ───────────────────────── Runs and cost ───────────────────────── */

function toStep(step: StepOut): RunStep {
  return {
    id: step.id,
    label: step.label,
    status: step.state,
    detail: step.detail,
    result: step.result,
    credits_used: step.cost.crustdata_credits || null,
    model_usd: step.cost.llm_usd || null,
    from_cache: step.from_cache,
    error: step.error,
  };
}

export const isRunActive = (run: Pick<RunOut, "state"> | null | undefined): boolean =>
  run?.state === "pending" || run?.state === "running";

/** `now` is a millisecond timestamp, used for the elapsed time of a run still going. */
export function toRun(run: RunOut, now: number): Run {
  const start = new Date(run.created_at).getTime();
  const end = run.finished_at ? new Date(run.finished_at).getTime() : now;
  return {
    id: run.id,
    kind: run.kind,
    subject: run.subject,
    status: run.state === "done" ? "finished" : run.state === "failed" ? "failed" : "running",
    steps: [...run.steps].sort((a, b) => a.position - b.position).map(toStep),
    elapsed_seconds: Number.isFinite(start) ? Math.max(0, (end - start) / 1000) : 0,
    credits_used: run.cost.crustdata_credits,
    credit_budget: run.budget_credits,
    resumed_at: run.resumed_at,
    checks_not_run: run.checks_not_run,
  };
}

export function toCaseCost(cost: CaseCostOut): CaseCost {
  return {
    credits_used: cost.crustdata_credits,
    credit_budget: cost.credit_budget,
    model_usd: cost.llm_usd,
    checks_not_run: cost.checks_not_run,
    lines: cost.by_step.map((line) => ({
      id: `${line.run_id}-${line.step_key}`,
      run_label: line.run_kind,
      step_label: line.step_label,
      credits: line.cost.crustdata_credits || null,
      model_usd: line.cost.llm_usd || null,
      from_cache: line.cached,
      at: line.at,
    })),
  };
}

/* ───────────────────────── Events ───────────────────────── */

export type { EventNature } from "@/components/insight/event-timeline";
import type { EventNature } from "@/components/insight/event-timeline";

/**
 * How an event is known. An announcement shows that the company said something, a news
 * report that an outlet reported it; only a record or a document confirms it happened.
 */
export function eventNature(event: CaseDetail["events"][number]): EventNature {
  switch (event.evidence.source.source_class) {
    case "company_announcement":
    case "seller_statement":
      return "Announced";
    case "news":
      return "Reported";
    default:
      return "Recorded";
  }
}

export { EVENT_NATURE_MEANING } from "@/components/insight/event-timeline";

/** True when the case can attach records: the legal entity is confirmed. */
export const identityResolved = (detail: CaseDetail): boolean =>
  detail.identity.state === "confirmed";

/* ───────────────────────── Sources ───────────────────────── */

/**
 * What each source was used for, found by walking the case for every fact that cites it.
 * Keyed by source id; each value is a short list such as ["Claim 1", "Fit criteria"].
 */
export function usesBySource(detail: CaseDetail): Map<string, string[]> {
  const uses = new Map<string, Set<string>>();

  const walk = (node: unknown, use: string) => {
    if (Array.isArray(node)) {
      for (const item of node) walk(item, use);
      return;
    }
    if (node === null || typeof node !== "object") return;
    const record = node as Record<string, unknown>;
    const source = record.source as { source_id?: unknown } | undefined;
    if (source && typeof source.source_id === "string") {
      const set = uses.get(source.source_id) ?? new Set<string>();
      set.add(use);
      uses.set(source.source_id, set);
    }
    for (const value of Object.values(record)) walk(value, use);
  };

  walk(detail.identity, "Identity");
  walk(detail.profile, "Company profile");
  walk(detail.opportunity, "Fit criteria");
  for (const claim of detail.claims) walk(claim, `Claim ${claim.number}`);
  walk(detail.events, "Dated events");
  walk(detail.comparables, "Comparables");
  if (detail.assessment) {
    const { judgments } = detail.assessment;
    walk(judgments.opportunity_fit, "Fit criteria");
    walk(judgments.business_assessment, "Operating signals");
    walk(judgments.financial_assessment, "Financial assessment");
  }

  // A seller file is where claims were stated, even when no fact was taken from it.
  for (const source of detail.sources) {
    const stated = detail.claims.filter(
      (claim) =>
        claim.stated_in.filename && source.url_or_endpoint === `upload:${claim.stated_in.filename}`,
    ).length;
    if (stated > 0) {
      const set = uses.get(source.source_id) ?? new Set<string>();
      uses.set(source.source_id, new Set([`Where ${stated} of the seller's claims were stated`, ...set]));
    }
  }

  return new Map([...uses].map(([id, set]) => [id, [...set]]));
}
