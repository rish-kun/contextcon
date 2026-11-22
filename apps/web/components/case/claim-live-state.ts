/**
 * Where one claim stands in the run being followed, worked out from things that really
 * happened: the run's steps (`checks.claim:{id}`, with their live `detail`), and the
 * activity events that name the claim in `ref`.
 *
 * Nothing here guesses. "Checking" needs a running step or a `checking` finding for this
 * claim. A claim whose check has not started is queued, with how many are ahead of it
 * when the step list says so. While identity is open, a claim waits and says that.
 */
import type { CaseDetail, RunOut, StepOut } from "@/lib/api/client";
import type { RunActivityView, SourceRow } from "@/lib/run/activity-store";
import type { Activity, ActivityItem, ActivitySource } from "@/lib/run/types";

export type ClaimPhase =
  | "waiting_identity"
  | "queued"
  | "gathering"
  | "reading"
  | "deciding"
  | "settled";

export interface ClaimFact {
  key: string;
  /** What was found, in the event's own words. */
  text: string;
  /** Date of the fact. Null reads as "no date". */
  asOf: string | null;
}

export interface ClaimLive {
  phase: ClaimPhase;
  /**
   * True when activity events describe this claim. Without them only the step is known,
   * so the phases between "checking" and "settled" cannot be told apart and are not shown.
   */
  detailed: boolean;
  /** What is being done for this claim now. */
  line: string | null;
  progress: { done: number; total: number } | null;
  /** Checks that will run before this one. Null when the step list does not say. */
  ahead: number | null;
  /** Pages and records read for this claim, oldest first. */
  sources: SourceRow[];
  /** Dated facts found for this claim so far. */
  facts: ClaimFact[];
  /** Facts the model extracted and the checker threw out for having no matching passage. */
  factCount: number;
  rejected: number;
  /** Set once the rule has fired. */
  status: string | null;
  /** The public source the settling evidence came from, with its snippet. */
  evidence: { source: ActivitySource | null; snippet: string | null; gap: string | null; count: number | null } | null;
  /** While identity is open: true if the identity step is running right now. */
  identityRunning: boolean;
  /** The event that last changed this claim's stage, to tell arrival from history. */
  seq: number;
  /** True if that event arrived in front of the reader. */
  fresh: boolean;
}

const SETTLED_STEP = new Set<StepOut["state"]>(["done", "failed", "skipped_budget"]);

// Kept local (not imported from the store) so this module has no runtime imports and
// its rules can be tested on their own.
// A re-check of the same claim carries a suffix: `checks.claim:{id}@2`, `…~1`.
const stepClaimId = (key: string | null) =>
  key ? (/(?:^|\.)(?:claim|facts):([^@~:]+)(?:[@~]\d+)?$/.exec(key)?.[1] ?? null) : null;
const isClaimStep = (key: string) => stepClaimId(key) !== null;
const claimOfEvent = (event: Activity) =>
  event.ref?.type === "claim" ? event.ref.id : stepClaimId(event.step_key);

function factText(item: ActivityItem): string {
  return (
    item.title ??
    item.name ??
    [item.company, item.round].filter(Boolean).join(" · ") ??
    item.event_kind ??
    "Fact"
  );
}

export function claimLiveState(
  claimId: string,
  input: {
    detail: CaseDetail;
    run: RunOut | null;
    runActive: boolean;
    view: RunActivityView;
    /** The events on screen, oldest first. */
    events: Activity[];
    /** Findings at or below this `seq` are history. */
    settledSeq: number;
  },
): ClaimLive | null {
  const { detail, run, runActive, view, events, settledSeq } = input;
  const claim = detail.claims.find((c) => c.id === claimId);
  if (!claim || !run) return null;

  // A claim can have more than one check step in a run (a re-check after a pick). The one
  // that counts is the one still to settle; failing that, the latest.
  const steps = run.steps.filter((s) => stepClaimId(s.key) === claimId);
  const step =
    steps.find((s) => s.state === "running") ?? steps.find((s) => s.state === "pending") ?? steps.at(-1);
  const act = view.claims.get(claimId);
  const own = events.filter((event) => claimOfEvent(event) === claimId);
  const sources = view.sources.filter((row) => row.claimId === claimId);

  let factCount = 0;
  let rejected = 0;
  const facts: ClaimFact[] = [];
  for (const event of own) {
    if (event.kind === "model") {
      factCount += event.counts?.facts ?? 0;
      rejected += event.counts?.rejected_no_span ?? 0;
    }
    // A dated event or record found while checking this claim.
    if (event.kind === "finding" && event.subject !== "claim") {
      for (const item of event.items ?? []) {
        facts.push({ key: `${event.seq}:${item.id}`, text: factText(item), asOf: item.date ?? null });
      }
    }
  }
  // A page read for this claim that states a date is a dated fact's source.
  for (const row of sources) {
    if (row.source.state === "read" && row.source.as_of && row.source.title) {
      facts.push({ key: `s${row.seq}`, text: row.source.title, asOf: row.source.as_of });
    }
  }

  const base = {
    detailed: own.length > 0 || act !== undefined,
    line: null,
    progress: null,
    ahead: null,
    sources,
    facts,
    factCount,
    rejected,
    status: null,
    evidence: null,
    identityRunning: false,
    seq: act?.seq ?? 0,
    fresh: (act?.seq ?? 0) > settledSeq,
  } satisfies Partial<ClaimLive>;

  // The rule has fired: the finding carries the status and a public evidence reference.
  if (act && (act.stage === "settled" || act.stage === "not_checked")) {
    return {
      ...base,
      phase: "settled",
      status: act.status ?? (act.stage === "not_checked" ? "not_checked" : null),
      evidence: { source: act.source, snippet: act.snippet, gap: act.gap, count: act.evidenceCount },
    };
  }
  // The step settled and no finding said how: the case reload carries the result.
  if (step && SETTLED_STEP.has(step.state)) return null;

  const running = step?.state === "running" || act?.stage === "checking";
  if (running) {
    // The furthest point the events show: a page read, then a model read of what was found.
    const read = own.some(
      (event) => event.kind === "source" || (event.kind === "call" && event.call?.endpoint === "web_fetch"),
    );
    const decided = own.some((event) => event.kind === "model");
    return {
      ...base,
      phase: decided ? "deciding" : read ? "reading" : "gathering",
      line: act?.line ?? step?.detail ?? null,
      progress: act?.progress ?? null,
    };
  }

  if (!runActive) return null;

  // Checks cannot start until the legal entity is confirmed.
  if (detail.identity.state !== "confirmed") {
    const identityStep = run.steps.find((s) => s.key.includes("identity"));
    return {
      ...base,
      phase: "waiting_identity",
      identityRunning: identityStep?.state === "running" || identityStep?.state === "pending",
      line: identityStep?.state === "running" ? (view.steps.get(identityStep.key)?.line ?? identityStep.detail) : null,
    };
  }

  if (step?.state === "pending" || act?.stage === "queued") {
    const ahead = step
      ? run.steps.filter(
          (other) => isClaimStep(other.key) && other.position < step.position && !SETTLED_STEP.has(other.state),
        ).length
      : null;
    return { ...base, phase: "queued", ahead };
  }

  // No step and no event names this claim: the run may not touch it at all (a single-claim
  // check, a recheck), so the row keeps its stored state until its own step exists.
  return null;
}
