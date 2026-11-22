/**
 * Typed client for the DealProof API.
 *
 * Types come from `schema.ts`, generated from `apps/api/openapi.json`
 * (`pnpm --filter web gen:api`; `gen:api:export` re-exports the OpenAPI first).
 *
 * In the browser every call goes to the same-origin proxy at `/api/*`
 * (`app/api/[...path]/route.ts`), so the session cookie stays first-party. On the
 * server, calls go straight to `API_BASE_URL`; pass the incoming `cookie` header in
 * `init.headers` when the call needs the user's session.
 *
 * `NEXT_PUBLIC_API_MODE=fixtures` resolves every call from `fixtures.json` (fictional
 * "(fixture)" companies) without touching the network. The fixtures module is loaded
 * with a dynamic import only in that mode.
 */
import type { Activity, ActivityPage } from "@/lib/run/types";
import type { components } from "./schema";
import { showcaseReadPath } from "./showcase-paths";

/* ───────────────────────── Types ───────────────────────── */

export type Schemas = components["schemas"];

export type UserOut = Schemas["UserOut"];
export type LoginIn = Schemas["LoginIn"];

export type ThesisOut = Schemas["ThesisOut"];
export type ThesisSummary = Schemas["ThesisSummary"];
export type CriterionIn = Schemas["CriterionIn"];
export type CriterionOut = Schemas["CriterionOut"];
export type CriterionResultOut = Schemas["CriterionResultOut"];
export type ShortlistItemOut = Schemas["ShortlistItemOut"];

export type InvestorSearchIn = Schemas["InvestorSearchIn"];
export type InvestorSearchOut = Schemas["InvestorSearchOut"];
export type InvestorSearchSummary = Schemas["InvestorSearchSummary"];
export type InvestorEntryOut = Schemas["InvestorEntryOut"];

export type CaseCreate = Schemas["CaseCreate"];
export type CompanyCandidate = Schemas["CompanyCandidateOut"];
export type CompanyLookup = Schemas["CompanyLookupOut"];
export type CaseOut = Schemas["CaseOut"];
export type CaseSummary = Schemas["CaseSummary"];
export type CaseDetail = Schemas["CaseDetail"];
export type CaseCriteriaIn = Schemas["CaseCriteriaIn"];
export type IdentityOut = Schemas["IdentityOut"];
export type ClaimOut = Schemas["ClaimOut"];
export type ClaimStatus = Schemas["ClaimStatus"];
export type Disposition = Schemas["Disposition"];
export type IdentityState = Schemas["IdentityState"];
export type EvidenceOut = Schemas["EvidenceOut"];
export type SourceRef = Schemas["SourceRef"];
export type FactStr = Schemas["FactStr"];
export type AssessmentVersionOut = Schemas["AssessmentVersionOut"];
export type DiffLineOut = Schemas["DiffLineOut"];
export type DocumentOut = Schemas["DocumentOut"];
export type DocumentKind = Schemas["DocumentKind"];
export type DocumentUrlOut = Schemas["DocumentUrlOut"];
export type CaseCostOut = Schemas["CaseCostOut"];

export type RequestListOut = Schemas["RequestListOut"];
export type MessageOut = Schemas["MessageOut"];
export type RevisionIn = Schemas["RevisionIn"];
export type EditIn = Schemas["EditIn"];
export type SendOut = Schemas["SendOut"];
export type SendSummaryOut = Schemas["SendSummaryOut"];

export type RunOut = Schemas["RunOut"];
export type RunQueueOut = Schemas["RunQueueOut"];
export type RunQueueItemOut = Schemas["RunQueueItemOut"];
export type RunQueueStatus = Schemas["RunQueueStatus"];
export type StepOut = Schemas["StepOut"];
export type PolicyOut = Schemas["PolicyOut"];

export type { Activity, ActivityPage };

/**
 * One server-sent event from `GET /runs/{id}/events`, or a polling snapshot.
 * `activity` is one stored fact about what the run did, ordered by `seq`. `live` marks the
 * end of the backlog: everything before it is history and is drawn without animation.
 */
export type RunStreamEvent =
  | { event: "step"; data: StepOut }
  | { event: "run"; data: RunOut }
  | { event: "activity"; data: Activity }
  | { event: "live" };

/* ───────────────────────── Transport ───────────────────────── */

export const isFixtureMode = process.env.NEXT_PUBLIC_API_MODE === "fixtures";

function apiBase(): string {
  if (typeof window !== "undefined") return "/api";
  return (process.env.API_BASE_URL?.trim() || "http://localhost:8000").replace(/\/+$/, "");
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
    readonly path: string,
  ) {
    super(
      `API ${status} on ${path}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
    );
    this.name = "ApiError";
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface CallOptions {
  json?: unknown;
  form?: FormData;
  init?: RequestInit;
}

/* ───────────────────────── Public showcase (read-only) ───────────────────────── */

let publicShowcase = false;

/**
 * Browser only. While on `/showcase/**` the case, run, assessment, thesis and investor
 * reads go to the API's public read-only routes (`/public/showcase/*`), which serve only
 * the flagged showcase records, and every other call is refused here without a request.
 * Server components call the `getShowcase*` functions directly instead.
 */
export function setPublicShowcaseMode(on: boolean): void {
  publicShowcase = on;
}

function showcasePath(method: Method, path: string): string {
  const mapped = showcaseReadPath(method, path);
  if (mapped !== null) return mapped;
  throw new ApiError(403, "This is a read-only showcase. Log in to work on your own cases.", path);
}

async function call<T>(method: Method, path: string, opts: CallOptions = {}): Promise<T> {
  if (publicShowcase && typeof window !== "undefined") path = showcasePath(method, path);
  const headers = new Headers(opts.init?.headers);
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form; // the browser sets the multipart boundary
  } else if (opts.json !== undefined) {
    body = JSON.stringify(opts.json);
    headers.set("content-type", "application/json");
  }
  headers.set("accept", "application/json");

  const response = await fetch(`${apiBase()}${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    ...opts.init,
    method,
    headers,
    body,
  });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail, path);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const enc = encodeURIComponent;

type Fixtures = typeof import("./fixtures");
let fixturesPromise: Promise<Fixtures> | null = null;

/** Loads the fixture module, only ever called in fixture mode. */
function fx(): Promise<Fixtures> {
  fixturesPromise ??= import("./fixtures");
  return fixturesPromise;
}

/* ───────────────────────── Auth ───────────────────────── */

export async function login(body: LoginIn): Promise<UserOut> {
  if (isFixtureMode) return (await fx()).login(body);
  return call("POST", "/auth/login", { json: body });
}

export async function logout(): Promise<void> {
  if (isFixtureMode) return;
  return call("POST", "/auth/logout");
}

export async function me(init?: RequestInit): Promise<UserOut> {
  if (isFixtureMode) return (await fx()).me();
  return call("GET", "/auth/me", { init });
}

/* ───────────────────────── Discover ───────────────────────── */

export async function createThesis(text: string): Promise<ThesisOut> {
  if (isFixtureMode) return (await fx()).createThesis(text);
  return call("POST", "/theses", { json: { text } });
}

export async function listTheses(init?: RequestInit): Promise<ThesisSummary[]> {
  if (isFixtureMode) return (await fx()).listTheses();
  return call("GET", "/theses", { init });
}

export async function getThesis(id: string, init?: RequestInit): Promise<ThesisOut> {
  if (isFixtureMode) return (await fx()).getThesis(id);
  return call("GET", `/theses/${enc(id)}`, { init });
}

export async function updateCriteria(id: string, criteria: CriterionIn[]): Promise<ThesisOut> {
  if (isFixtureMode) return (await fx()).updateCriteria(id, criteria);
  return call("PUT", `/theses/${enc(id)}/criteria`, { json: criteria });
}

export async function startSearch(id: string): Promise<RunOut> {
  if (isFixtureMode) return (await fx()).startSearch(id);
  return call("POST", `/theses/${enc(id)}/search`);
}

/* ───────────────────────── Investors ───────────────────────── */

export async function createInvestorSearch(body: InvestorSearchIn): Promise<InvestorSearchOut> {
  if (isFixtureMode) return (await fx()).createInvestorSearch(body);
  return call("POST", "/investor-searches", { json: body });
}

export async function listInvestorSearches(init?: RequestInit): Promise<InvestorSearchSummary[]> {
  if (isFixtureMode) return (await fx()).listInvestorSearches();
  return call("GET", "/investor-searches", { init });
}

export async function getInvestorSearch(id: string, init?: RequestInit): Promise<InvestorSearchOut> {
  if (isFixtureMode) return (await fx()).getInvestorSearch(id);
  return call("GET", `/investor-searches/${enc(id)}`, { init });
}

/* ───────────────────────── Cases ───────────────────────── */

export async function createCase(body: CaseCreate): Promise<CaseOut> {
  if (isFixtureMode) return (await fx()).createCase(body);
  return call("POST", "/cases", { json: body });
}

export async function lookupCompanies(q: string): Promise<CompanyLookup> {
  return call("GET", `/companies/lookup?q=${encodeURIComponent(q)}`);
}

export async function listCases(init?: RequestInit): Promise<CaseSummary[]> {
  if (isFixtureMode) return (await fx()).listCases();
  return call("GET", "/cases", { init });
}

export async function getCase(id: string, init?: RequestInit): Promise<CaseDetail> {
  if (isFixtureMode) return (await fx()).getCase(id);
  return call("GET", `/cases/${enc(id)}`, { init });
}

export async function pickIdentity(caseId: string, crustdataCompanyId: number): Promise<CaseOut> {
  if (isFixtureMode) return (await fx()).caseOut(caseId);
  return call("POST", `/cases/${enc(caseId)}/identity`, {
    json: { crustdata_company_id: crustdataCompanyId },
  });
}

export async function startVerify(caseId: string): Promise<RunOut> {
  if (isFixtureMode) return (await fx()).startVerify(caseId);
  return call("POST", `/cases/${enc(caseId)}/verify`);
}

/** Check one claim again (its row's "Run check"), then re-assess the case. */
export async function checkClaim(caseId: string, claimId: string): Promise<RunOut> {
  if (isFixtureMode) return (await fx()).startVerify(caseId);
  return call("POST", `/cases/${enc(caseId)}/claims/${enc(claimId)}/check`);
}

export async function setCaseCriteria(caseId: string, body: CaseCriteriaIn): Promise<CaseOut> {
  if (isFixtureMode) return (await fx()).caseOut(caseId);
  return call("PUT", `/cases/${enc(caseId)}/criteria`, { json: body });
}

export async function listAssessments(
  caseId: string,
  init?: RequestInit,
): Promise<AssessmentVersionOut[]> {
  if (isFixtureMode) return (await fx()).listAssessments(caseId);
  return call("GET", `/cases/${enc(caseId)}/assessments`, { init });
}

/* ───────────────────────── Claims and documents ───────────────────────── */

export async function addClaim(caseId: string, text: string): Promise<ClaimOut> {
  if (isFixtureMode) return (await fx()).addClaim(caseId, text);
  return call("POST", `/cases/${enc(caseId)}/claims`, { json: { text } });
}

export async function uploadDocument(
  caseId: string,
  file: File,
  kind: DocumentKind,
  answersRequestItemIds: string[] = [],
): Promise<DocumentOut> {
  if (isFixtureMode) return (await fx()).uploadDocument(caseId, kind);
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  for (const id of answersRequestItemIds) form.append("answers_request_item_ids", id);
  return call("POST", `/cases/${enc(caseId)}/documents`, { form });
}

export async function getDocumentUrl(documentId: string): Promise<DocumentUrlOut> {
  if (isFixtureMode) return (await fx()).getDocumentUrl(documentId);
  return call("GET", `/documents/${enc(documentId)}/url`);
}

/* ───────────────────────── Act ───────────────────────── */

/** Build the request list and the drafted seller email from the latest assessment. */
export async function createRequestList(caseId: string): Promise<RequestListOut> {
  if (isFixtureMode) return (await fx()).getRequestList(caseId);
  return call("POST", `/cases/${enc(caseId)}/requests`);
}

export async function getRequestList(caseId: string, init?: RequestInit): Promise<RequestListOut> {
  if (isFixtureMode) return (await fx()).getRequestList(caseId);
  return call("GET", `/cases/${enc(caseId)}/requests`, { init });
}

/** Turn the (edited) draft into message revision 1. */
export async function createMessage(caseId: string, body: RevisionIn): Promise<MessageOut> {
  if (isFixtureMode) return (await fx()).message("draft", body);
  return call("POST", `/cases/${enc(caseId)}/messages`, { json: body });
}

export async function getMessage(
  caseId: string,
  messageId: string,
  init?: RequestInit,
): Promise<MessageOut> {
  if (isFixtureMode) return (await fx()).message();
  return call("GET", `/cases/${enc(caseId)}/messages/${enc(messageId)}`, { init });
}

/** Any edit creates a new immutable revision and clears approval. */
export async function editMessage(
  caseId: string,
  messageId: string,
  body: EditIn,
): Promise<MessageOut> {
  if (isFixtureMode) return (await fx()).message("edited", body);
  return call("POST", `/cases/${enc(caseId)}/messages/${enc(messageId)}/revisions`, {
    json: body,
  });
}

/** Approve one exact revision as the signed-in user. */
export async function approveMessage(
  caseId: string,
  messageId: string,
  revisionId: string,
): Promise<MessageOut> {
  if (isFixtureMode) return (await fx()).message("approved");
  return call("POST", `/cases/${enc(caseId)}/messages/${enc(messageId)}/approve`, {
    json: { revision_id: revisionId },
  });
}

/** Send the approved revision once. A 409 `send_exists` carries the existing send. */
export async function sendMessage(
  caseId: string,
  messageId: string,
  /**
   * What the person confirmed: the exact approved revision, and whether the screen told
   * them a real email leaves. The API answers 409 `stale_revision` or
   * `delivery_mode_changed` when either no longer holds, and sends nothing.
   */
  confirmed: Schemas["SendIn"],
): Promise<SendOut> {
  if (isFixtureMode) return (await fx()).sendMessage();
  return call("POST", `/cases/${enc(caseId)}/messages/${enc(messageId)}/send`, {
    json: confirmed,
  });
}

/** The `code` of a 409 from the API ("stale_revision", "send_exists"), or null. */
export function conflictCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const detail = error.detail;
  if (detail && typeof detail === "object" && "code" in detail) {
    const code = (detail as { code: unknown }).code;
    return typeof code === "string" ? code : null;
  }
  return null;
}

/** Resolve an `unknown` send with the provider; never dispatches again. */
export async function reconcileMessage(caseId: string, messageId: string): Promise<SendOut> {
  if (isFixtureMode) return (await fx()).sendMessage();
  return call("POST", `/cases/${enc(caseId)}/messages/${enc(messageId)}/reconcile`);
}

export async function getSendSummary(caseId: string): Promise<SendSummaryOut> {
  if (isFixtureMode) return (await fx()).sendSummary();
  return call("GET", `/cases/${enc(caseId)}/messages/send-summary`);
}

/* ───────────────────────── Runs ───────────────────────── */

export async function getRun(id: string, init?: RequestInit): Promise<RunOut> {
  if (isFixtureMode) return (await fx()).getRun(id);
  return call("GET", `/runs/${enc(id)}`, { init });
}

/** The workspace's jobs: `active` (queued or working) or `recent` (latest of any state). */
export async function listRuns(
  status: RunQueueStatus = "active",
  limit = 20,
  init?: RequestInit,
): Promise<RunQueueOut> {
  if (isFixtureMode) return (await fx()).listRuns(status, limit);
  return call("GET", `/runs?status=${status}&limit=${limit}`, { init });
}

export async function resumeRun(id: string): Promise<RunOut> {
  if (isFixtureMode) return (await fx()).getRun(id);
  return call("POST", `/runs/${enc(id)}/resume`);
}

/**
 * One page of a run's stored activity, oldest first. An API that predates the activity
 * feature answers 404; that reads as "nothing recorded", not as an error.
 */
export async function listRunActivity(
  id: string,
  after = 0,
  init?: RequestInit,
): Promise<ActivityPage> {
  if (isFixtureMode) return (await fx()).listRunActivity(id, after);
  try {
    return await call("GET", `/runs/${enc(id)}/activity?after=${after}&limit=500`, { init });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { items: [], next_after: null };
    throw error;
  }
}

/** Every stored activity of a run, following `next_after` to the end. */
export async function listAllRunActivity(id: string): Promise<Activity[]> {
  const all: Activity[] = [];
  let after = 0;
  // 2,000 events is the server's cap per run; ten pages is past it.
  for (let page = 0; page < 10; page += 1) {
    const { items, next_after } = await listRunActivity(id, after);
    all.push(...items);
    if (next_after === null || items.length === 0) break;
    after = next_after;
  }
  return all;
}

const POLL_MS = 2000;
const SSE_RECONNECTS = 3;
const isTerminal = (run: RunOut) => run.state === "done" || run.state === "failed";

/**
 * Follow a run. Uses server-sent events through the proxy and falls back to polling
 * `GET /runs/{id}` and `GET /runs/{id}/activity` every 2 s if the stream fails. Polling
 * emits `run` events that include every step. Returns an unsubscribe function. Browser only.
 *
 * `after` is the last activity `seq` the caller already holds; the stream resumes from it.
 */
export function subscribeRun(
  runId: string,
  onEvent: (event: RunStreamEvent) => void,
  after = 0,
): () => void {
  let stopped = false;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastSeq = after;
  let live = false;
  let finished = false;
  // Aborts every request still in flight when the caller unsubscribes.
  const aborter = new AbortController();
  const stop = () => {
    stopped = true;
    source?.close();
    if (timer) clearTimeout(timer);
    timer = null;
    aborter.abort();
  };

  if (isFixtureMode) {
    void fx().then((f) => {
      if (!stopped) f.replayRun(runId, onEvent, () => stopped);
    });
    return stop;
  }

  const emitActivity = (activity: Activity) => {
    if (activity.seq <= lastSeq) return;
    lastSeq = activity.seq;
    onEvent({ event: "activity", data: activity });
  };
  const goLive = () => {
    if (live) return;
    live = true;
    onEvent({ event: "live" });
  };

  const poll = async () => {
    if (stopped) return;
    const init = { signal: aborter.signal };
    try {
      // The run first, then its activity: a run seen finished has all of its activity
      // written by the time the page is read.
      const run = await getRun(runId, init);
      if (stopped) return;
      const page = await listRunActivity(runId, lastSeq, init).catch(() => null);
      if (stopped) return;
      for (const activity of page?.items ?? []) emitActivity(activity);
      const lastPage = page !== null && page.next_after === null;
      // The first poll is the backlog; what later polls bring is new.
      if (lastPage) goLive();
      onEvent({ event: "run", data: run });
      // Only once the final page of a finished run has been read: a failed page read
      // polls again rather than dropping the activity after it.
      if (isTerminal(run) && lastPage) return stop();
    } catch {
      /* keep polling through transient errors */
    }
    if (stopped) return;
    timer = setTimeout(poll, POLL_MS);
  };

  if (typeof EventSource === "undefined") {
    void poll();
    return stop;
  }

  // A dropped stream reconnects from the last activity seen (`?after=`, the same as
  // `Last-Event-ID`); the server re-sends the run and every step, so nothing is missed.
  // After a few failed reconnects it falls back to polling.
  let reconnects = 0;
  const connect = () => {
    if (stopped) return;
    const query = lastSeq > 0 ? `?after=${lastSeq}` : "";
    const es = new EventSource(`/api/runs/${enc(runId)}/events${query}`);
    source = es;
    es.addEventListener("step", (e) => {
      onEvent({ event: "step", data: JSON.parse((e as MessageEvent<string>).data) as StepOut });
    });
    es.addEventListener("activity", (e) => {
      emitActivity(JSON.parse((e as MessageEvent<string>).data) as Activity);
    });
    // The server marks the end of the backlog with a `: live` comment, which EventSource
    // does not surface. A named `live` event is honoured if one is ever sent; otherwise the
    // run feed tells backlog from live by each event's own age.
    es.addEventListener("live", goLive);
    es.addEventListener("run", (e) => {
      reconnects = 0;
      const run = JSON.parse((e as MessageEvent<string>).data) as RunOut;
      onEvent({ event: "run", data: run });
      // Not a reason to close: on a reconnect the finished run comes before the backlog.
      if (isTerminal(run)) finished = true;
    });
    // The server's last frame, after the backlog and the final run: nothing more follows.
    es.addEventListener("end", stop);
    es.onerror = () => {
      if (stopped) return;
      es.close();
      source = null;
      // A finished run whose stream closed without `end` (an older server): read what is
      // left by polling, which stops after the final page.
      if (finished) {
        void poll();
      } else if (reconnects < SSE_RECONNECTS) {
        timer = setTimeout(connect, 1000 * 2 ** reconnects);
        reconnects += 1;
      } else {
        void poll();
      }
    };
  };
  connect();
  return stop;
}

/* ───────────────────────── Policy ───────────────────────── */

export async function getPolicy(init?: RequestInit): Promise<PolicyOut> {
  if (isFixtureMode) return (await fx()).getPolicy();
  return call("GET", "/policy", { init });
}

/* ───────────────────────── Public showcase reads ───────────────────────── */

export interface ShowcaseOut {
  company_name: string | null;
  website: string | null;
  case_id: string | null;
  thesis_id: string | null;
  investor_search_id: string | null;
  run_ids: string[];
  provenance: string;
}

/** The flagged showcase records (no session needed). */
export async function getShowcase(init?: RequestInit): Promise<ShowcaseOut> {
  return call("GET", "/public/showcase", { init });
}

export async function getShowcaseCase(init?: RequestInit): Promise<CaseDetail> {
  return call("GET", "/public/showcase/case", { init });
}

export async function getShowcaseDiscovery(init?: RequestInit): Promise<ThesisOut> {
  return call("GET", "/public/showcase/discovery", { init });
}

export async function getShowcaseInvestors(init?: RequestInit): Promise<InvestorSearchOut> {
  return call("GET", "/public/showcase/investors", { init });
}
