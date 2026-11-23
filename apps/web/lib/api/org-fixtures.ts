/**
 * Fixture mode for `org.ts` (`NEXT_PUBLIC_API_MODE=fixtures`). Never imported otherwise.
 *
 * Every company and fund here is fictional and named "… (fixture)". What the person
 * types during sign-up and onboarding is kept for the browser tab (sessionStorage) and
 * shown back, so the flow reads the way it will against the real service. The research
 * results are one fixed example and do not change with the profile.
 *
 * Two switches for demos: an email containing "pending" signs up into the test-mode
 * waiting state, and a website containing "nomatch" or "fail" returns those lookup states.
 */
import type { CaseOut, SourceRef } from "./client";
import * as base from "./fixtures";
import type {
  AutofillOut,
  Fact,
  FundItem,
  FundRound,
  HomeOut,
  OrgProfile,
  OrgProfileIn,
  ProfileField,
  ResearchMode,
  ResearchStart,
  SignupIn,
  SignupOut,
  TargetItem,
} from "./org";

const RETRIEVED = "2026-11-22T09:32:00Z";
const STORE_KEY = "dp-fixture-org";

const delay = (ms = 300) => new Promise((resolve) => setTimeout(resolve, ms));

function source(id: string, label: string, source_class: SourceRef["source_class"], endpoint: string): SourceRef {
  return {
    source_id: `fx-src-${id}`,
    provider: source_class === "news" || source_class === "company_announcement" ? "web" : "crustdata",
    label,
    url_or_endpoint: endpoint,
    retrieved_at: RETRIEVED,
    source_class,
    origin_id: null,
  };
}

const PROFILE_SRC = source("own-profile", "Company record", "data_provider", "POST /company/enrich");
const FUNDING_SRC = source("own-funding", "Funding record", "data_provider", "POST /company/enrich#funding");
const PEOPLE_SRC = source("own-people", "Professional profiles", "professional_profile_signal", "POST /company/enrich#headcount");

function field(
  key: string,
  label: string,
  value: string,
  from: SourceRef,
  as_of: string,
  estimate_basis: string | null = null,
): ProfileField {
  return { key, label, value, source: from, as_of, stated_by_user: false, estimate_basis };
}

const RECORD_FIELDS: ProfileField[] = [
  field("sector", "Sector", "Transportation, logistics and storage", PROFILE_SRC, "2026-11"),
  field("hq", "Headquarters", "Mumbai, India", PROFILE_SRC, "2026-11"),
  field("founded", "Founded", "2012", PROFILE_SRC, "2026-11"),
  field("headcount", "Team size", "640", PEOPLE_SRC, "2026-10", "From professional profiles, not a payroll count"),
  field("funding_total", "Funding to date", "$18.5M across 3 rounds", FUNDING_SRC, "2025-03-12"),
  field("stage", "Latest round", "Series B", FUNDING_SRC, "2025-03-12"),
  field(
    "description",
    "What you do",
    "Runs contract warehousing and line-haul freight for enterprise shippers in western India",
    PROFILE_SRC,
    "2026-11",
  ),
];

/* ───────────────────────── Session ───────────────────────── */

interface Session {
  profile: OrgProfile | null;
  researchStartedAt: number | null;
}

function readSession(): Session {
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(STORE_KEY);
      if (raw) return JSON.parse(raw) as Session;
    } catch {
      /* storage blocked: the session lives for this page only */
    }
  }
  return { profile: null, researchStartedAt: null };
}

let session: Session | null = null;
const current = (): Session => (session ??= readSession());

function save(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORE_KEY, JSON.stringify(current()));
  } catch {
    /* storage blocked */
  }
}

/** Demo switch read by the Overview in fixture mode: `/app?home=none|running|ready`. */
export type HomeDemo = "none" | "running" | "ready";
let demo: HomeDemo | null = null;
export function setHomeDemo(value: HomeDemo | null): void {
  demo = value;
}

const EXAMPLE_PROFILE: OrgProfile = {
  org_name: "Tidewater Logistics (fixture)",
  website: "tidewater-logistics.example",
  goal: "both",
  org_kind: "corporate_development",
  fields: RECORD_FIELDS,
  deal_size_usd: 10_000_000,
  funding_sought_usd: 25_000_000,
  wants: "Regional warehousing operators with enterprise customers, and growth investors who know logistics",
  onboarded: true,
  version: 1,
  updated_at: RETRIEVED,
};

/* ───────────────────────── Auth and profile ───────────────────────── */

export async function signup(body: SignupIn): Promise<SignupOut> {
  await delay(500);
  const sent: SignupOut = { status: "verification_sent", email: body.email.trim().toLowerCase() };
  // Like the API: the same answer for a bot (honeypot) or a registered email.
  if (body.company_url || /exists/.test(body.email)) return sent;
  current().profile = {
    ...EXAMPLE_PROFILE,
    org_name: body.organisation || `${body.display_name}'s workspace`,
    website: null,
    goal: null,
    org_kind: null,
    fields: [],
    deal_size_usd: null,
    funding_sought_usd: null,
    wants: null,
    onboarded: false,
    updated_at: new Date().toISOString(),
  };
  current().researchStartedAt = null;
  save();
  return sent;
}

export async function getOrgProfile(): Promise<OrgProfile | null> {
  return structuredClone(current().profile);
}

export async function putOrgProfile(body: OrgProfileIn): Promise<OrgProfile> {
  await delay(200);
  const previous = current().profile ?? { ...EXAMPLE_PROFILE, org_name: "Your organisation", website: null, goal: null, org_kind: null, fields: [], deal_size_usd: null, funding_sought_usd: null, wants: null, onboarded: false, version: 0 };
  current().profile = { ...previous, ...body, version: previous.version + 1, updated_at: new Date().toISOString() };
  save();
  return structuredClone(current().profile as OrgProfile);
}

export async function autofillOrgProfile(website: string): Promise<AutofillOut> {
  await delay(1400);
  const domain = website.replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
  if (/fail/.test(domain)) {
    return { match: "failed", company_name: null, domain, fields: [], retrieved_at: null, reason: "The company data source did not answer" };
  }
  if (/nomatch/.test(domain)) {
    return { match: "none", company_name: null, domain, fields: [], retrieved_at: new Date().toISOString(), reason: null };
  }
  return {
    match: "single",
    company_name: "Tidewater Logistics (fixture)",
    domain,
    fields: structuredClone(RECORD_FIELDS),
    retrieved_at: new Date().toISOString(),
    reason: null,
  };
}

/* ───────────────────────── Research and home ───────────────────────── */

export async function startOrgResearch(body: { mode?: ResearchMode } = {}): Promise<ResearchStart> {
  await delay(300);
  current().researchStartedAt = Date.now();
  save();
  const mode = body.mode ?? "both";
  return {
    research: { id: "fx-research-1", mode, status: "ready", budget: { credits: mode === "both" ? 120 : mode === "acquire" ? 80 : 50 } },
    runs: { research: null, discover: null, investors: null },
  };
}

export async function verifyTarget(item: TargetItem): Promise<CaseOut> {
  return base.createCase({ name: item.name, website: item.domain ?? null });
}

export async function draftApproach(item: FundItem): Promise<{ id: string }> {
  await delay(300);
  return { id: `fx-draft-${item.entry_id}` };
}

const rec = (value: string | number, from: SourceRef, as_of: string, is_estimate = false): Fact => ({
  value,
  origin: "record",
  source: from,
  as_of,
  is_estimate,
});
const stated = (value: string): Fact => ({ value, origin: "stated", confirmed_at: "2026-11-22" });
const ENRICH = (id: string) => source(`fit-${id}`, "Company record", "data_provider", "POST /company/enrich");
const OWN_CATEGORIES = rec("Warehousing and storage; contract logistics", PROFILE_SRC, "2026-11");

function target(
  rank: number,
  id: string,
  name: string,
  place: string,
  people: number,
  fitScore: number | null,
  assessable_pct: number,
  headline: string | null,
  theirs: string,
  unknowns: string[],
  caseRef: TargetItem["case"] = null,
): TargetItem {
  const from = ENRICH(id);
  return {
    candidate_id: `fx-target-${id}`,
    crustdata_company_id: 900100 + rank,
    name: `${name} (fixture)`,
    domain: `${id}.example`,
    location: rec(place, from, "2026-10"),
    headcount: rec(people, PEOPLE_SRC, "2026-10", true),
    fit: fitScore,
    assessable_pct,
    headline,
    reasons:
      fitScore === null
        ? []
        : [
            { kind: "same_activity", state: "supported", text: null, own: { label: "You", fact: OWN_CATEGORIES }, theirs: { label: "Them", fact: rec(theirs, from, "2026-10") } },
            { kind: "size_in_range", state: "supported", text: null, own: { label: "You", fact: stated("Looking for 51 to 500 people") }, theirs: { label: "Them", fact: rec(people, PEOPLE_SRC, "2026-10", true) } },
            { kind: "deal_size", state: "unknown", text: null, would_settle: "No valuation or revenue is on public record. A figure from the seller would settle it" },
          ],
    unknowns,
    case: caseRef,
    actions: {},
  };
}

const TARGETS: TargetItem[] = [
  target(1, "kestrel-supply", "Kestrel Supply Systems", "Pune, Maharashtra", 420, 92, 83, "Same activity: your warehousing and their warehouse software", "Warehouse management software", ["Revenue", "Deal size"]),
  target(2, "harbourline", "Harbourline Warehousing", "Bhiwandi, Maharashtra", 310, 88, 67, "Same activity: contract warehousing near Mumbai", "Contract warehousing for consumer goods", ["Customers", "Deal size"], { id: "fx-case-harbourline", disposition: "investigate_further" }),
  target(3, "coastline-cold", "Coastline Cold Storage", "Chennai, Tamil Nadu", 180, 84, 83, "New region: no Tidewater location in Tamil Nadu", "Temperature-controlled storage", ["Funding", "Deal size"]),
  target(4, "lakshya-freight", "Lakshya Freight Tech", "Bengaluru, Karnataka", 95, 76, 50, "Adjacent: line-haul booking software", "Freight booking software", ["Customers", "Deal size"]),
  target(5, "malabar-bonded", "Malabar Bonded Stores", "Kochi, Kerala", 210, 64, 33, "Same activity: bonded warehousing", "Bonded warehousing", ["Customers", "Funding", "Deal size"]),
];

function fundRound(company_id: number, company: string, round_type: string, date: string, amount_usd: number | null, in_stage_window: boolean): FundRound {
  return {
    company_id,
    company_name: `${company} (fixture)`,
    round_type,
    date,
    amount_usd,
    source: source(`round-${company_id}-${date}`, "Funding record", "data_provider", "POST /company/enrich#funding"),
    evidence_id: `fx-ev-round-${company_id}-${date}`,
    stage: round_type,
    in_stage_window,
  };
}

function fund(rank: number, id: string, name: string, rounds: FundRound[], unknowns: string[]): FundItem {
  const disclosed = rounds.map((r) => r.amount_usd).filter((n): n is number => n !== null).sort((a, b) => a - b);
  const latest = rounds.map((r) => r.date).sort().at(-1) ?? null;
  const inWindow = rounds.filter((r) => r.in_stage_window).length;
  return {
    entry_id: `fx-fund-${id}`,
    rank,
    investor_name: `${name} (fixture)`,
    investor_key: id,
    comparable_rounds: rounds,
    latest_comparable: latest,
    stage_fit: { in_window: inWindow, of: rounds.length },
    cheque_fit: {
      state: disclosed.length >= 2 ? "supported" : "unknown",
      median_round_usd: disclosed.length >= 2 ? disclosed[Math.floor(disclosed.length / 2)] : null,
      disclosed: disclosed.length,
      of: rounds.length,
      note: "Round totals, not this fund's own cheque",
    },
    invested_in_you: null,
    headline: `${rounds.length} comparable ${rounds.length === 1 ? "round" : "rounds"}; ${inWindow} at your stage`,
    reasons: [],
    unknowns,
    actions: {},
  };
}

const FUNDS: FundItem[] = [
  fund(1, "saltmarsh", "Saltmarsh Growth", [
    fundRound(900106, "Strait Fulfilment", "series_b", "2026-01-15", 32_000_000, true),
    fundRound(900120, "Portside Parcel", "series_b", "2024-09-03", 24_000_000, true),
    fundRound(900121, "Anchor Line Haul", "series_a", "2022-06-18", 9_000_000, true),
  ], ["Fund size", "Current mandate"]),
  fund(2, "northgate", "Northgate Ventures", [
    fundRound(900001, "Harbourline Warehousing", "series_a", "2023-11-20", 6_000_000, true),
    fundRound(900002, "Kestrel Supply Systems", "seed", "2025-04-02", null, false),
  ], ["Cheque size unknown for 1 round"]),
  fund(3, "ironbridge", "Ironbridge Capital", [
    fundRound(900122, "Quayside Storage", "growth_equity", "2025-08-21", 40_000_000, true),
    fundRound(900120, "Portside Parcel", "series_a", "2022-11-09", 11_000_000, true),
  ], ["Current mandate"]),
  fund(4, "monsoon", "Monsoon Seed", [fundRound(900125, "Dockhand", "seed", "2024-12-05", null, false)], ["Amount not on record", "Stage focus is earlier than yours"]),
];

const EMPTY_HOME: HomeOut = {
  generated_at: RETRIEVED,
  profile_version: null,
  company: null,
  research: null,
  targets: { status: "absent", thesis_id: null, total: 0, reason_kinds: [], regions: [], items: [] },
  funds: { status: "absent", investor_search_id: null, total: 0, ranking_basis: "", scope_note: null, own_stage: null, ask_band: null, timeline: null, items: [] },
  signals: { filter: { sectors: [], countries: [], months: 12 }, items: [] },
  next: [],
  work: { cases: 0, needs_you: 0 },
};

/** One fixed example. `/app?home=none` shows the page before a profile exists. */
export async function getHome(): Promise<HomeOut> {
  await delay(250);
  if (demo === "none") return structuredClone(EMPTY_HOME);
  return {
    ...structuredClone(EMPTY_HOME),
    profile_version: 3,
    company: {
      name: rec("Tidewater Logistics (fixture)", PROFILE_SRC, "2026-11"),
      domain: "tidewater-logistics.example",
      one_line: rec("Contract warehousing and line-haul freight for enterprise shippers in western India", PROFILE_SRC, "2026-11"),
      kpis: [
        { key: "headcount", label: "People", fact: rec(640, PEOPLE_SRC, "2026-10", true) },
        { key: "founded_year", label: "Founded", fact: rec("2012", PROFILE_SRC, "2026-11") },
        { key: "stage", label: "Stage", fact: rec("Series B", FUNDING_SRC, "2025-03-12"), sub: "12 Mar 2025" },
        { key: "total_funding_usd", label: "Raised", fact: rec("$18.5M", FUNDING_SRC, "2025-03-12"), sub: "3 rounds" },
        { key: "looking_for", label: "Looking for", fact: stated("Warehousing and supply-chain software · India · 51 to 500 people") },
      ],
      absent: ["revenue_band"],
      confirmed: true,
    },
    research: {
      id: "fx-research-1",
      mode: "both",
      status: "ready",
      stale: { is_stale: false, changed_fields: [], age_days: 0 },
      created_at: "2026-11-22T11:12:41Z",
      finished_at: "2026-11-22T11:16:02Z",
      cost: { credits: 63, budget_credits: 120, usd: 0.03 },
      runs: { research: null, discover: null, investors: null, finish: null },
      angles: [
        { key: "adjacent_capability", label: "Adjacent: warehouse and freight software", basis: [OWN_CATEGORIES], thesis_id: "fx-thesis-logistics" },
        { key: "geographic_expansion", label: "New region: Tamil Nadu, Karnataka", basis: [], thesis_id: "fx-thesis-logistics" },
      ],
      not_used: [{ scope: "acquire", code: "no_customer_segment", text: "Your customer segment was not stated" }],
    },
    targets: {
      status: "ready",
      thesis_id: "fx-thesis-logistics",
      total: TARGETS.length,
      reason_kinds: ["same_activity", "size_in_range", "deal_size"],
      regions: [
        { label: "Maharashtra", level: "state", count: 2, is_own: true },
        { label: "Tamil Nadu", level: "state", count: 1, is_own: false },
        { label: "Karnataka", level: "state", count: 1, is_own: false },
        { label: "Kerala", level: "state", count: 1, is_own: false },
      ],
      items: structuredClone(TARGETS),
    },
    funds: {
      status: "ready",
      investor_search_id: "fx-investor-search",
      total: FUNDS.length,
      ranking_basis: "Recency-weighted count of dated rounds in comparable companies",
      scope_note: null,
      own_stage: "series_b",
      ask_band: null,
      timeline: { from: "2022-01-01", to: "2026-11-22" },
      items: structuredClone(FUNDS),
    },
    signals: {
      filter: { sectors: ["Warehousing", "Logistics"], countries: ["India"], months: 12 },
      items: [
        { at: "2026-01-15", precision: "day", kind: "funding_round", company_name: "Strait Fulfilment (fixture)", crustdata_company_id: 900106, text: "Series B recorded, $32.0M", is_estimate: false, source: source("sig-1", "Funding record", "data_provider", "POST /company/enrich#funding"), on_page: "fund:saltmarsh" },
        { at: "2025-08-21", precision: "day", kind: "funding_round", company_name: "Quayside Storage (fixture)", crustdata_company_id: 900122, text: "Growth equity round recorded, $40.0M", is_estimate: false, source: source("sig-2", "Funding record", "data_provider", "POST /company/enrich#funding"), on_page: "fund:ironbridge" },
        { at: "2026-10", precision: "month", kind: "headcount", company_name: "Coastline Cold Storage (fixture)", crustdata_company_id: 900103, text: "Headcount about 180, up from about 150", is_estimate: true, source: PEOPLE_SRC, on_page: "target:fx-target-coastline-cold" },
      ],
    },
    next: [
      { kind: "verify_target", label: "Verify Kestrel Supply Systems (fixture)", sub: "Top fit, not yet a case", href: "#fits" },
      { kind: "draft_approach", label: "Draft approach to Saltmarsh Growth (fixture)", sub: "Needs a named approver. Nothing is sent", href: "#funds" },
      { kind: "complete_profile", label: "State your customer segment", sub: "Makes 1 reason assessable", href: "/app/settings" },
    ],
    work: { cases: 2, needs_you: 1 },
  };
}
