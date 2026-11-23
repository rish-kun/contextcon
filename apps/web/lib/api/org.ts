/**
 * Sign-up, the organisation profile, its auto-research run and the personalised home.
 *
 *   POST /auth/signup         → SignupOut
 *   GET  /profile             → OrgProfile | 404
 *   PUT  /profile             → OrgProfile
 *   POST /profile/autofill    → AutofillOut
 *   POST /profile/research    → ResearchStart
 *   GET  /home                → HomeOut   (docs/design/iterations/I-auto-research-home.md §4.2)
 *
 * The shapes below are written by hand from that document, because these routes are
 * not in `schema.ts` yet. When they are, replace each interface with its
 * `Schemas["…"]` alias and delete the hand-written one; the callers read these names only.
 * `NEXT_PUBLIC_API_MODE=fixtures` resolves every call from `org-fixtures.ts`.
 */
import {
  ApiError,
  isFixtureMode,
  type CaseOut,
  type Disposition,
  type InvestorEntryOut,
  type RunOut,
  type SignupIn as ApiSignupIn,
  type SourceRef,
  type VerificationSentOut,
} from "./client";

/* ───────────────────────── Types ───────────────────────── */

/** `company_url` is a honeypot: a person never fills it. */
export type SignupIn = ApiSignupIn;

/**
 * Always `verification_sent`, whether or not the email already had an account: the
 * person confirms their email from the link before they can sign in.
 */
export type SignupOut = VerificationSentOut;

export type OrgGoal = "acquire" | "raise" | "both";

/** One value on the profile, with where it came from. Sourced or stated, never both. */
export interface ProfileField {
  key: string;
  label: string;
  value: string | null;
  /** The record it was read from. Null when the person typed it or the record lacks it. */
  source: SourceRef | null;
  /** Date of the underlying fact. */
  as_of: string | null;
  stated_by_user: boolean;
  /** An inferred figure, such as a headcount from professional profiles. */
  estimate_basis: string | null;
}

export interface OrgProfile {
  org_name: string;
  website: string | null;
  goal: OrgGoal | null;
  /** "corporate_development", "startup", "ma_advisory", … */
  org_kind: string | null;
  fields: ProfileField[];
  /** Acquirers: the size of deal looked for, in US dollars. */
  deal_size_usd: number | null;
  /** Businesses raising: the amount sought, in US dollars. */
  funding_sought_usd: number | null;
  /** "What we want", in the person's words. */
  wants: string | null;
  /** True once the last onboarding step was finished or the setup was skipped. */
  onboarded: boolean;
  version: number;
  updated_at: string;
}

export type OrgProfileIn = Partial<
  Pick<
    OrgProfile,
    "org_name" | "website" | "goal" | "org_kind" | "fields" | "deal_size_usd" | "funding_sought_usd" | "wants" | "onboarded"
  >
>;

export interface AutofillOut {
  /** `failed`: the lookup did not run or the source did not answer. Not "no data". */
  match: "single" | "none" | "failed";
  company_name: string | null;
  domain: string | null;
  fields: ProfileField[];
  retrieved_at: string | null;
  /** Why nothing was pre-filled, in plain words. */
  reason: string | null;
}

/* ───────────────────────── GET /home (iteration I §4.2) ───────────────────────── */

/**
 * One displayed value. A `record` fact carries its source and the date it was true; a
 * `stated` fact carries the date the person confirmed it. Nothing is shown without one.
 */
export interface Fact {
  value: string | number | null;
  origin?: "record" | "stated";
  source?: SourceRef | null;
  as_of?: string | null;
  confirmed_at?: string | null;
  is_estimate?: boolean;
}

export interface HomeKpi {
  key: string;
  label: string;
  fact: Fact;
  /** A second line under the figure: "3 Jun 2025", "2 rounds". */
  sub?: string | null;
  /** A dated series behind the figure. Null when the record holds none. */
  series?: { at: string; value: number }[] | null;
}

export interface HomeCompany {
  name: Fact;
  domain: string | null;
  one_line: Fact | null;
  kpis: HomeKpi[];
  /** Keys the record does not hold: "revenue_band". */
  absent: string[];
  /** False until the person has confirmed the looked-up record. */
  confirmed?: boolean;
}

export type ResearchMode = "acquire" | "raise" | "both";
export type ResearchStatus = "deriving" | "searching" | "finishing" | "ready" | "partial" | "failed";

export interface ResearchAngle {
  key: string;
  label: string;
  basis: Fact[];
  thesis_id: string | null;
}

export interface NotUsed {
  scope: "acquire" | "raise";
  code: string;
  text: string;
}

export interface HomeResearch {
  id: string;
  mode: ResearchMode;
  status: ResearchStatus;
  stale: { is_stale: boolean; changed_fields: string[]; age_days: number };
  created_at: string;
  finished_at: string | null;
  cost: { credits: number; budget_credits: number; usd: number };
  runs: { research: RunOut | null; discover: RunOut | null; investors: RunOut | null; finish: RunOut | null };
  angles: ResearchAngle[];
  not_used: NotUsed[];
}

export type PartStatus = "absent" | "running" | "ready" | "empty" | "failed";
export type ReasonState = "supported" | "unknown" | "not_applicable";

/** A pair of sourced facts and the rule that relates them. */
export interface Reason {
  kind: string;
  state: ReasonState;
  /** The checked sentence. Null renders the facts alone. */
  text: string | null;
  own?: { label: string; fact: Fact } | null;
  theirs?: { label: string; fact: Fact } | null;
  /** Unknown rows only: the record that would settle it. */
  would_settle?: string | null;
}

export interface ApiAction {
  method: "POST";
  path: string;
  needs_approval?: boolean;
}

export interface TargetItem {
  candidate_id: string;
  crustdata_company_id: number | null;
  name: string;
  domain?: string | null;
  location: Fact | null;
  headcount: Fact | null;
  /** 0 to 100 against the stated criteria. Null when nothing could be assessed. */
  fit: number | null;
  assessable_pct: number;
  headline: string | null;
  reasons: Reason[];
  unknowns: string[];
  case: { id: string; disposition: Disposition | null } | null;
  actions: { verify?: ApiAction };
}

export interface TargetRegion {
  label: string;
  level: "state" | "country" | null;
  count: number;
  is_own: boolean;
}

export interface HomeTargets {
  status: PartStatus;
  thesis_id: string | null;
  total: number;
  reason_kinds: string[];
  regions: TargetRegion[];
  items: TargetItem[];
  /** Empty and failed states: what happened, in the API's words. */
  note?: string | null;
}

export type FundRound = InvestorEntryOut["comparable_rounds"][number] & {
  stage: string | null;
  in_stage_window: boolean;
};

export interface FundItem {
  entry_id: string;
  rank: number;
  investor_name: string;
  investor_key: string;
  comparable_rounds: FundRound[];
  latest_comparable: string | null;
  stage_fit: { in_window: number; of: number };
  cheque_fit: {
    state: ReasonState;
    median_round_usd: number | null;
    disclosed: number;
    of: number;
    note: string;
  };
  /** The own-record round this fund is named on: "Series A, 3 Jun 2025". */
  invested_in_you: string | null;
  headline: string | null;
  reasons: Reason[];
  unknowns: string[];
  actions: { draft_approach?: ApiAction };
}

export interface HomeFunds {
  status: PartStatus;
  investor_search_id: string | null;
  total: number;
  ranking_basis: string;
  scope_note: string | null;
  own_stage: string | null;
  ask_band: string | null;
  timeline: { from: string; to: string } | null;
  items: FundItem[];
  note?: string | null;
}

export interface HomeSignal {
  at: string | null;
  precision: "day" | "month" | "year";
  kind: string;
  company_name: string;
  crustdata_company_id: number | null;
  text: string;
  is_estimate: boolean;
  source: SourceRef;
  /** "fund:<investor_key>" or "target:<candidate_id>" when that row is on the page. */
  on_page: string | null;
}

export interface HomeSignals {
  filter: { sectors: string[]; countries: string[]; months: number };
  items: HomeSignal[];
}

export interface HomeNext {
  kind: "verify_target" | "draft_approach" | "complete_profile" | "rerun" | string;
  label: string;
  sub: string | null;
  action?: ApiAction | null;
  href?: string | null;
}

export interface HomeOut {
  generated_at: string;
  profile_version: number | null;
  /** Null when the workspace has no profile yet. */
  company: HomeCompany | null;
  /** Null when no research has run. */
  research: HomeResearch | null;
  targets: HomeTargets;
  funds: HomeFunds;
  signals: HomeSignals;
  next: HomeNext[];
  work: { cases: number; needs_you: number };
}

/* ───────────────────────── Transport ───────────────────────── */

type Fixtures = typeof import("./org-fixtures");
let fixturesPromise: Promise<Fixtures> | null = null;
const fx = (): Promise<Fixtures> => (fixturesPromise ??= import("./org-fixtures"));

async function request<T>(method: "GET" | "POST" | "PUT", path: string, json?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: json === undefined ? { accept: "application/json" } : { accept: "application/json", "content-type": "application/json" },
    body: json === undefined ? undefined : JSON.stringify(json),
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
  return (await response.json()) as T;
}

export async function signup(body: SignupIn): Promise<SignupOut> {
  if (isFixtureMode) return (await fx()).signup(body);
  return request("POST", "/auth/signup", body);
}

/** The workspace's profile, or null when none has been set up. */
export async function getOrgProfile(): Promise<OrgProfile | null> {
  if (isFixtureMode) return (await fx()).getOrgProfile();
  try {
    return await request("GET", "/profile");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function putOrgProfile(body: OrgProfileIn): Promise<OrgProfile> {
  if (isFixtureMode) return (await fx()).putOrgProfile(body);
  return request("PUT", "/profile", body);
}

export async function autofillOrgProfile(website: string): Promise<AutofillOut> {
  if (isFixtureMode) return (await fx()).autofillOrgProfile(website);
  return request("POST", "/profile/autofill", { website });
}

export interface ResearchStart {
  research: { id: string; mode: ResearchMode; status: ResearchStatus; budget: { credits: number } };
  runs: { research: RunOut | null; discover: RunOut | null; investors: RunOut | null };
}

/** The most a research run may spend, printed before it starts. */
export const RESEARCH_CEILING: Record<ResearchMode, number> = { acquire: 80, raise: 50, both: 120 };

/** Start the research for the saved profile. A 409 means one is already running. */
export async function startOrgResearch(body: { mode?: ResearchMode; trigger?: "onboarding" | "manual" | "retry"; retry_part?: "acquire" | "raise" } = {}): Promise<ResearchStart> {
  if (isFixtureMode) return (await fx()).startOrgResearch(body);
  return request("POST", "/profile/research", body);
}

export async function getHome(): Promise<HomeOut> {
  if (isFixtureMode) return (await fx()).getHome();
  return request("GET", "/home");
}

/** Open a case for a research target. One click: it starts identity and contacts nobody. */
export async function verifyTarget(item: TargetItem): Promise<CaseOut> {
  if (isFixtureMode) return (await fx()).verifyTarget(item);
  if (item.actions.verify) return request("POST", item.actions.verify.path);
  return request("POST", "/cases", { name: item.name, website: item.domain ?? null });
}

/** Create a draft approach in Approvals. Nothing is sent; a named person approves later. */
export async function draftApproach(item: FundItem): Promise<{ id: string } | null> {
  if (isFixtureMode) return (await fx()).draftApproach(item);
  if (!item.actions.draft_approach) return null;
  return request("POST", item.actions.draft_approach.path);
}

/* ───────────────────────── Small readers ───────────────────────── */

export const profileField = (profile: Pick<OrgProfile, "fields"> | null, key: string): ProfileField | null =>
  profile?.fields.find((field) => field.key === key) ?? null;

export const wantsToAcquire = (goal: OrgGoal | null) => goal === "acquire" || goal === "both";
export const wantsToRaise = (goal: OrgGoal | null) => goal === "raise" || goal === "both";
