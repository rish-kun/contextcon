/**
 * Maps API shapes (`@/lib/api/client`) onto the shapes the shared DealProof components
 * take (`@/lib/types`), for the Discover screens. Nothing here invents a value: a field
 * the API left empty stays empty.
 */
import type {
  EvidenceOut,
  RunOut,
  RunStreamEvent,
  Schemas,
  ShortlistItemOut,
  SourceRef,
  StepOut,
} from "@/lib/api/client";
import type {
  EstimateMeta,
  Evidence,
  FitResult,
  ReliabilityClass,
  Run,
  RunStep,
  Source,
} from "@/lib/types";

type SourceClass = Schemas["SourceClass"];

/**
 * The API's source classes are the domain's own. All but one are a reliability class the
 * shared chip already words (`lib/labels.ts`); a registry mirror takes the registry glyph
 * and says in its own words that it is a mirror.
 */
const SOURCE_CLASS: Record<
  SourceClass,
  { reliability: ReliabilityClass; label?: string; note?: string }
> = {
  registry: { reliability: "registry" },
  registry_mirror: {
    reliability: "registry",
    label: "Registry mirror",
    note: "A secondary mirror of official filings. Reflects what the mirror held on the stated date; confirm against primary filings in formal diligence",
  },
  audited_statement: { reliability: "audited_statement" },
  counterparty_confirmation: { reliability: "counterparty_confirmation" },
  company_announcement: { reliability: "company_announcement" },
  news: { reliability: "news" },
  professional_profile_signal: { reliability: "professional_profile_signal" },
  data_provider: { reliability: "data_provider" },
  seller_document: { reliability: "seller_document" },
  seller_statement: { reliability: "seller_statement" },
};

export function toSource(ref: SourceRef, asOf: string | null): Source {
  // The cast admits a class added to the API after this screen was built.
  const known = SOURCE_CLASS[ref.source_class] as (typeof SOURCE_CLASS)[SourceClass] | undefined;
  const isUrl = /^https?:\/\//.test(ref.url_or_endpoint);
  return {
    id: ref.source_id,
    provider: ref.provider,
    label: ref.label,
    url: isUrl ? ref.url_or_endpoint : null,
    request: isUrl ? null : ref.url_or_endpoint,
    retrieved_at: ref.retrieved_at,
    as_of: asOf,
    reliability: known?.reliability ?? "data_provider",
    class_label: known ? (known.label ?? null) : ref.source_class,
    class_note: known ? (known.note ?? null) : "This source class is new to this screen",
  };
}

function valueText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function toEvidence(evidence: EvidenceOut): Evidence {
  return {
    id: evidence.evidence_id,
    source: toSource(evidence.source, evidence.as_of),
    quote: evidence.quote,
    field_path: evidence.field_path,
    value: valueText(evidence.value),
    attached_to: evidence.attached_to
      ? {
          entity_name: evidence.attached_to.entity_name,
          matched_on: evidence.attached_to.matched_on.join(" + "),
        }
      : null,
  };
}

/** Any sourced value on a shortlist card: the API's Fact* shapes share these fields. */
export interface SourcedFact {
  source: SourceRef;
  evidence_id: string | null;
  as_of: string | null;
  is_estimate: boolean;
  estimate_kind: Schemas["EstimateKind"] | null;
  estimate_basis: string | null;
}

export function factEvidence(
  fact: Pick<SourcedFact, "source" | "evidence_id" | "as_of">,
): Evidence[] {
  return [{ id: fact.evidence_id ?? undefined, source: toSource(fact.source, fact.as_of) }];
}

export function factEstimate(fact: SourcedFact): EstimateMeta | null {
  if (!fact.is_estimate) return null;
  return {
    kind: fact.estimate_kind ?? "estimate",
    basis: fact.estimate_basis ?? "basis not recorded",
  };
}

const VERDICT = { pass: "met", fail: "not_met", unknown: "unknown" } as const;

export function toFit(item: ShortlistItemOut): FitResult {
  return {
    fit: item.fit,
    assessable_share: item.assessable_pct / 100,
    criteria: item.criterion_results.map((result) => ({
      id: result.criterion_id,
      label: result.label,
      kind: result.kind,
      weight: result.weight,
      verdict: VERDICT[result.state],
      evidence: result.evidence.map(toEvidence),
    })),
  };
}

/**
 * Every piece of evidence a card can point at, by id: criterion evidence, plus the card's
 * own sourced facts. `reasons[].evidence_ids` resolve against this.
 */
export function evidenceIndex(item: ShortlistItemOut): Map<string, Evidence> {
  const index = new Map<string, Evidence>();
  for (const result of item.criterion_results) {
    for (const evidence of result.evidence) index.set(evidence.evidence_id, toEvidence(evidence));
  }
  const { card } = item;
  const facts = [
    card.business,
    card.location,
    card.headcount,
    card.headcount_growth_yoy_pct,
    card.total_funding_usd,
    card.hiring?.openings,
    card.hiring?.recent_titles,
  ];
  for (const fact of facts) {
    if (fact?.evidence_id && !index.has(fact.evidence_id)) {
      index.set(fact.evidence_id, factEvidence(fact)[0]);
    }
  }
  for (const round of card.funding_rounds) {
    if (round.evidence_id && !index.has(round.evidence_id)) {
      index.set(round.evidence_id, {
        id: round.evidence_id,
        source: toSource(round.source, round.date),
      });
    }
  }
  return index;
}

/* ───────────────────────── Runs ───────────────────────── */

export const isTerminal = (run: RunOut) => run.state === "done" || run.state === "failed";

/** A run shown as live before its first event arrives. */
export function asLiveSeed(run: RunOut): RunOut {
  return isTerminal(run) ? { ...run, state: "running", steps: [] } : run;
}

/** Folds one stream event into the run. A `run` event without steps keeps the ones seen. */
export function mergeRunEvent(run: RunOut, event: RunStreamEvent): RunOut {
  if (event.event === "activity" || event.event === "live") return run;
  if (event.event === "run") {
    return {
      ...event.data,
      steps: event.data.steps.length > 0 ? event.data.steps : run.steps,
    };
  }
  const steps = run.steps.filter((step) => step.id !== event.data.id);
  steps.push(event.data);
  steps.sort((a, b) => a.position - b.position);
  return { ...run, steps };
}

function toStep(step: StepOut): RunStep {
  const modelOnly = step.cost.llm_usd > 0 && step.cost.crustdata_credits === 0;
  return {
    id: step.id,
    label: step.label,
    status: step.state,
    detail: step.detail,
    result: step.result,
    credits_used: modelOnly ? null : step.cost.crustdata_credits,
    model_usd: modelOnly ? step.cost.llm_usd : null,
    from_cache: step.from_cache,
    error: step.error,
  };
}

/** Seconds a finished run took, from its own timestamps. Null when they are missing. */
export function runDuration(run: RunOut): number | null {
  if (!run.finished_at) return null;
  const seconds = (Date.parse(run.finished_at) - Date.parse(run.created_at)) / 1000;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function toRun(run: RunOut, elapsedSeconds: number): Run {
  return {
    id: run.id,
    kind: run.kind,
    subject: run.subject,
    status: run.state === "done" ? "finished" : run.state === "failed" ? "failed" : "running",
    steps: run.steps.map(toStep),
    elapsed_seconds: elapsedSeconds,
    credits_used: run.cost.crustdata_credits,
    credit_budget: run.budget_credits,
    resumed_at: run.resumed_at,
    checks_not_run: run.checks_not_run,
  };
}

/* ───────────────────────── Wording ───────────────────────── */

/** Model usage. An amount under a cent is said to be under a cent, not shown as zero. */
export function formatModelUsd(value: number): string {
  if (value > 0 && value < 0.005) return "under $0.01";
  return `$${value.toFixed(2)}`;
}

/** `$6.0M`, `$450K`, `$1.2B`. One format for every funding amount. */
export function formatAmountUsd(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `$${Math.round(value / 1e3)}K`;
  return `$${Math.round(value)}`;
}

/** `series_a` → `Series A`. */
export function roundLabel(roundType: string | null): string {
  if (!roundType) return "Round type not recorded";
  const words = roundType.replace(/[_-]+/g, " ").trim().split(" ");
  return words
    .map((word, index) =>
      index === 0 || word.length === 1 ? word.charAt(0).toUpperCase() + word.slice(1) : word,
    )
    .join(" ");
}

/** A readable message from whatever a failed call threw. */
export function errorText(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "The request did not complete";
}

export function isNotFound(error: unknown): boolean {
  return Boolean(
    error && typeof error === "object" && (error as { status?: number }).status === 404,
  );
}
