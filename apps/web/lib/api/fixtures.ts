/**
 * Fixture mode for `client.ts` (`NEXT_PUBLIC_API_MODE=fixtures`).
 *
 * The data in `fixtures.json` is produced by the API's own fixtures
 * (`uv run python -m app.api.export_openapi`) and validated there against the response
 * schemas, so it always matches the contract. Every company and investor in it is
 * fictional and named "… (fixture)". Never imported outside fixture mode.
 */
import data from "./fixtures.json";
import type {
  AssessmentVersionOut,
  CaseCreate,
  CaseDetail,
  CaseOut,
  CaseSummary,
  CriterionIn,
  DocumentKind,
  DocumentOut,
  DocumentUrlOut,
  InvestorSearchIn,
  InvestorSearchOut,
  InvestorSearchSummary,
  LoginIn,
  MessageOut,
  PolicyOut,
  RequestListOut,
  RunOut,
  RunQueueOut,
  RunStreamEvent,
  SendOut,
  SendSummaryOut,
  ThesisOut,
  ThesisSummary,
  UserOut,
  ClaimOut,
  WorkspaceMessageOut,
  WorkspaceOut,
} from "./client";
import { ApiError } from "./client";
import type { Activity, ActivityPage } from "@/lib/run/types";

interface FixtureData {
  me: UserOut;
  theses: ThesisSummary[];
  thesis: ThesisOut;
  investorSearches: InvestorSearchSummary[];
  investorSearch: InvestorSearchOut;
  cases: CaseSummary[];
  caseDetails: Record<string, CaseDetail>;
  workspace: WorkspaceOut;
  assessments: Record<string, AssessmentVersionOut[]>;
  runs: Record<string, RunOut>;
  runQueue: Record<"active" | "recent", RunQueueOut>;
  requestList: RequestListOut;
  message: Record<"draft" | "edited" | "approved" | "suppressed", MessageOut>;
  documents: DocumentOut[];
  policy: PolicyOut;
  /** Recorded activity per run, from the API's fixtures. A run without one has steps only. */
  activity?: Record<string, Activity[]>;
}

const fixtures = data as unknown as FixtureData;
const PRIMARY_CASE_ID = fixtures.cases[0].id;

/**
 * What the person did in this browser session. Fixture results are a fixed example, but
 * the words they typed (a thesis, criteria, an investor profile, a message draft) are
 * kept and shown back, so the flow reads the way it will against the real service. The
 * screens say that the results themselves are an example.
 */
const session: {
  thesisText: string | null;
  criteria: ThesisOut["criteria"] | null;
  investorProfile: InvestorSearchIn | null;
  /** Where the seller request stands. It starts with no message, so it can be drafted, approved and sent once. */
  message: keyof FixtureData["message"] | null;
  typed: { recipient: string; subject: string; body: string } | null;
} = { thesisText: null, criteria: null, investorProfile: null, message: null, typed: null };

/** Deep copy, so callers can mutate results freely. */
const clone = <T>(value: T): T => structuredClone(value);
const delay = (ms = 250) => new Promise((resolve) => setTimeout(resolve, ms));

function notFound(what: string): never {
  throw new ApiError(404, `${what} not found.`, "fixtures");
}

function lookup<T>(table: Record<string, T>, id: string, what: string): T {
  const value = table[id];
  if (value === undefined) notFound(what);
  return clone(value);
}

export async function login(body: LoginIn): Promise<UserOut> {
  await delay();
  return { ...clone(fixtures.me), email: body.email };
}

export const me = async () => clone(fixtures.me);

export async function createThesis(text: string): Promise<ThesisOut> {
  await delay(600);
  session.thesisText = text;
  session.criteria = null;
  return { ...clone(fixtures.thesis), text, status: "draft", run: null, shortlist: [] };
}

export const listTheses = async () =>
  clone(fixtures.theses).map((thesis) =>
    thesis.id === fixtures.thesis.id && session.thesisText
      ? { ...thesis, text: session.thesisText, criteria_count: session.criteria?.length ?? thesis.criteria_count }
      : thesis,
  );

export async function getThesis(id: string): Promise<ThesisOut> {
  if (id !== fixtures.thesis.id) notFound("Thesis");
  const thesis = clone(fixtures.thesis);
  if (session.thesisText) thesis.text = session.thesisText;
  if (session.criteria) thesis.criteria = clone(session.criteria);
  return thesis;
}

export async function updateCriteria(id: string, criteria: CriterionIn[]): Promise<ThesisOut> {
  const thesis = await getThesis(id);
  thesis.criteria = criteria.map((c, position) => ({
    ...c,
    id: c.id ?? `fx-crit-new-${position}`,
    position,
    crustdata_filter: c.crustdata_filter ?? null,
    assessed_from_evidence: !c.crustdata_filter,
    edited: true,
  }));
  session.criteria = clone(thesis.criteria);
  return thesis;
}

export async function startSearch(id: string): Promise<RunOut> {
  const thesis = await getThesis(id);
  return clone(thesis.run ?? notFound("Run"));
}

export async function createInvestorSearch(profile: InvestorSearchIn): Promise<InvestorSearchOut> {
  await delay();
  session.investorProfile = profile;
  return { ...clone(fixtures.investorSearch), profile };
}

export const listInvestorSearches = async () =>
  clone(fixtures.investorSearches).map((search) =>
    search.id === fixtures.investorSearch.id && session.investorProfile
      ? {
          ...search,
          sector: session.investorProfile.sector,
          location: session.investorProfile.location,
          stage: session.investorProfile.stage,
        }
      : search,
  );

export async function getInvestorSearch(id: string): Promise<InvestorSearchOut> {
  if (id !== fixtures.investorSearch.id) notFound("Investor search");
  const search = clone(fixtures.investorSearch);
  if (session.investorProfile) search.profile = { ...session.investorProfile };
  return search;
}

export async function caseOut(id: string): Promise<CaseOut> {
  return lookup(fixtures.caseDetails, id, "Case").case;
}

export async function createCase(body: CaseCreate): Promise<CaseOut> {
  void body;
  await delay();
  return caseOut(PRIMARY_CASE_ID);
}

export const listCases = async () => clone(fixtures.cases);

/** The fixture message in its current state, carrying what the person typed. */
function currentMessage(): MessageOut | null {
  if (!session.message) return null;
  const message = clone(fixtures.message[session.message]);
  if (session.typed) {
    const current = { ...message.current_revision, ...session.typed };
    message.current_revision = current;
    message.revisions = message.revisions.map((revision) =>
      revision.id === current.id ? current : revision,
    );
  }
  return message;
}

export async function getCase(id: string): Promise<CaseDetail> {
  const detail = lookup(fixtures.caseDetails, id, "Case");
  // The request on the primary case follows this session: it starts undrafted.
  if (id === PRIMARY_CASE_ID && detail.request_list) {
    detail.message = currentMessage();
    detail.request_list.message_id = detail.message?.id ?? null;
  }
  return detail;
}

/** The workspace read, with the primary case's request following this session as `getCase` does. */
export async function getWorkspace(): Promise<WorkspaceOut> {
  const workspace = clone(fixtures.workspace);
  const primary = workspace.records.find((record) => record.case_id === PRIMARY_CASE_ID);
  const detail = await getCase(PRIMARY_CASE_ID);
  if (primary && detail.request_list) primary.message = messageRecord(detail.message);
  return workspace;
}

/** `MessageOut` as `GET /workspace` carries it: no revision history, no email text. */
function messageRecord(message: MessageOut | null): WorkspaceMessageOut | null {
  if (!message) return null;
  const { number, recipient, entered_by_user_id, created_at } = message.current_revision;
  return {
    status: message.status,
    current_revision: { number, recipient, entered_by_user_id, created_at },
    approval: message.approval,
    send: message.send,
  };
}

export async function startVerify(caseId: string): Promise<RunOut> {
  const run = (await caseOut(caseId)).run;
  return clone(run ?? notFound("Run"));
}

export const listAssessments = async (caseId: string) =>
  lookup(fixtures.assessments, caseId, "Case");

export async function addClaim(caseId: string, text: string): Promise<ClaimOut> {
  await caseOut(caseId);
  // Shape template: the typed, not-yet-checked claim on the ambiguous fixture case.
  const template = Object.values(fixtures.caseDetails)
    .flatMap((d) => d.claims)
    .find((c) => c.origin === "typed");
  if (!template) notFound("Claim template");
  return {
    ...clone(template),
    id: "fx-claim-typed",
    number: 99,
    original_text: text,
    normalised_text: text,
    category: "other",
    stated_in: { ...template.stated_in, typed_at: new Date().toISOString() },
    reason: "Queued; the check has not run yet",
    not_checked_reason: null,
    history: [],
  };
}

export async function uploadDocument(caseId: string, kind: DocumentKind): Promise<DocumentOut> {
  await caseOut(caseId);
  await delay(800);
  const doc = fixtures.documents.find((d) => d.kind === kind) ?? fixtures.documents[0];
  return clone(doc);
}

export async function getDocumentUrl(documentId: string): Promise<DocumentUrlOut> {
  if (!fixtures.documents.some((d) => d.id === documentId)) notFound("Document");
  return {
    url: `https://storage.example/fixture/${documentId}`,
    expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
  };
}

export async function getRequestList(caseId: string): Promise<RequestListOut> {
  if (caseId !== fixtures.requestList.case_id) notFound("Request list");
  return clone(fixtures.requestList);
}

/** Moves the fixture message to a state, keeping what was typed. Reading passes no state. */
export async function message(
  state?: keyof FixtureData["message"],
  typed?: { recipient: string; subject: string; body: string },
): Promise<MessageOut> {
  if (state) session.message = state;
  if (typed) session.typed = { recipient: typed.recipient, subject: typed.subject, body: typed.body };
  return currentMessage() ?? clone(fixtures.message.draft);
}

export async function sendMessage(): Promise<SendOut> {
  await delay(500);
  session.message = "suppressed";
  return clone(fixtures.message.suppressed.send ?? notFound("Send"));
}

export const sendSummary = async (): Promise<SendSummaryOut> => ({
  sent: 0,
  suppressed_test_mode: session.message === "suppressed" ? 1 : 0,
  failed: 0,
  unknown: 0,
  sending: 0,
});

export const getRun = async (id: string) => lookup(fixtures.runs, id, "Run");

/**
 * Adds a run and its recorded activity to the fixture tables, so a screen that keeps its
 * own fixtures (the personalised home) can be followed and replayed like any other run.
 */
export function registerRun(run: RunOut, activities: Activity[]): void {
  fixtures.runs[run.id] = clone(run);
  (fixtures.activity ??= {})[run.id] = clone(activities);
}

/** The fixture investors, for screens that list funds outside an investor search. */
export const investorEntries = () => clone(fixtures.investorSearch.entries);

/** The jobs queue. The in-flight example is re-clocked to have started 75 s ago. */
export async function listRuns(status: "active" | "recent", limit: number): Promise<RunQueueOut> {
  const queue = clone(fixtures.runQueue[status]);
  const started = Date.now() - 75_000;
  for (const item of queue.items) {
    if (item.state !== "running" && item.state !== "pending") continue;
    item.created_at = new Date(started).toISOString();
    item.started_at = item.created_at;
    item.updated_at = new Date().toISOString();
  }
  queue.items = queue.items.slice(0, limit);
  return queue;
}

export const getPolicy = async () => clone(fixtures.policy);

/** The recorded activity of a fixture run, oldest first, with its recorded times. */
export function fixtureActivities(runId: string): Activity[] {
  return fixtures.activity?.[runId] ?? [];
}

export async function listRunActivity(runId: string, after = 0): Promise<ActivityPage> {
  if (!fixtures.runs[runId]) notFound("Run");
  return { items: clone(fixtureActivities(runId).filter((e) => e.seq > after)), next_after: null };
}

/** The longest a replayed fixture run waits between two events. */
const MAX_GAP_MS = 600;
const ZERO_COST = {
  crustdata_credits: 0,
  llm_usd: 0,
  input_tokens: 0,
  output_tokens: 0,
  unknown_cost_calls: 0,
};

/**
 * Replay a fixture run the way the SSE stream would: the run starts, each step goes
 * running, emits its recorded activity and settles, then a final `run` event. Gaps keep
 * their recorded proportions, compressed to 600 ms at most. Activity is stamped with the
 * time it is replayed, so "read 2 s ago" is true on screen.
 */
export function replayRun(
  runId: string,
  onEvent: (event: RunStreamEvent) => void,
  isStopped: () => boolean,
): void {
  const run = fixtures.runs[runId];
  if (!run) return;
  const activities = fixtureActivities(runId);
  const timeline: { wait: number; event: () => RunStreamEvent }[] = [
    {
      wait: 0,
      event: () => ({
        event: "run",
        data: { ...clone(run), state: "running", steps: [], cost: { ...ZERO_COST }, finished_at: null },
      }),
    },
    { wait: 0, event: () => ({ event: "live" }) },
  ];
  // Every step is listed as pending first: the plan exists before the work does.
  for (const step of run.steps) {
    timeline.push({
      wait: 0,
      event: () => ({
        event: "step",
        data: { ...clone(step), state: "pending", result: null, detail: null, cost: { ...ZERO_COST } },
      }),
    });
  }
  let previousAt: number | null = null;
  for (const step of [...run.steps].sort((a, b) => a.position - b.position)) {
    const own = activities.filter((activity) => activity.step_id === step.id);
    timeline.push({
      wait: 350,
      event: () => ({
        event: "step",
        data: { ...clone(step), state: "running", result: null, cost: { ...ZERO_COST } },
      }),
    });
    for (const activity of own) {
      const at = Date.parse(activity.at);
      const gap: number = previousAt === null ? 300 : at - previousAt;
      previousAt = at;
      timeline.push({
        wait: Math.min(MAX_GAP_MS, Math.max(120, gap / 3)),
        event: () => ({
          event: "activity",
          data: { ...clone(activity), at: new Date().toISOString() },
        }),
      });
    }
    timeline.push({ wait: 400, event: () => ({ event: "step", data: clone(step) }) });
  }
  timeline.push({ wait: 500, event: () => ({ event: "run", data: { ...clone(run), steps: [] } }) });

  const next = (index: number) => {
    if (isStopped() || index >= timeline.length) return;
    const { wait, event } = timeline[index];
    setTimeout(() => {
      if (isStopped()) return;
      onEvent(event());
      next(index + 1);
    }, wait);
  };
  next(0);
}
