/**
 * Turns API responses (lib/api/schema.ts) into the shapes the shared DealProof components
 * draw (lib/types.ts). Nothing is invented here: a field the API did not send stays empty.
 */
import type {
  AssessmentVersionOut,
  CaseDetail,
  ClaimOut,
  DiffLineOut,
  EvidenceOut,
  FactStr,
  MessageOut,
  RequestListOut,
  Schemas,
  SourceRef,
} from "@/lib/api/client";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import {
  CLAIM_STATUSES,
  DISPOSITIONS,
  type Assessment,
  type AssessmentChange,
  type AssessmentDiff,
  type AssessmentVersionMeta,
  type ClaimStatus,
  type ClaimStatusCounts,
  type Disposition,
  type Evidence,
  type ReliabilityClass,
  type SellerRequest,
  type Source,
} from "@/lib/types";

export type SourceClass = Schemas["SourceClass"];
export type ClaimCategory = Schemas["ClaimCategory"];
export type CompanyType = Schemas["CompanyType"];

/* ───────────────────────── Wording ───────────────────────── */

/** The API's source classes, in the product's words. */
export const SOURCE_CLASS_LABEL: Record<SourceClass, string> = {
  registry_official: "Official registry",
  registry_mirror: "Registry mirror",
  audited_statement: "Audited statement",
  counterparty_confirmation: "Counterparty confirmation",
  company_announcement: "Company announcement",
  funding_database: "Funding database",
  professional_profile: "Professional profile",
  headcount_estimate: "Headcount estimate",
  data_provider_profile: "Data provider profile",
  news: "News report",
  seller_document: "Seller document",
  seller_statement: "Seller statement",
  user_typed: "Typed by a user",
};

/**
 * The shared source chip knows eight reliability classes; the API has thirteen. Each API
 * class is drawn with the glyph of its nearest family. The exact class is always named in
 * words on the Sources tab.
 */
const CLASS_TO_RELIABILITY: Record<SourceClass, ReliabilityClass> = {
  registry_official: "registry",
  registry_mirror: "registry",
  audited_statement: "audited_statement",
  counterparty_confirmation: "counterparty_confirmation",
  company_announcement: "company_announcement",
  funding_database: "news",
  professional_profile: "professional_profile_signal",
  headcount_estimate: "professional_profile_signal",
  data_provider_profile: "professional_profile_signal",
  news: "news",
  seller_document: "seller_document",
  seller_statement: "seller_statement",
  user_typed: "seller_statement",
};

export function reliabilityOf(sourceClass: SourceClass): ReliabilityClass {
  return CLASS_TO_RELIABILITY[sourceClass];
}

export const CATEGORY_LABEL: Record<ClaimCategory, string> = {
  identity_incorporation: "Identity and incorporation",
  location: "Location",
  team_size: "Team size",
  leadership_history: "Leadership history",
  funding: "Funding",
  dated_event: "Dated events",
  customer_partnership: "Customers and partnerships",
  financials: "Financials",
  debt_security: "Debt and security",
  litigation: "Litigation",
  other: "Other",
};

export const COMPANY_TYPE_LABEL: Record<CompanyType, string> = {
  startup: "Startup",
  established: "Established company",
};

const JUDGMENT_LABEL: Record<string, string> = {
  opportunity_fit: "Opportunity fit",
  evidence_sufficiency: "Evidence sufficiency",
  business_assessment: "Business assessment",
  financial_assessment: "Financial assessment",
  screening_disposition: "Screening disposition",
};

/** `initial screening`, or `after "Lease agreement.pdf" from seller`. */
export function triggerLabel(trigger: string): string {
  if (/^initial\b/i.test(trigger)) return "initial screening";
  const fromSeller = /^seller documents?\s+(.+)$/i.exec(trigger);
  if (fromSeller) return `after "${fromSeller[1]}" from seller`;
  return trigger;
}

/* ───────────────────────── Evidence ───────────────────────── */

const isUrl = (value: string) => /^https?:\/\//i.test(value);

export function toSource(source: SourceRef, asOf: string | null): Source {
  const web = isUrl(source.url_or_endpoint);
  return {
    id: source.source_id,
    provider: source.provider,
    label: source.label,
    url: web ? source.url_or_endpoint : null,
    request: web ? null : source.url_or_endpoint,
    retrieved_at: source.retrieved_at,
    as_of: asOf,
    reliability: reliabilityOf(source.source_class),
  };
}

export function toEvidence(evidence: EvidenceOut): Evidence {
  return {
    id: evidence.evidence_id,
    source: toSource(evidence.source, evidence.as_of),
    quote: evidence.quote,
    field_path: evidence.field_path,
    value: evidence.value == null ? null : String(evidence.value),
    attached_to: evidence.attached_to
      ? {
          entity_name: evidence.attached_to.entity_name,
          matched_on: evidence.attached_to.matched_on.join(" + ").replaceAll("_", " "),
        }
      : null,
  };
}

/** A sourced value from the API, as the evidence behind it. */
export function factEvidence(fact: FactStr): Evidence {
  return {
    id: fact.evidence_id ?? undefined,
    source: toSource(fact.source, fact.as_of),
    value: fact.value,
  };
}

/* ───────────────────────── Assessment ───────────────────────── */

const isClaimStatus = (value: string | null): value is ClaimStatus =>
  value !== null && (CLAIM_STATUSES as readonly string[]).includes(value);
const isDisposition = (value: string | null): value is Disposition =>
  value !== null && (DISPOSITIONS as readonly string[]).includes(value);

function claimNumbers(ids: string[], claims: ClaimOut[]): number[] {
  return ids
    .map((id) => claims.find((claim) => claim.id === id)?.number)
    .filter((number): number is number => number !== undefined)
    .sort((a, b) => a - b);
}

export function toAssessment(version: AssessmentVersionOut, claims: ClaimOut[]): Assessment {
  const { judgments } = version;
  const fit = judgments.opportunity_fit;
  const sufficiency = judgments.evidence_sufficiency;
  const financial = judgments.financial_assessment;
  const disposition = judgments.screening_disposition;

  const counts = Object.fromEntries(CLAIM_STATUSES.map((s) => [s, 0])) as ClaimStatusCounts;
  for (const item of [...sufficiency.settled, ...sufficiency.gaps]) {
    if (item.status) counts[item.status] += 1;
  }

  const restsOn = claimNumbers(
    disposition.reasons.flatMap((reason) => reason.claim_ids),
    claims,
  );

  return {
    version: version.version,
    policy_version: version.policy_version,
    created_at: version.created_at,
    fit: {
      fit: fit.state === "scored" ? fit.fit : null,
      assessable_share: fit.assessable_pct / 100,
      criteria: fit.criterion_results.map((result) => ({
        id: result.criterion_id,
        label: result.label,
        kind: result.kind,
        weight: result.weight,
        verdict: result.state === "pass" ? "met" : result.state === "fail" ? "not_met" : "unknown",
        evidence: result.evidence.map(toEvidence),
      })),
    },
    sufficiency: {
      settled: sufficiency.settled.length,
      required: sufficiency.required_categories.length,
      counts,
      gaps: sufficiency.gaps.map((gap) => CATEGORY_LABEL[gap.category].toLowerCase()),
    },
    business: judgments.business_assessment.signals.map((signal) => ({
      id: signal.label,
      text: `${signal.label}: ${signal.fact.value}`,
      estimate: signal.fact.is_estimate
        ? {
            kind: signal.fact.estimate_kind ?? "signal",
            basis: signal.fact.estimate_basis ?? "basis not recorded",
          }
        : null,
      evidence: [factEvidence(signal.fact)],
    })),
    financial: financial.assessed
      ? {
          state: "assessed",
          figures: financial.figures.map((figure) => ({
            label: figure.label,
            value: figure.fact.value,
            assumption: figure.assumption,
            evidence: [factEvidence(figure.fact)],
          })),
        }
      : {
          state: "not_assessed",
          reason: (financial.reason ?? "No reliable financial inputs").replace(/^./, (c) =>
            c.toLowerCase(),
          ),
          would_need: financial.would_need.length
            ? financial.would_need.map((item) => item.replace(/^./, (c) => c.toLowerCase()))
            : ["audited financial statements"],
        },
    disposition: {
      disposition: disposition.disposition,
      reasons: disposition.reasons.map((reason) => ({ text: reason.text })),
      rests_on_claims: restsOn.length ? restsOn : undefined,
      policy_version: version.policy_version,
    },
  };
}

export function toVersionMeta(version: AssessmentVersionOut): AssessmentVersionMeta {
  return {
    version: version.version,
    created_at: version.created_at,
    trigger: triggerLabel(version.trigger),
  };
}

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

/** The diff a version carries against the one before it. Null for the first version. */
export function toDiff(version: AssessmentVersionOut, claims: ClaimOut[]): AssessmentDiff | null {
  if (!version.diff_from_previous) return null;
  const changedClaims = new Set(
    version.diff_from_previous.filter((l) => l.kind === "claim").map((l) => l.subject_id),
  );
  return {
    from_version: version.version - 1,
    to_version: version.version,
    changes: version.diff_from_previous.map((line) => toChange(line, claims)),
    unchanged_claims: Math.max(0, claims.length - changedClaims.size),
  };
}

/* ───────────────────────── Request ───────────────────────── */

/** The message in the shape the shared receipt draws. Only settled outcomes use it. */
export function toSellerRequest(
  message: MessageOut,
  list: RequestListOut,
  claims: ClaimOut[],
): SellerRequest {
  const status = message.send?.status ?? message.status;
  return {
    id: message.id,
    status:
      status === "sent" || status === "suppressed_test_mode" || status === "failed"
        ? status
        : status === "draft"
          ? "draft"
          : "approved",
    documents: list.items.map((item) => ({
      id: item.id,
      name: item.document,
      claim_number: claimNumbers(item.claim_ids, claims)[0] ?? 0,
    })),
    recipient: message.current_revision.recipient || null,
    subject: message.current_revision.subject,
    body: message.current_revision.body,
    approver: message.approval ? { name: message.approval.approver_display_name } : null,
    approved_at: message.approval?.approved_at ?? null,
    sent_at: message.send?.completed_at ?? null,
    failure_reason: message.send?.error ?? null,
  };
}

export { claimNumbers };

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

  return new Map([...uses].map(([id, set]) => [id, [...set]]));
}
