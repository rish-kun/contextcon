/**
 * Folds a run's activity events into what the live view draws: the "now" line, each
 * step's sub-line, the Crustdata tally, the sources read, and the findings by subject.
 *
 * Everything here is a pure function of the stored events. Nothing is estimated and no
 * row is made up: if an event did not say it, the view does not show it. The same
 * function draws a live run, a reload mid-run, the run log and a replay.
 */
import type {
  Activity,
  ActivityCall,
  ActivityItem,
  ActivitySource,
  MarkState,
} from "./types";

/* ───────────────────────── The log ───────────────────────── */

/** Adds events to an ordered list, once each. Returns the same list when nothing is new. */
export function appendActivities(current: Activity[], incoming: Activity[]): Activity[] {
  if (incoming.length === 0) return current;
  const last = current.at(-1)?.seq ?? 0;
  // The common case: the stream delivers in order.
  if (incoming.every((event, index) => event.seq > (index === 0 ? last : incoming[index - 1].seq))) {
    return [...current, ...incoming];
  }
  const bySeq = new Map(current.map((event) => [event.seq, event]));
  let changed = false;
  for (const event of incoming) {
    if (!bySeq.has(event.seq)) {
      bySeq.set(event.seq, event);
      changed = true;
    }
  }
  return changed ? [...bySeq.values()].sort((a, b) => a.seq - b.seq) : current;
}

/**
 * The claim a step checks, from its key: `checks.claim:{id}`, `recheck.facts:{id}`. A
 * re-check of the same claim carries a suffix (`…@2` after a pick, `…~1` when deferred).
 */
export function claimStepId(key: string | null | undefined): string | null {
  if (!key) return null;
  const match = /(?:^|\.)(?:claim|facts):([^@~:]+)(?:[@~]\d+)?$/.exec(key);
  return match ? match[1] : null;
}

/** The claim an event is about: its `ref`, or failing that the claim its step checks. */
export function claimOfEvent(event: Activity): string | null {
  return event.ref?.type === "claim" ? event.ref.id : claimStepId(event.step_key);
}

/* ───────────────────────── The view ───────────────────────── */

export type OrbWork = "working" | "searching" | "connecting" | "weaving" | "solving" | "composing";

export interface NowLine {
  seq: number;
  at: string;
  label: string;
  stepKey: string | null;
}

export interface StepActivity {
  /** The latest `status` label for this step. */
  line: string | null;
  progress: { done: number; total: number } | null;
  notices: Activity[];
  /** Set by a `seller_document` source: shown in the step list and nowhere else. */
  document: string | null;
  firstAt: string | null;
  lastAt: string | null;
  events: number;
}

export interface TallyRow {
  endpoint: string;
  calls: number;
  failed: number;
  retried: number;
  fromCache: number;
  credits: number;
  /** Sums of the events' `counts`, by key. */
  counts: Record<string, number>;
  /** The two most recent highlights. */
  highlights: string[];
}

export interface Tally {
  rows: Map<string, TallyRow>;
  calls: number;
  fromCache: number;
  credits: number;
  model: { reads: number; usd: number; counts: Record<string, number> };
}

export interface SourceRow {
  seq: number;
  at: string;
  stepKey: string | null;
  label: string;
  detail: string | null;
  source: ActivitySource;
  claimId: string | null;
}

export interface ClaimLive {
  id: string;
  stage: "queued" | "checking" | "settled" | "not_checked";
  category: string | null;
  status: string | null;
  previousStatus: string | null;
  snippet: string | null;
  gap: string | null;
  evidenceCount: number | null;
  /** The public source the settling evidence came from. */
  source: ActivitySource | null;
  /** What is being done for this claim right now. */
  line: string | null;
  progress: { done: number; total: number } | null;
  /** The event that last changed the stage. */
  seq: number;
  detail: string | null;
}

export interface CompanyRow extends ActivityItem {
  /** The event that first named the company: arrival order. */
  firstSeq: number;
  /** The event that last changed it. */
  seq: number;
  /** Position inside its first event, for the 60 ms stagger. */
  slot: number;
  marks: Record<string, MarkState>;
}

export interface RoundRow extends ActivityItem {
  seq: number;
}

export interface InvestorRow {
  key: string;
  name: string;
  rounds: RoundRow[];
  /** Arrival order while rounds are still being read. */
  firstSeq: number;
  /** The event that last added a round. */
  seq: number;
  rank: number | null;
  /** True once the rank step has named it; false means "not ranked · no dated round". */
  ranked: boolean;
}

export interface FindingGroup<T> {
  rows: T[];
  /** Group totals as the latest event stated them. */
  counts: Record<string, number>;
  /** Seq of the event that last touched the group. */
  seq: number;
}

export interface SubjectFinding {
  seq: number;
  at: string;
  label: string;
  detail: string | null;
  stage: string | null;
  items: ActivityItem[];
  counts: Record<string, number>;
}

export interface RunActivityView {
  /** How many events this view was built from. Zero means nothing was recorded. */
  total: number;
  now: NowLine | null;
  /** What kind of work the latest event was, for the header orb. */
  work: OrbWork;
  /** The provider of the most recent call, for the "still waiting on" suffix. */
  lastProvider: "crustdata" | "anthropic" | null;
  steps: Map<string, StepActivity>;
  tally: Tally;
  /** Server totals from the latest call that carried them. */
  cost: { credits: number | null; usd: number | null; lastDelta: CostDelta | null };
  /** Oldest first. The ticker reverses it. */
  sources: SourceRow[];
  sourceCounts: { read: number; failed: number };
  companies: FindingGroup<CompanyRow>;
  /** Seq of the `scored` finding, once there is one. */
  companiesScoredSeq: number | null;
  /** Step key that emitted the scores, so the view can wait for it to finish. */
  companiesScoredStep: string | null;
  claims: Map<string, ClaimLive>;
  claimCounts: Record<string, number>;
  identity: SubjectFinding | null;
  rounds: FindingGroup<RoundRow>;
  investors: InvestorRow[];
  investorsRankedSeq: number | null;
  investorsRankedStep: string | null;
  events: FindingGroup<ActivityItem>;
  peers: FindingGroup<ActivityItem>;
  assessment: SubjectFinding | null;
  requestList: SubjectFinding | null;
  notices: Activity[];
}

export interface CostDelta {
  seq: number;
  credits: number | null;
  usd: number | null;
  fromCache: boolean;
}

function emptyGroup<T>(): FindingGroup<T> {
  return { rows: [], counts: {}, seq: 0 };
}

function cleanCounts(counts: Activity["counts"]): Record<string, number> {
  const out: Record<string, number> = {};
  if (!counts) return out;
  for (const [key, value] of Object.entries(counts)) {
    if (typeof value === "number" && Number.isFinite(value)) out[key] = value;
  }
  return out;
}

/** Later stages send only what changed; a field left out or null keeps its value. */
function mergeItem<T extends ActivityItem>(previous: T | undefined, next: ActivityItem): T {
  const merged = { ...(previous ?? {}) } as Record<string, unknown>;
  for (const [key, value] of Object.entries(next)) {
    if (value !== null && value !== undefined) merged[key] = value;
  }
  return merged as T;
}

const WORK_BY_ENDPOINT: Record<string, OrbWork> = {
  company_identify: "searching",
  company_search: "searching",
  person_search: "searching",
  job_search: "searching",
  web_search: "searching",
  company_enrich: "connecting",
  web_fetch: "connecting",
  messages: "weaving",
};

/** Steps that apply rules or draft text. Matched on the key the pipeline already uses. */
function workForStep(stepKey: string | null): OrbWork | null {
  if (!stepKey) return null;
  if (/(score|rank|gate|evaluate|assess)/.test(stepKey)) return "solving";
  if (/(explain|cards|request_list|draft)/.test(stepKey)) return "composing";
  return null;
}

function workFor(event: Activity): OrbWork | null {
  if (event.kind === "call" && event.call) return WORK_BY_ENDPOINT[event.call.endpoint] ?? "working";
  if (event.kind === "source") return "connecting";
  if (event.kind === "model") return workForStep(event.step_key) ?? "weaving";
  if (event.kind === "status") return workForStep(event.step_key) ?? "working";
  return null;
}

function tallyCall(tally: Tally, event: Activity, call: ActivityCall): void {
  if (call.provider === "anthropic") {
    tally.model.reads += 1;
    tally.model.usd += call.usd ?? 0;
    for (const [key, value] of Object.entries(cleanCounts(event.counts))) {
      tally.model.counts[key] = (tally.model.counts[key] ?? 0) + value;
    }
    return;
  }
  const row: TallyRow = tally.rows.get(call.endpoint) ?? {
    endpoint: call.endpoint,
    calls: 0,
    failed: 0,
    retried: 0,
    fromCache: 0,
    credits: 0,
    counts: {},
    highlights: [],
  };
  row.calls += 1;
  tally.calls += 1;
  if (!call.ok) row.failed += 1;
  else if (call.attempts > 1) row.retried += 1;
  if (call.from_cache) {
    row.fromCache += 1;
    tally.fromCache += 1;
  }
  row.credits += call.credits ?? 0;
  tally.credits += call.credits ?? 0;
  for (const [key, value] of Object.entries(cleanCounts(event.counts))) {
    row.counts[key] = (row.counts[key] ?? 0) + value;
  }
  if (event.highlights?.length) {
    row.highlights = [...row.highlights, ...event.highlights].slice(-2);
  }
  tally.rows.set(call.endpoint, row);
}

function subjectFinding(event: Activity): SubjectFinding {
  return {
    seq: event.seq,
    at: event.at,
    label: event.label,
    detail: event.detail,
    stage: event.items?.[0]?.stage ?? null,
    items: event.items ?? [],
    counts: cleanCounts(event.counts),
  };
}

/** Build the whole view from an ordered list of events. */
export function deriveView(events: Activity[]): RunActivityView {
  const steps = new Map<string, StepActivity>();
  const tally: Tally = {
    rows: new Map(),
    calls: 0,
    fromCache: 0,
    credits: 0,
    model: { reads: 0, usd: 0, counts: {} },
  };
  const sources: SourceRow[] = [];
  const companies = new Map<string, CompanyRow>();
  const companyGroup = emptyGroup<CompanyRow>();
  const claims = new Map<string, ClaimLive>();
  let claimCounts: Record<string, number> = {};
  const rounds = new Map<string, RoundRow>();
  const roundGroup = emptyGroup<RoundRow>();
  const investors = new Map<string, InvestorRow>();
  const eventGroup = emptyGroup<ActivityItem>();
  const eventRows = new Map<string, ActivityItem>();
  const peerGroup = emptyGroup<ActivityItem>();
  const peerRows = new Map<string, ActivityItem>();
  const notices: Activity[] = [];

  const view: RunActivityView = {
    total: events.length,
    now: null,
    work: "working",
    lastProvider: null,
    steps,
    tally,
    cost: { credits: null, usd: null, lastDelta: null },
    sources,
    sourceCounts: { read: 0, failed: 0 },
    companies: companyGroup,
    companiesScoredSeq: null,
    companiesScoredStep: null,
    claims,
    claimCounts,
    identity: null,
    rounds: roundGroup,
    investors: [],
    investorsRankedSeq: null,
    investorsRankedStep: null,
    events: eventGroup,
    peers: peerGroup,
    assessment: null,
    requestList: null,
    notices,
  };

  const claimOf = (id: string): ClaimLive =>
    claims.get(id) ?? {
      id,
      stage: "queued",
      category: null,
      status: null,
      previousStatus: null,
      snippet: null,
      gap: null,
      evidenceCount: null,
      source: null,
      line: null,
      progress: null,
      seq: 0,
      detail: null,
    };

  for (const event of events) {
    const stepKey = event.step_key;
    if (stepKey) {
      const step: StepActivity = steps.get(stepKey) ?? {
        line: null,
        progress: null,
        notices: [],
        document: null,
        firstAt: null,
        lastAt: null,
        events: 0,
      };
      step.firstAt ??= event.at;
      step.lastAt = event.at;
      step.events += 1;
      if (event.kind === "status") {
        step.line = event.label;
        step.progress = event.progress;
      } else if (event.progress) {
        step.progress = event.progress;
      }
      if (event.kind === "notice") step.notices.push(event);
      if (event.kind === "source" && event.source?.type === "seller_document") {
        step.document = event.source.title ?? event.label;
      }
      steps.set(stepKey, step);
    }

    const work = workFor(event);
    if (work) view.work = work;

    const isDocument = event.source?.type === "seller_document";
    if (event.kind === "status" || event.kind === "call" || (event.kind === "source" && !isDocument)) {
      view.now = { seq: event.seq, at: event.at, label: event.label, stepKey };
    }

    // A status or source about one claim is that claim's live sub-line.
    const aboutClaim = claimOfEvent(event);
    if (aboutClaim && (event.kind === "status" || event.kind === "source")) {
      const claim = claimOf(aboutClaim);
      if (claim.stage === "queued" || claim.stage === "checking") {
        claim.line = event.label;
        claim.progress = event.progress;
        claims.set(claim.id, claim);
      }
    }

    switch (event.kind) {
      case "call":
      case "model": {
        const call = event.call;
        if (!call) break;
        view.lastProvider = call.provider;
        tallyCall(tally, event, call);
        if (call.credits_total !== null) view.cost.credits = call.credits_total;
        if (call.usd_total !== null) view.cost.usd = call.usd_total;
        view.cost.lastDelta = {
          seq: event.seq,
          credits: call.provider === "crustdata" ? (call.credits ?? null) : null,
          usd: call.provider === "anthropic" ? (call.usd ?? null) : null,
          fromCache: call.from_cache,
        };
        break;
      }
      case "source": {
        const source = event.source;
        // Uploaded documents never reach the ticker; the step list names them.
        if (!source || source.type === "seller_document") break;
        sources.push({
          seq: event.seq,
          at: event.at,
          stepKey,
          label: event.label,
          detail: event.detail,
          source,
          claimId: aboutClaim,
        });
        if (source.state === "read") view.sourceCounts.read += 1;
        else view.sourceCounts.failed += 1;
        break;
      }
      case "notice":
        notices.push(event);
        break;
      case "finding": {
        const counts = cleanCounts(event.counts);
        const items = event.items ?? [];
        switch (event.subject) {
          case "company": {
            companyGroup.counts = { ...companyGroup.counts, ...counts };
            companyGroup.seq = event.seq;
            items.forEach((item, slot) => {
              const previous = companies.get(item.id);
              const merged = mergeItem<CompanyRow>(previous, item);
              merged.firstSeq = previous?.firstSeq ?? event.seq;
              merged.slot = previous?.slot ?? slot;
              merged.seq = event.seq;
              merged.marks = { ...(previous?.marks ?? {}), ...(item.marks ?? {}) };
              companies.set(item.id, merged);
              if (item.stage === "scored") {
                view.companiesScoredSeq = event.seq;
                view.companiesScoredStep = stepKey;
              }
            });
            break;
          }
          case "claim": {
            claimCounts = { ...claimCounts, ...counts };
            for (const item of items) {
              const claim = claimOf(item.id);
              const stage = item.stage as ClaimLive["stage"];
              claim.stage = stage;
              claim.seq = event.seq;
              claim.category = item.category ?? claim.category;
              claim.previousStatus = item.previous_status ?? claim.previousStatus;
              if (stage === "settled" || stage === "not_checked") {
                claim.status = item.status ?? (stage === "not_checked" ? "not_checked" : claim.status);
                claim.snippet = item.snippet ?? null;
                claim.gap = item.gap ?? null;
                claim.evidenceCount = item.evidence_count ?? null;
                claim.source = event.source;
                claim.detail = event.detail;
                claim.line = null;
                claim.progress = null;
              }
              claims.set(item.id, claim);
            }
            break;
          }
          case "identity":
            view.identity = subjectFinding(event);
            break;
          case "round": {
            roundGroup.counts = { ...roundGroup.counts, ...counts };
            roundGroup.seq = event.seq;
            for (const item of items) {
              const row = mergeItem<RoundRow>(rounds.get(item.id), item);
              row.seq = rounds.get(item.id)?.seq ?? event.seq;
              const isNew = !rounds.has(item.id);
              rounds.set(item.id, row);
              if (!isNew) continue;
              for (const named of item.investors ?? []) {
                const investor: InvestorRow = investors.get(named.key) ?? {
                  key: named.key,
                  name: named.name,
                  rounds: [],
                  firstSeq: event.seq,
                  seq: event.seq,
                  rank: null,
                  ranked: false,
                };
                investor.rounds.push(row);
                investor.seq = event.seq;
                investors.set(named.key, investor);
              }
            }
            break;
          }
          case "investor": {
            roundGroup.counts = { ...roundGroup.counts, ...counts };
            for (const item of items) {
              const investor: InvestorRow = investors.get(item.id) ?? {
                key: item.id,
                name: item.name ?? item.id,
                rounds: [],
                firstSeq: event.seq,
                seq: event.seq,
                rank: null,
                ranked: false,
              };
              if (item.stage === "ranked") {
                investor.rank = item.rank ?? null;
                investor.ranked = true;
                view.investorsRankedSeq = event.seq;
                view.investorsRankedStep = stepKey;
              }
              investors.set(item.id, investor);
            }
            break;
          }
          case "event": {
            eventGroup.counts = { ...eventGroup.counts, ...counts };
            eventGroup.seq = event.seq;
            for (const item of items) eventRows.set(item.id, mergeItem(eventRows.get(item.id), item));
            break;
          }
          case "peer": {
            peerGroup.counts = { ...peerGroup.counts, ...counts };
            peerGroup.seq = event.seq;
            for (const item of items) peerRows.set(item.id, mergeItem(peerRows.get(item.id), item));
            break;
          }
          case "assessment":
            view.assessment = subjectFinding(event);
            break;
          case "request_list":
            view.requestList = subjectFinding(event);
            break;
          default:
            break;
        }
        break;
      }
      default:
        break;
    }
  }

  companyGroup.rows = [...companies.values()];
  roundGroup.rows = [...rounds.values()];
  eventGroup.rows = [...eventRows.values()];
  peerGroup.rows = [...peerRows.values()];
  view.investors = [...investors.values()];
  view.claimCounts = claimCounts;
  return view;
}

/** Claim stage totals counted from the rows, for when no event carried the totals. */
export function countClaimStages(claims: Iterable<ClaimLive>): Record<ClaimLive["stage"], number> {
  const totals = { queued: 0, checking: 0, settled: 0, not_checked: 0 };
  for (const claim of claims) totals[claim.stage] += 1;
  return totals;
}

/* ───────────────────────── Regions and pacing ───────────────────────── */

export type Region = "sources" | "findings";

/** Which pacing queue an event waits in. Everything else is shown the moment it arrives. */
export function regionOf(event: Activity): Region | null {
  if (event.kind === "source" && event.source?.type !== "seller_document") return "sources";
  if (event.kind === "finding") return "findings";
  return null;
}

/** The events on screen: paced regions up to their watermark, the rest in full. */
export function visibleEvents(
  events: Activity[],
  upto: Record<Region, number>,
): Activity[] {
  return events.filter((event) => {
    const region = regionOf(event);
    return region === null || event.seq <= upto[region];
  });
}
