/**
 * Pure functions from case records to the rows each explainer draws. No fetches, no
 * React, no dates read from the clock: the same input always gives the same picture.
 *
 * Nothing is inferred. Where the API does not yet record something an explainer could
 * show (which sources were searched and came back empty, the rule that fired, what
 * caused a derived change), the model leaves it out and the view says so.
 */
import type { CaseCostOut } from "@/lib/api/client";
import { CLAIM_STATUS_MEANING } from "@/lib/labels";
import {
  CLAIM_STATUSES,
  type AssessmentChange,
  type AssessmentDiff,
  type AssessmentVersionMeta,
  type CaseCost,
  type Claim,
  type ClaimStatus,
  type ClaimStatusCounts,
  type Disposition,
  type EstimateMeta,
  type Evidence,
  type NotCheckedReason,
  type ReliabilityClass,
  type RequestStatus,
  type Run,
  type RunKind,
} from "@/lib/types";

/* ───────────────────────── Shared ───────────────────────── */

/**
 * A search that ran and returned nothing. The API does not record these yet, so every
 * derive function takes them as an optional input and draws none when they are absent.
 */
export interface EmptySearch {
  reliability: ReliabilityClass;
  /** The claim the search was run for. */
  claim_id: string;
  /** What was searched, in words: "Registry mirror". */
  label?: string;
}

/** Strongest first. A data provider's compiled record is second-hand, so it sits last. */
export const INDEPENDENT_CLASSES = [
  "registry",
  "registry_mirror",
  "audited_statement",
  "counterparty_confirmation",
  "company_announcement",
  "professional_profile_signal",
  "news",
  "data_provider",
] as const satisfies readonly ReliabilityClass[];

/** The seller's own material: where a claim came from, never independent evidence. */
export const SELLER_CLASSES = [
  "seller_document",
  "seller_statement",
] as const satisfies readonly ReliabilityClass[];

/** Column heads short enough for a ten-column grid. */
export const CLASS_SHORT_LABEL: Record<ReliabilityClass, string> = {
  registry: "Registry",
  registry_mirror: "Registry mirror",
  audited_statement: "Audited statement",
  counterparty_confirmation: "Counterparty",
  company_announcement: "Company announcement",
  professional_profile_signal: "Profile signals",
  news: "News",
  data_provider: "Data provider",
  seller_document: "Seller document",
  seller_statement: "Seller statement",
};

function emptyCounts(): ClaimStatusCounts {
  return Object.fromEntries(CLAIM_STATUSES.map((status) => [status, 0])) as ClaimStatusCounts;
}

const sourceKey = (evidence: Evidence): string =>
  evidence.source.id ?? `${evidence.source.provider}|${evidence.source.label}`;

/* ───────────────────────── Evidence trail ───────────────────────── */

export interface TrailFact {
  key: string;
  /** The as-of date of the fact, at whatever precision the source gave. Null when unknown. */
  as_of: string | null;
  text: string;
  evidence: Evidence;
  part: "supported" | "not_supported" | null;
  estimate: EstimateMeta | null;
}

export interface TrailSource {
  key: string;
  /** Every evidence row taken from this source for this claim. */
  evidence: Evidence[];
  facts: TrailFact[];
}

export interface TrailModel {
  /**
   * found: at least one dated fact. nothing_found: the check ran and attached no
   * evidence. not_checked: no search was run.
   */
  state: "found" | "nothing_found" | "not_checked";
  sources: TrailSource[];
  emptySearches: EmptySearch[];
  /** What DealProof concluded from several pieces of evidence taken together. */
  findings: string[];
  rule: {
    text: string;
    /** `status_definition` is the fallback: the fixed meaning of the status, not this claim's rule. */
    from: "claim" | "status_definition";
  };
  /** The sources disagree with each other, so a marker is drawn between them. */
  disagree: boolean;
}

function excerpt(evidence: Evidence): string | null {
  if (evidence.quote) return `“${evidence.quote}”`;
  if (evidence.field_path) {
    return evidence.value ? `${evidence.field_path} = ${evidence.value}` : evidence.field_path;
  }
  return evidence.value ?? null;
}

export function trailFromClaim(
  claim: Claim,
  options: { rule?: string | null; emptySearches?: EmptySearch[] } = {},
): TrailModel {
  const rule: TrailModel["rule"] = options.rule
    ? { text: options.rule, from: "claim" }
    : { text: CLAIM_STATUS_MEANING[claim.status], from: "status_definition" };
  const emptySearches = (options.emptySearches ?? []).filter((s) => s.claim_id === claim.id);

  if (claim.status === "not_checked") {
    return { state: "not_checked", sources: [], emptySearches: [], findings: [], rule, disagree: false };
  }

  const sources = new Map<string, TrailSource>();
  const findings: string[] = [];

  claim.record.forEach((statement, statementIndex) => {
    // One statement resting on several sources is a conclusion, not a fact from any one
    // of them: each source then shows what was read from it, and the conclusion is
    // listed with the rule.
    const shared = statement.evidence.length > 1;
    if (shared) findings.push(statement.text);

    statement.evidence.forEach((evidence, evidenceIndex) => {
      const key = sourceKey(evidence);
      const group = sources.get(key) ?? { key, evidence: [], facts: [] };
      group.evidence.push(evidence);
      group.facts.push({
        key: evidence.id ?? `${statementIndex}-${evidenceIndex}`,
        as_of: evidence.source.as_of,
        text: shared ? (excerpt(evidence) ?? "Read for this claim. No excerpt was recorded") : statement.text,
        evidence,
        part: statement.part ?? null,
        estimate: shared ? null : (statement.estimate ?? null),
      });
      sources.set(key, group);
    });
  });

  return {
    state: sources.size > 0 ? "found" : "nothing_found",
    sources: [...sources.values()],
    emptySearches,
    findings,
    rule,
    disagree: claim.status === "conflicting_evidence" && sources.size > 1,
  };
}

/* ───────────────────────── Pipeline rail ───────────────────────── */

export type StationKey = "discover" | "verify" | "evaluate" | "act";

export interface PipelineInput {
  /** `/app/cases/{id}` */
  basePath: string;
  created_at: string;
  owner_name: string;
  /** Set when the case was opened from a thesis shortlist. */
  thesis_id: string | null;
  identity_confirmed: boolean;
  /** Every run on the case, any order. */
  runs: { kind: RunKind; state: "pending" | "running" | "done" | "failed"; finished_at: string | null }[];
  /** The run going right now, when there is one. */
  live_run_kind: RunKind | null;
  claim_counts: ClaimStatusCounts;
  assessment: {
    version: number;
    created_at: string;
    disposition: Disposition;
    /** Weighted share of criteria that could be assessed, 0 to 1. Null when the case has none. */
    assessable_share: number | null;
  } | null;
  /** Null when no request list has been built. `draft` covers a list with no approved message. */
  request: {
    status: RequestStatus | "sending" | "unknown";
    documents: number;
    at: string | null;
  } | null;
}

export interface Station {
  key: StationKey;
  label: string;
  /** done: the stage produced a result. open: it has not. live: its run is going now. */
  state: "done" | "open" | "live";
  /** What the stage produced, in one line, then at most one line of detail. */
  produced: string;
  detail: string | null;
  /** ISO timestamp of the result. Null when there is none. */
  when: string | null;
  /** "2nd pass" when the stage has been run again. */
  pass: string | null;
  /** The share of this stage's work that was not done, 0 to 1. Hatched on the connector. */
  not_done_share: number;
  /** What the hatched share is, in words. */
  not_done_note: string | null;
  /** The tab that holds this stage's result. */
  href: string;
  /** The next action, on the current stage only. */
  action: { label: string; href: string } | null;
}

function ordinal(n: number): string {
  const rest = n % 100;
  if (rest >= 11 && rest <= 13) return `${n}th`;
  return `${n}${["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
}

const DISPOSITION_WORDS: Record<Disposition, string> = {
  prioritise: "Prioritise",
  investigate_further: "Investigate further",
  deprioritise: "Deprioritise",
  cannot_assess: "Cannot assess",
};

export function pipelineStations(input: PipelineInput): Station[] {
  const { basePath, claim_counts: counts } = input;
  const claims = CLAIM_STATUSES.reduce((sum, status) => sum + counts[status], 0);
  const settled = claims - counts.not_checked;
  const verifyRuns = input.runs.filter(
    (run) => (run.kind === "verify" || run.kind === "recheck") && run.state === "done",
  );
  const lastVerify = verifyRuns
    .map((run) => run.finished_at)
    .filter((at): at is string => at !== null)
    .sort()
    .at(-1);
  const verifyLive = input.live_run_kind === "verify" || input.live_run_kind === "recheck";
  const evaluateLive = input.live_run_kind === "evaluate";
  const plural = (n: number, one: string) => `${n} ${n === 1 ? one : `${one}s`}`;

  /* Discover */
  const discover: Station = input.thesis_id
    ? {
        key: "discover",
        label: "Discover",
        state: "done",
        produced: "From a thesis shortlist",
        detail: null,
        when: input.created_at,
        pass: null,
        not_done_share: 0,
        not_done_note: null,
        href: `/app/discover/${encodeURIComponent(input.thesis_id)}`,
        action: null,
      }
    : {
        key: "discover",
        label: "Discover",
        state: "open",
        produced: `Added directly by ${input.owner_name}`,
        detail: "No thesis search produced this case",
        when: input.created_at,
        pass: null,
        not_done_share: 0,
        not_done_note: null,
        href: basePath,
        action: null,
      };

  /* Verify */
  let verify: Station;
  const verifyBase = {
    key: "verify" as const,
    label: "Verify",
    pass: verifyRuns.length > 1 ? `${ordinal(verifyRuns.length)} pass` : null,
    href: `${basePath}/claims`,
  };
  if (!input.identity_confirmed) {
    verify = {
      ...verifyBase,
      state: "open",
      produced: "Waiting on identity",
      detail: "No record is attached until the legal entity is confirmed",
      when: null,
      pass: null,
      not_done_share: 0,
      not_done_note: null,
      action: { label: "Resolve identity", href: `${basePath}/identity` },
    };
  } else if (verifyLive) {
    verify = {
      ...verifyBase,
      state: "live",
      produced: claims > 0 ? plural(claims, "claim") : "Reading the record",
      detail: "Checks are running",
      when: null,
      not_done_share: 0,
      not_done_note: null,
      action: null,
    };
  } else if (verifyRuns.length === 0) {
    verify = {
      ...verifyBase,
      state: "open",
      produced: "Not started",
      detail: claims > 0 ? `${plural(claims, "claim")} on file, none checked` : "No claims on file yet",
      when: null,
      not_done_share: 0,
      not_done_note: null,
      action: { label: "Open claims to run verify", href: `${basePath}/claims` },
    };
  } else {
    const notChecked = counts.not_checked;
    verify = {
      ...verifyBase,
      state: "done",
      produced: plural(claims, "claim"),
      detail:
        claims === 0
          ? "No claims on file"
          : notChecked > 0
            ? `${settled} settled · ${notChecked} not checked`
            : `${settled} settled`,
      when: lastVerify ?? null,
      not_done_share: claims > 0 ? notChecked / claims : 0,
      not_done_note: notChecked > 0 ? `${plural(notChecked, "check")} not run` : null,
      action:
        notChecked > 0
          ? { label: `See the ${plural(notChecked, "check")} not run`, href: `${basePath}/claims?status=not_checked` }
          : null,
    };
  }

  /* Evaluate */
  let evaluate: Station;
  const evaluateBase = { key: "evaluate" as const, label: "Evaluate", href: `${basePath}/assessment` };
  if (evaluateLive) {
    evaluate = {
      ...evaluateBase,
      state: "live",
      produced: "Applying the scoring policy",
      detail: null,
      when: null,
      pass: null,
      not_done_share: 0,
      not_done_note: null,
      action: null,
    };
  } else if (input.assessment && input.identity_confirmed) {
    const share = input.assessment.assessable_share;
    const unassessed = share === null ? 0 : Math.max(0, 1 - share);
    evaluate = {
      ...evaluateBase,
      state: "done",
      produced: `Version ${input.assessment.version}`,
      detail: DISPOSITION_WORDS[input.assessment.disposition],
      when: input.assessment.created_at,
      pass: input.assessment.version > 1 ? `${ordinal(input.assessment.version)} pass` : null,
      not_done_share: unassessed,
      not_done_note:
        unassessed > 0 ? `${Math.round(unassessed * 100)}% of criteria could not be assessed` : null,
      action: null,
    };
  } else {
    evaluate = {
      ...evaluateBase,
      state: "open",
      produced: "Not assessed yet",
      detail: input.identity_confirmed ? "Follows verification" : "Waiting on identity",
      when: null,
      pass: null,
      not_done_share: 0,
      not_done_note: null,
      action: null,
    };
  }

  /* Act */
  const actBase = {
    key: "act" as const,
    label: "Act",
    pass: null,
    not_done_share: 0,
    not_done_note: null,
    href: `${basePath}/request`,
  };
  const review = { label: "Review request", href: `${basePath}/request` };
  let act: Station;
  const request = input.request;
  if (!request) {
    act = {
      ...actBase,
      state: "open",
      produced: "No request yet",
      detail: evaluate.state === "done" ? "A request list can be built from the assessment" : null,
      when: null,
      action: evaluate.state === "done" ? { label: "Open request", href: `${basePath}/request` } : null,
    };
  } else {
    const documents = plural(request.documents, "document");
    const byStatus: Record<
      NonNullable<PipelineInput["request"]>["status"],
      Pick<Station, "state" | "produced" | "detail" | "action">
    > = {
      draft: { state: "open", produced: "Request drafted", detail: `${documents} · awaiting your approval`, action: review },
      approved: { state: "open", produced: "Approved, not sent yet", detail: documents, action: review },
      sending: { state: "open", produced: "Sending", detail: documents, action: null },
      sent: { state: "done", produced: "Sent once", detail: `${documents} requested`, action: null },
      // A suppressed send is not a send, so the station stays open.
      suppressed_test_mode: { state: "open", produced: "Suppressed (test mode)", detail: "Not sent", action: null },
      failed: { state: "open", produced: "Failed · not sent", detail: documents, action: review },
      unknown: { state: "open", produced: "Send outcome unknown", detail: documents, action: review },
    };
    act = { ...actBase, ...byStatus[request.status], when: request.at };
  }

  // Only the current stage carries its action: the first one that still needs something.
  const stations = [discover, verify, evaluate, act];
  const current = stations.find((station) => station.action !== null);
  return stations.map((station) => (station === current ? station : { ...station, action: null }));
}

/* ───────────────────────── Coverage map ───────────────────────── */

export type CoverageCellState =
  /** At least one dated fact from an independent source. */
  | "found"
  /** The seller's own material: where the claim came from. */
  | "seller"
  /** A search ran and returned nothing. Only ever set from a recorded empty search. */
  | "searched_empty"
  /** No search was run for any claim of this kind. */
  | "not_searched"
  /** No fact from this class, and no record of a search. */
  | "none";

export interface CoverageCell {
  reliability: ReliabilityClass;
  state: CoverageCellState;
  /** Dated facts in the cell. */
  count: number;
  /** Most recent as-of date among them. */
  latest_as_of: string | null;
  claim_numbers: number[];
  source_ids: string[];
}

export interface CoverageRow {
  category: string;
  claim_numbers: number[];
  counts: ClaimStatusCounts;
  /** Why the whole row is hatched, when it is. */
  not_searched_reason: NotCheckedReason | "mixed" | null;
  cells: CoverageCell[];
}

export interface CoverageModel {
  columns: ReliabilityClass[];
  rows: CoverageRow[];
  /** Whether any cell is drawn from a recorded empty search, so the legend can list it. */
  has_empty_searches: boolean;
}

export function coverageFromClaims(
  claims: Claim[],
  options: { emptySearches?: EmptySearch[]; identityOpen?: boolean } = {},
): CoverageModel {
  const columns: ReliabilityClass[] = [...INDEPENDENT_CLASSES, ...SELLER_CLASSES];
  const empty = options.emptySearches ?? [];
  const groups = new Map<string, Claim[]>();
  for (const claim of [...claims].sort((a, b) => a.number - b.number)) {
    groups.set(claim.category, [...(groups.get(claim.category) ?? []), claim]);
  }

  const rows: CoverageRow[] = [...groups].map(([category, group]) => {
    const counts = emptyCounts();
    for (const claim of group) counts[claim.status] += 1;
    const allUnchecked = group.every((claim) => claim.status === "not_checked");
    const reasons = new Set(group.map((claim) => claim.not_checked_reason ?? null));
    const rowReason: CoverageRow["not_searched_reason"] = options.identityOpen
      ? "identity_unresolved"
      : allUnchecked
        ? reasons.size === 1
          ? ([...reasons][0] ?? "mixed")
          : "mixed"
        : null;

    const cells = columns.map((reliability): CoverageCell => {
      const seen = new Set<string>();
      const numbers = new Set<number>();
      const sourceIds = new Set<string>();
      let latest: string | null = null;
      const take = (evidence: Evidence, claim: Claim, index: string) => {
        if (evidence.source.reliability !== reliability) return;
        const id = evidence.id ?? `${claim.id}-${index}`;
        if (seen.has(id)) return;
        seen.add(id);
        numbers.add(claim.number);
        if (evidence.source.id) sourceIds.add(evidence.source.id);
        const asOf = evidence.source.as_of;
        if (asOf && (latest === null || asOf > latest)) latest = asOf;
      };
      const seller = (SELLER_CLASSES as readonly ReliabilityClass[]).includes(reliability);
      for (const claim of group) {
        if (seller) take(claim.stated_in, claim, "stated");
        claim.record.forEach((statement, s) =>
          statement.evidence.forEach((evidence, e) => take(evidence, claim, `${s}-${e}`)),
        );
      }

      let state: CoverageCellState;
      if (seen.size > 0) state = seller ? "seller" : "found";
      else if (seller) state = "none";
      else if (rowReason) state = "not_searched";
      else if (empty.some((s) => s.reliability === reliability && group.some((c) => c.id === s.claim_id))) {
        state = "searched_empty";
      } else state = "none";

      return {
        reliability,
        state,
        count: seen.size,
        latest_as_of: latest,
        claim_numbers: [...numbers].sort((a, b) => a - b),
        source_ids: [...sourceIds],
      };
    });

    return {
      category,
      claim_numbers: group.map((claim) => claim.number),
      counts,
      not_searched_reason: rowReason,
      cells,
    };
  });

  return {
    columns,
    rows,
    has_empty_searches: rows.some((row) => row.cells.some((cell) => cell.state === "searched_empty")),
  };
}

/**
 * Where the case is thin, in one sentence: kinds of claim that were never searched, and
 * kinds that rest on a single class of independent source.
 */
export function coverageThinSpots(model: CoverageModel): string[] {
  const spots: string[] = [];
  for (const row of model.rows) {
    if (row.not_searched_reason) {
      spots.push(`${row.category}: not searched`);
      continue;
    }
    const found = row.cells.filter((cell) => cell.state === "found");
    if (found.length === 0) spots.push(`${row.category}: no independent fact`);
    else if (found.length === 1) {
      spots.push(`${row.category}: ${CLASS_SHORT_LABEL[found[0].reliability].toLowerCase()} only`);
    }
  }
  return spots;
}

/* ───────────────────────── Change timeline ───────────────────────── */

export interface VersionState {
  claims: number;
  settled: number;
  not_checked: number;
  disposition: Disposition;
}

/** What arrived between two versions. */
export interface TimelineCause {
  /** `"Lease agreement.pdf" received from seller`, or the trigger phrase when that is all there is. */
  label: string;
  /** When it arrived. Null when only the trigger phrase is recorded. */
  at: string | null;
  by: string | null;
  /** Claim numbers that changed in the version it produced. */
  changed_claims: number[];
}

export interface TimelineEntry {
  meta: AssessmentVersionMeta;
  /** The one-line state of the version. Null when it was not loaded. */
  state: VersionState | null;
  /** What came in before this version. Null for the first one. */
  cause: TimelineCause | null;
  diff: AssessmentDiff | null;
}

export function versionState(statuses: ClaimStatus[], disposition: Disposition): VersionState {
  const notChecked = statuses.filter((status) => status === "not_checked").length;
  return {
    claims: statuses.length,
    settled: statuses.length - notChecked,
    not_checked: notChecked,
    disposition,
  };
}

/**
 * The cause entry for a version: the uploaded documents the version names in
 * `trigger_document_ids`, matched by id. The API gives no separate trigger record, so the
 * time is the upload time of the last of them; with no document it is the trigger phrase
 * alone and no time.
 */
export function timelineCause(
  triggerLabel: string,
  triggerDocumentIds: string[],
  diff: AssessmentDiff | null,
  documents: { id: string; filename: string; uploaded_at: string; uploaded_by_name: string | null }[],
): TimelineCause {
  const changed = (diff?.changes ?? [])
    .flatMap((change) => (change.kind === "claim_status" ? [change.claim_number] : []))
    .filter((number) => number > 0)
    .sort((a, b) => a - b);
  const named = documents.filter((doc) => triggerDocumentIds.includes(doc.id));
  if (named.length === 0) return { label: triggerLabel, at: null, by: null, changed_claims: changed };
  const names = named.map((doc) => `“${doc.filename}”`).join(", ");
  const last = [...named].sort((a, b) => a.uploaded_at.localeCompare(b.uploaded_at)).at(-1)!;
  return {
    label: `${names} received from seller`,
    at: last.uploaded_at,
    by: last.uploaded_by_name,
    changed_claims: changed,
  };
}

/**
 * Claim changes are the roots. Everything else moved because a claim did, but the API
 * does not say which one, so derived changes are returned as one group, never attached
 * to a particular claim.
 */
export function splitChanges(diff: AssessmentDiff): {
  claimChanges: Extract<AssessmentChange, { kind: "claim_status" }>[];
  derived: Exclude<AssessmentChange, { kind: "claim_status" }>[];
} {
  const claimChanges: Extract<AssessmentChange, { kind: "claim_status" }>[] = [];
  const derived: Exclude<AssessmentChange, { kind: "claim_status" }>[] = [];
  for (const change of diff.changes) {
    if (change.kind === "claim_status") claimChanges.push(change);
    else derived.push(change);
  }
  return { claimChanges, derived };
}

/* ───────────────────────── Cost meter ───────────────────────── */

export interface MeterSegment {
  key: string;
  label: string;
  credits: number;
  /** The step is going now, so its segment is still growing. */
  running: boolean;
  /** How many recorded steps the segment adds up, when more than one. */
  steps: number;
}

export interface MeterModel {
  used: number;
  budget: number;
  model_usd: number;
  /** In run order. Steps that spent no credits take no width and are not listed. */
  segments: MeterSegment[];
  /** Steps replayed from the cache: listed as text, since they cost nothing. */
  cached_steps: number;
  checks_not_run: number;
  /** Average credits a claim check has cost so far. Null when no claim check has spent any. */
  credits_per_claim: number | null;
}

/** Per-claim steps share a key family; drawn one by one they would be slivers. */
const STEP_FAMILY_LABEL: Record<string, string> = {
  "evidence.claim": "Check claims",
  "recheck.facts": "Re-check claims",
  "claims.extract": "Extract claims",
};

function withRemainder(segments: MeterSegment[], used: number): MeterSegment[] {
  const sum = segments.reduce((total, segment) => total + segment.credits, 0);
  const rest = used - sum;
  // Credits the step lines do not account for are still spent, so they are drawn and named.
  return rest > 0.05
    ? [...segments, { key: "unattributed", label: "Not attributed to a step", credits: rest, running: false, steps: 1 }]
    : segments;
}

export function meterFromCostOut(cost: CaseCostOut): MeterModel {
  const lines = [...cost.by_step].sort((a, b) => a.at.localeCompare(b.at));
  const segments = new Map<string, MeterSegment>();
  let claimCredits = 0;
  let claimChecks = 0;
  for (const line of lines) {
    const family = line.step_key.split(":")[0];
    if (family === "evidence.claim" && !line.cached) {
      claimChecks += 1;
      claimCredits += line.cost.crustdata_credits;
    }
    if (line.cached || line.cost.crustdata_credits <= 0) continue;
    const key = `${line.run_id}:${family}`;
    const existing = segments.get(key);
    if (existing) {
      existing.credits += line.cost.crustdata_credits;
      existing.steps += 1;
      existing.label = STEP_FAMILY_LABEL[family] ?? existing.label;
    } else {
      segments.set(key, {
        key,
        label: line.step_label,
        credits: line.cost.crustdata_credits,
        running: false,
        steps: 1,
      });
    }
  }
  return {
    used: cost.crustdata_credits,
    budget: cost.credit_budget,
    model_usd: cost.llm_usd,
    segments: withRemainder([...segments.values()], cost.crustdata_credits),
    cached_steps: lines.filter((line) => line.cached).length,
    checks_not_run: cost.checks_not_run,
    credits_per_claim: claimChecks > 0 && claimCredits > 0 ? claimCredits / claimChecks : null,
  };
}

export function meterFromCaseCost(cost: CaseCost): MeterModel {
  const segments = cost.lines
    .filter((line) => !line.from_cache && (line.credits ?? 0) > 0)
    .map((line) => ({
      key: line.id,
      label: line.step_label,
      credits: line.credits ?? 0,
      running: false,
      steps: 1,
    }));
  return {
    used: cost.credits_used,
    budget: cost.credit_budget,
    model_usd: cost.model_usd,
    segments: withRemainder(segments, cost.credits_used),
    cached_steps: cost.lines.filter((line) => line.from_cache).length,
    checks_not_run: cost.checks_not_run ?? 0,
    credits_per_claim: null,
  };
}

/** The meter of one run while it is going: the running step's segment is still growing. */
export function meterFromRun(run: Run, creditsPerClaim: number | null = null): MeterModel {
  const stepCredits = run.steps.reduce((sum, step) => sum + (step.from_cache ? 0 : (step.credits_used ?? 0)), 0);
  const segments: MeterSegment[] = [];
  for (const step of run.steps) {
    if (step.from_cache) continue;
    const running = step.status === "running";
    // The run total moves before the running step reports its own figure.
    const credits = running
      ? Math.max(step.credits_used ?? 0, run.credits_used - stepCredits + (step.credits_used ?? 0))
      : (step.credits_used ?? 0);
    if (credits <= 0 && !running) continue;
    segments.push({ key: step.id, label: step.label, credits: Math.max(0, credits), running, steps: 1 });
  }
  return {
    used: run.credits_used,
    budget: run.credit_budget,
    model_usd: run.steps.reduce((sum, step) => sum + (step.model_usd ?? 0), 0),
    segments: run.status === "running" ? segments : withRemainder(segments, run.credits_used),
    cached_steps: run.steps.filter((step) => step.from_cache).length,
    checks_not_run: run.checks_not_run ?? 0,
    credits_per_claim: creditsPerClaim,
  };
}

/** How many more claim checks the remaining credits would cover. Null when it cannot be estimated. */
export function claimsLeftEstimate(model: MeterModel): number | null {
  if (model.credits_per_claim === null || model.credits_per_claim <= 0) return null;
  const left = model.budget - model.used;
  if (left <= 0) return 0;
  return Math.floor(left / model.credits_per_claim);
}
