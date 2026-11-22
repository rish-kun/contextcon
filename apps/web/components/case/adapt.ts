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
import { CLAIM_STATUSES, DISPOSITIONS } from "@/lib/types";

type SourceClass = Schemas["SourceClass"];
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
  registry_mirror: "registry",
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

export function toClaim(claim: ClaimOut): Claim {
  const evidence = claim.evidence.map(toEvidence);
  const reason = claim.not_checked_reason;
  return {
    id: claim.id,
    number: claim.number,
    text: claim.original_text,
    category: CATEGORY_LABEL[claim.category] ?? claim.category,
    stated_in: statedIn(claim),
    status: claim.status,
    not_checked_reason: reason && KNOWN_REASONS.includes(reason) ? reason : null,
    // The API states one finding per claim, resting on all of its evidence.
    record: evidence.length > 0 ? [{ text: claim.reason, evidence }] : [],
    what_would_settle: claim.settle_with,
    changed_in_version: claim.changed_in_version,
  };
}

export function statusCounts(claims: { status: ClaimStatus }[]): ClaimStatusCounts {
  const counts = Object.fromEntries(CLAIM_STATUSES.map((s) => [s, 0])) as ClaimStatusCounts;
  for (const claim of claims) counts[claim.status] += 1;
  return counts;
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

export function toAssessment(version: AssessmentVersionOut, claims: ClaimOut[]): Assessment {
  const j = version.judgments;
  const numberOf = new Map(claims.map((claim) => [claim.id, claim.number]));
  const restsOn = [
    ...new Set(
      j.screening_disposition.reasons.flatMap((reason) =>
        reason.claim_ids.flatMap((id) => numberOf.get(id) ?? []),
      ),
    ),
  ].sort((a, b) => a - b);

  return {
    version: version.version,
    policy_version: version.policy_version,
    created_at: version.created_at,
    fit: toFit(j.opportunity_fit),
    sufficiency: {
      settled: j.evidence_sufficiency.settled.length,
      required: j.evidence_sufficiency.required_categories.length,
      counts: statusCounts(claims),
      gaps: j.evidence_sufficiency.gaps.map(
        (gap) => gap.settle_with ?? CATEGORY_LABEL[gap.category].toLowerCase(),
      ),
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
          reason: j.financial_assessment.reason ?? "No reliable financial inputs",
          would_need: j.financial_assessment.would_need,
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

const isStatus = (value: string | null): value is ClaimStatus =>
  value !== null && (CLAIM_STATUSES as readonly string[]).includes(value);
const isDisposition = (value: string | null): value is Disposition =>
  value !== null && (DISPOSITIONS as readonly string[]).includes(value);

/** The "what changed" list of a version, in the shape `VersionDiff` draws. Null for version 1. */
export function toDiff(version: AssessmentVersionOut, claims: ClaimOut[]): AssessmentDiff | null {
  const lines = version.diff_from_previous;
  if (!lines || version.version < 2) return null;
  const changes: AssessmentChange[] = [];
  for (const line of lines) {
    const evidence = line.evidence.map(toEvidence);
    if (line.kind === "claim" && isStatus(line.before) && isStatus(line.after)) {
      const claim = claims.find((c) => c.id === line.subject_id);
      changes.push({
        kind: "claim_status",
        claim_number: claim?.number ?? 0,
        claim_text: line.subject,
        before: line.before,
        after: line.after,
        reason: line.because,
        evidence,
      });
    } else if (line.kind === "disposition" && isDisposition(line.before) && isDisposition(line.after)) {
      changes.push({ kind: "disposition", before: line.before, after: line.after, reason: line.because, evidence });
    } else {
      const pct = line.subject === "evidence_sufficiency" ? "%" : "";
      changes.push({
        kind: "value",
        label: JUDGMENT_LABEL[line.subject] ?? line.subject,
        before: line.before === null ? "not set" : `${line.before}${pct}`,
        after: `${line.after}${pct}`,
        reason: line.because,
        evidence,
      });
    }
  }
  const changed = new Set(lines.filter((l) => l.kind === "claim").map((l) => l.subject_id));
  return {
    from_version: version.version - 1,
    to_version: version.version,
    changes,
    unchanged_claims: claims.filter((c) => !changed.has(c.id)).length,
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

export type EventNature = "Announced" | "Reported" | "Recorded";

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

export const EVENT_NATURE_MEANING: Record<EventNature, string> = {
  Announced: "The company said so. Not confirmed to have happened",
  Reported: "An outlet reported it. Not independently confirmed",
  Recorded: "Confirmed occurrence: a record or document shows it",
};

/** True when the case can attach records: the legal entity is confirmed. */
export const identityResolved = (detail: CaseDetail): boolean =>
  detail.identity.state === "confirmed";
