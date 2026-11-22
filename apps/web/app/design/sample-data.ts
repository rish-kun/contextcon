/**
 * SAMPLE DATA for the component gallery only.
 * "Meridian Warehousing" is an illustration, not a real company. Every source, date,
 * figure and person here is invented to show density and wording. Nothing in this file
 * may be imported by a product page.
 */
import type {
  Assessment,
  AssessmentDiff,
  AssessmentVersionMeta,
  CaseCost,
  Claim,
  ClaimStatusCounts,
  Evidence,
  FitResult,
  Identity,
  ReliabilityClass,
  Run,
  SellerRequest,
  Source,
} from "@/lib/types";

const RETRIEVED = "2026-11-22T11:09:00Z"; // 22 Nov 2026, 16:39 IST
const ENTITY = { entity_name: "Meridian Warehousing Pvt Ltd (sample)", matched_on: "domain + registration number" };

function source(
  label: string,
  reliability: ReliabilityClass,
  as_of: string | null,
  extra: Partial<Source> = {},
): Source {
  return {
    provider: "Sample provider",
    label,
    reliability,
    as_of,
    retrieved_at: RETRIEVED,
    url: `https://example.com/sample/${reliability}`,
    ...extra,
  };
}

export const ev = {
  registry: {
    source: source("Registry mirror", "registry_mirror", "2014-03-12"),
    field_path: "company.date_of_incorporation",
    value: "2014-03-12",
    attached_to: ENTITY,
  },
  registryOffice: {
    source: source("Registry mirror", "registry_mirror", "2014-03-12"),
    field_path: "company.registered_office.city",
    value: "Pune",
    attached_to: ENTITY,
  },
  profiles: {
    source: source("Crustdata profiles", "professional_profile_signal", "2026-10", {
      provider: "Crustdata company enrich (sample)",
      url: null,
      request: "company_enrich?domain=meridian-warehousing.example&fields=headcount",
    }),
    field_path: "headcount.latest_count",
    value: "180",
    attached_to: ENTITY,
  },
  jobs: {
    source: source("Crustdata job listings", "professional_profile_signal", "2026-11", {
      provider: "Crustdata job search (sample)",
      url: null,
      request: "job_search?company_id=sample-001&status=open",
    }),
    field_path: "jobs.open_count",
    value: "2",
    attached_to: ENTITY,
  },
  announcement: {
    source: source("Company announcement", "company_announcement", "2026-09-09"),
    quote: "We plan to open a second facility at Chakan in the coming quarter.",
    attached_to: ENTITY,
  },
  fundingAnnouncement: {
    source: source("Funding announcement", "company_announcement", "2025-06-05"),
    quote: "Meridian Warehousing has closed its Series A round.",
    attached_to: ENTITY,
  },
  news: {
    source: source("Trade press report", "news", "2025-06-03"),
    quote: "The round was reported at the start of June.",
    attached_to: ENTITY,
  },
  newsLater: {
    source: source("Business daily report", "news", "2025-07-18"),
    quote: "The round is said to have closed in mid July.",
    attached_to: ENTITY,
  },
  counterparty: {
    source: source("Customer confirmation", "counterparty_confirmation", "2026-11-18"),
    quote: "We confirm a warehousing contract with the company since 2023.",
    attached_to: ENTITY,
  },
  audited: {
    source: source("Audited statement FY2025", "audited_statement", "2025-03-31"),
    field_path: "statement.revenue_from_operations",
    value: "INR 41.2 crore",
    attached_to: ENTITY,
  },
  registryDirectors: {
    source: source("Registry mirror", "registry_mirror", "2026-08-01"),
    field_path: "company.directors.count",
    value: "3",
    attached_to: ENTITY,
  },
  deck: (page: number): Evidence => ({
    source: source(`Seller deck p. ${page}`, "seller_document", "2026-11", {
      provider: "Uploaded document (sample)",
      url: null,
    }),
    attached_to: ENTITY,
  }),
  lease: {
    source: source("Lease agreement p. 3", "seller_document", "2026-10-01", {
      provider: "Uploaded document (sample)",
      url: null,
    }),
    quote: "The lease term commences on 1 October 2026.",
    attached_to: ENTITY,
  },
  typed: {
    source: source("Typed by Asha Rao", "seller_statement", "2026-11-22", {
      provider: "Typed by a user (sample)",
      url: null,
    }),
  },
  undated: {
    source: source("Company website", "company_announcement", null),
    quote: "Serving enterprise customers across western India.",
    attached_to: ENTITY,
  },
} satisfies Record<string, Evidence | ((page: number) => Evidence)>;

export const allClasses: Evidence[] = [
  {
    source: source("Official registry", "registry", "2014-03-12"),
    field_path: "company.date_of_incorporation",
    value: "2014-03-12",
    attached_to: ENTITY,
  },
  ev.registry,
  ev.audited,
  ev.counterparty,
  ev.announcement,
  ev.profiles,
  {
    source: source("Crustdata company record", "data_provider", "2026-11", {
      url: null,
      request: "POST /company/enrich",
    }),
    field_path: "company.headquarters.city",
    value: "Pune",
    attached_to: ENTITY,
  },
  ev.news,
  ev.deck(7),
  ev.typed,
];

export const claims: Claim[] = [
  {
    id: "c1",
    number: 1,
    text: "Incorporated in 2014, based in Pune",
    category: "Identity",
    stated_in: ev.deck(2),
    status: "supported",
    record: [
      { text: "Incorporated 2014", evidence: [ev.registry] },
      { text: "Registered office in Pune", evidence: [ev.registryOffice] },
    ],
  },
  {
    id: "c2",
    number: 2,
    text: "We employ 250 people",
    category: "Team size",
    stated_in: ev.deck(4),
    status: "cannot_verify",
    record: [
      {
        text: "180 people",
        evidence: [ev.profiles],
        estimate: { kind: "estimate", basis: "from professional profiles, not a payroll count" },
      },
    ],
    note: "Warehouse staff rarely have professional profiles, so a profile count cannot settle a payroll figure.",
    what_would_settle: "a dated payroll summary",
  },
  {
    id: "c3",
    number: 3,
    text: "We have five directors on the board",
    category: "Leadership",
    stated_in: ev.deck(6),
    status: "contradicted",
    record: [{ text: "Three directors are on record", evidence: [ev.registryDirectors] }],
    note: "The registry lists three directors as of 1 Aug 2026. No appointment after that date was found.",
  },
  {
    id: "c4",
    number: 4,
    text: "We closed our Series A in June 2025",
    category: "Funding",
    stated_in: ev.deck(8),
    status: "conflicting_evidence",
    record: [
      { text: "An announcement and one report date the round to early June 2025", evidence: [ev.fundingAnnouncement, ev.news] },
      { text: "A second report says it closed in mid July 2025", evidence: [ev.newsLater] },
    ],
    note: "Two reports disagree on the closing date. The round itself is not in dispute.",
    what_would_settle: "the signed share subscription agreement",
  },
  {
    id: "c5",
    number: 5,
    text: "We opened a new facility in October 2026",
    category: "Dated events",
    stated_in: ev.deck(9),
    status: "partially_corroborated",
    record: [
      { text: "A facility was announced as planned", evidence: [ev.announcement], part: "supported" },
      { text: "Nothing found shows that it is operating", evidence: [ev.announcement], part: "not_supported" },
    ],
    what_would_settle: "a lease or occupancy record",
    changed_in_version: 2,
  },
  {
    id: "c6",
    number: 6,
    text: "Our top customer is a national retailer",
    category: "Customers",
    stated_in: ev.deck(11),
    status: "not_checked",
    not_checked_reason: "budget_reached",
    record: [],
    retry_credits_estimate: 4,
  },
  {
    id: "c7",
    number: 7,
    text: "We hold an ISO 9001 certificate for both sites",
    category: "Certifications",
    stated_in: ev.typed,
    status: "not_checked",
    not_checked_reason: "source_unavailable",
    record: [],
    retry_credits_estimate: 2,
  },
];

export const pendingClaim: Claim = {
  id: "c8",
  number: 8,
  text: "Our founder ran operations at a national logistics firm",
  category: "Leadership",
  stated_in: ev.deck(3),
  status: "not_checked",
  record: [],
};

export const counts: ClaimStatusCounts = {
  supported: 5,
  partially_corroborated: 1,
  conflicting_evidence: 1,
  contradicted: 1,
  cannot_verify: 1,
  not_checked: 3,
};

export const countsComplete: ClaimStatusCounts = {
  supported: 8,
  partially_corroborated: 2,
  conflicting_evidence: 0,
  contradicted: 0,
  cannot_verify: 2,
  not_checked: 0,
};

export const fit: FitResult = {
  fit: 82,
  assessable_share: 0.7,
  criteria: [
    { id: "k1", label: "Headquartered in India", kind: "must", weight: 1, verdict: "met", evidence: [ev.registryOffice] },
    { id: "k2", label: "Privately held", kind: "must", weight: 1, verdict: "met", evidence: [ev.registry] },
    { id: "k3", label: "Warehousing activity", kind: "preference", weight: 1, verdict: "met" },
    { id: "k4", label: "Founded before 2018", kind: "preference", weight: 1, verdict: "met" },
    { id: "k5", label: "More than 500 people", kind: "preference", weight: 0.5, verdict: "not_met" },
    { id: "k6", label: "Recent expansion", kind: "preference", weight: 1.5, verdict: "met" },
    { id: "k7", label: "Raised institutional funding", kind: "preference", weight: 1, verdict: "met" },
    { id: "k8", label: "Ownership", kind: "preference", weight: 1.5, verdict: "unknown" },
    { id: "k9", label: "Customer type", kind: "preference", weight: 1, verdict: "unknown" },
    { id: "k10", label: "Revenue band", kind: "preference", weight: 1.5, verdict: "unknown" },
  ],
};

export const fitFull: FitResult = {
  fit: 82,
  assessable_share: 1,
  criteria: fit.criteria.map((c, i) =>
    c.verdict === "unknown" ? { ...c, verdict: i === 8 ? "not_met" : "met" } : c,
  ),
};

export const fitUnavailable: FitResult = {
  fit: null,
  assessable_share: 0,
  criteria: fit.criteria.map((c) => ({ ...c, verdict: "unknown" as const })),
};

export const assessment: Assessment = {
  version: 2,
  policy_version: "1.0",
  created_at: "2026-11-22T11:12:00Z",
  fit,
  sufficiency: { settled: 9, required: 12, counts, gaps: ["payroll", "lender statement", "occupancy"] },
  business: [
    {
      id: "s1",
      text: "180 people",
      estimate: { kind: "estimate", basis: "from professional profiles, not a payroll count" },
      evidence: [ev.profiles],
    },
    {
      id: "s2",
      text: "Headcount up over 12 months",
      estimate: { kind: "signal", basis: "profile counts rose; this is not proof of revenue" },
      evidence: [ev.profiles],
    },
    {
      id: "s3",
      text: "2 open roles",
      estimate: { kind: "signal", basis: "open job listings, which can be stale" },
      evidence: [ev.jobs],
    },
    { id: "s4", text: "Planned facility announced", evidence: [ev.announcement] },
  ],
  financial: {
    state: "not_assessed",
    reason: "no reliable financial inputs",
    would_need: ["audited statements", "lender statements"],
  },
  disposition: {
    disposition: "investigate_further",
    reasons: [
      { text: "Strong fit on the criteria that could be assessed" },
      { text: "Three required checks are still open", evidence: [ev.profiles] },
    ],
    rests_on_claims: [2, 5, 6],
    policy_version: "1.0",
  },
};

export const assessmentWithFinancials: Assessment = {
  ...assessment,
  version: 3,
  fit: fitFull,
  sufficiency: { settled: 12, required: 12, counts: countsComplete, gaps: [] },
  financial: {
    state: "assessed",
    figures: [
      { label: "Revenue from operations, FY2025", value: "INR 41.2 crore", evidence: [ev.audited] },
      {
        label: "Scenario: revenue at 12% growth, FY2026",
        value: "INR 46.1 crore",
        assumption: "12% growth, supplied by the analyst; not a forecast",
        evidence: [ev.audited],
      },
    ],
  },
  disposition: {
    disposition: "prioritise",
    reasons: [{ text: "Strong fit, and every required check is settled" }],
    rests_on_claims: [1, 2, 5],
    policy_version: "1.0",
  },
};

export const identityConfirmed: Identity = {
  state: "confirmed",
  entity_name: "Meridian Warehousing Pvt Ltd (sample)",
  keys: [
    { key: "domain", label: "Domain", value: "meridian-warehousing.example", evidence: [ev.profiles] },
    { key: "registration_number", label: "Registration number", value: "SAMPLE-0000-2014", evidence: [ev.registry] },
    { key: "registered_city", label: "Registered city", value: "Pune", evidence: [ev.registryOffice] },
    { key: "founded_year", label: "Founded year", value: "2014", evidence: [ev.registry] },
  ],
};

/** A rule break: the founded year arrived with no evidence reference. */
export const identityUnsourcedKey: Identity = {
  ...identityConfirmed,
  keys: identityConfirmed.keys.map((item) =>
    item.key === "founded_year" ? { ...item, evidence: [] } : item,
  ),
};

export const identityUnresolved: Identity = {
  state: "unresolved",
  candidates: [
    {
      id: "a",
      name: "Cold Chain Logix Pvt Ltd (sample)",
      matching: [{ key: "legal_name", label: "Legal name", value: "Cold Chain Logix", evidence: [ev.registry] }],
      differing: [
        { key: "registered_city", label: "Registered city", value: "Nashik", evidence: [ev.registryOffice] },
        { key: "founded_year", label: "Founded year", value: "2016", evidence: [ev.registry] },
      ],
    },
    {
      id: "b",
      name: "Coldchain Logix Solutions LLP (sample)",
      matching: [{ key: "domain", label: "Domain", value: "coldchainlogix.example", evidence: [ev.profiles] }],
      differing: [
        { key: "legal_name", label: "Legal name", value: "Coldchain Logix Solutions", evidence: [ev.registry] },
        { key: "registered_city", label: "Registered city", value: "Pune", evidence: [ev.registryOffice] },
      ],
    },
  ],
};

const baseSteps: Run["steps"] = [
  { id: "r1", label: "Confirm identity", status: "done", result: "matched on domain + registration number", credits_used: 0 },
  { id: "r2", label: "Build public profile", status: "done", result: "Crustdata company record", credits_used: 4 },
  { id: "r3", label: "Read seller deck", status: "done", result: "12 claims extracted from 14 pages", model_usd: 0.03 },
  { id: "r4", label: "Gather evidence", status: "running", detail: "claim 7 of 12 · searching dated announcements" },
  { id: "r5", label: "Extract facts", status: "pending" },
  { id: "r6", label: "Apply status rules", status: "pending" },
  { id: "r7", label: "Evaluate", status: "pending" },
];

export const runRunning: Run = {
  id: "run-1",
  kind: "verify",
  subject: "Meridian Warehousing (sample)",
  status: "running",
  steps: baseSteps,
  elapsed_seconds: 134,
  credits_used: 38,
  credit_budget: 150,
};

export const runResumed: Run = {
  ...runRunning,
  id: "run-2",
  resumed_at: "2026-11-22T11:21:00Z",
  steps: baseSteps.map((s) => (s.status === "done" ? { ...s, from_cache: true } : s)),
};

export const runFailed: Run = {
  ...runRunning,
  id: "run-3",
  status: "failed",
  elapsed_seconds: 171,
  credits_used: 150,
  steps: [
    ...baseSteps.slice(0, 3),
    { id: "r4", label: "Gather evidence", status: "done", result: "evidence for 9 of 12 claims", credits_used: 146 },
    { id: "r4b", label: "Check customer claims", status: "skipped_budget" },
    { id: "r5", label: "Extract facts", status: "failed", error: "the model returned an invalid response twice" },
    { id: "r6", label: "Apply status rules", status: "pending" },
    { id: "r7", label: "Evaluate", status: "pending" },
  ],
};

export const runFinished: Run = {
  ...runRunning,
  id: "run-4",
  status: "finished",
  elapsed_seconds: 171,
  credits_used: 61,
  checks_not_run: 2,
  steps: baseSteps.map((s) => ({ ...s, status: "done" as const })),
};

export const cost: CaseCost = {
  credits_used: 86,
  credit_budget: 150,
  model_usd: 0.42,
  lines: [
    { id: "l1", run_label: "Verify", step_label: "Build public profile", credits: 4, model_usd: null, at: "2026-11-22T11:09:00Z" },
    { id: "l2", run_label: "Verify", step_label: "Gather evidence", credits: 48, model_usd: null, at: "2026-11-22T11:10:00Z" },
    { id: "l3", run_label: "Verify", step_label: "Extract facts", credits: null, model_usd: 0.18, at: "2026-11-22T11:11:00Z" },
    { id: "l4", run_label: "Verify (resumed)", step_label: "Gather evidence", credits: 0, model_usd: null, from_cache: true, at: "2026-11-22T11:21:00Z" },
    { id: "l5", run_label: "Recheck", step_label: "Gather evidence", credits: 34, model_usd: null, at: "2026-11-22T11:40:00Z" },
    { id: "l6", run_label: "Recheck", step_label: "Draft memo", credits: null, model_usd: 0.24, at: "2026-11-22T11:42:00Z" },
  ],
};

export const costReached: CaseCost = { ...cost, credits_used: 150, checks_not_run: 3 };

export const versions: AssessmentVersionMeta[] = [
  { version: 1, created_at: "2026-11-20T05:35:00Z", trigger: "initial screening" },
  { version: 2, created_at: "2026-11-22T11:12:00Z", trigger: "after “Lease agreement.pdf” from seller" },
];

export const diff: AssessmentDiff = {
  from_version: 1,
  to_version: 2,
  unchanged_claims: 11,
  changes: [
    {
      kind: "claim_status",
      claim_number: 5,
      claim_text: "We opened a new facility in October 2026",
      before: "partially_corroborated",
      after: "supported",
      reason: "the lease starts on 1 Oct 2026 and an occupancy certificate was supplied",
      evidence: [ev.lease],
    },
    { kind: "value", label: "Evidence sufficiency", before: "9 of 12 settled", after: "10 of 12 settled" },
    {
      kind: "disposition",
      before: "investigate_further",
      after: "prioritise",
      reason: "the facility claim was the last open required check for fit",
    },
  ],
};

export const diffDowngrade: AssessmentDiff = {
  from_version: 2,
  to_version: 3,
  unchanged_claims: 11,
  changes: [
    {
      kind: "claim_status",
      claim_number: 4,
      claim_text: "We closed our Series A in June 2025",
      before: "supported",
      after: "conflicting_evidence",
      reason: "a second report gives a different closing date",
      evidence: [ev.newsLater],
    },
    {
      kind: "disposition",
      before: "prioritise",
      after: "investigate_further",
      reason: "",
    },
  ],
};

/** A rule break: the claim status moved and no evidence came with it. */
export const diffUnsourced: AssessmentDiff = {
  from_version: 2,
  to_version: 3,
  unchanged_claims: 10,
  changes: [
    {
      kind: "claim_status",
      claim_number: 6,
      claim_text: "Our occupancy is above 90%",
      before: "cannot_verify",
      after: "supported",
      reason: "the seller confirmed it on a call",
      evidence: [],
    },
    diffDowngrade.changes[0],
  ],
};

/**
 * A scoring-policy update that gave many claims their first status, beside one claim
 * that moved on evidence and one judgment. The policy claims fold into one row.
 */
const policyCause = { kind: "policy", from: "2026-11-22.2", to: "2026-11-22.3" } as const;
export const diffPolicy: AssessmentDiff = {
  from_version: 1,
  to_version: 2,
  unchanged_claims: 0,
  changes: [
    ...[
      "Trusted by more than 100 clients in 20 countries",
      "We are an OEM partner of a named analytics vendor",
      "We have onboarded more than 80 customers",
      "99% positive feedback",
      "We hold ISO 9001 and ISO 27001 certificates",
    ].map(
      (text, index): AssessmentDiff["changes"][number] => ({
        kind: "claim_status",
        claim_number: index + 1,
        claim_text: text,
        before: null,
        after: "cannot_verify",
        reason: "",
        cause: policyCause,
        evidence: [],
      }),
    ),
    {
      kind: "claim_status",
      claim_number: 6,
      claim_text: "Headquartered in Pune, with branch offices in two other cities",
      before: null,
      after: "contradicted",
      reason: "",
      cause: { kind: "evidence" },
      evidence: [ev.registryOffice],
    },
    { kind: "value", label: "Evidence sufficiency", before: "0% of required checks settled", after: "17% of required checks settled", reason: "Required checks affected: location" },
    {
      kind: "disposition",
      before: "investigate_further",
      after: "deprioritise",
      reason: "a requirement you set has verifiably failed",
    },
  ],
};

const requestBase: SellerRequest = {
  id: "req-1",
  status: "draft",
  documents: [
    { id: "d1", name: "Dated payroll summary", claim_number: 2 },
    { id: "d2", name: "Lender statements", claim_number: 6 },
    { id: "d3", name: "Lease or occupancy record", claim_number: 5 },
  ],
  recipient: null,
  subject: "Information request: Meridian Warehousing (sample)",
  body: "Thank you for the presentation. To complete our first review, could you share the three documents listed below.\n\n1. A dated payroll summary\n2. Lender statements\n3. The lease or occupancy record for the new facility",
  approver: null,
};

const approved = {
  recipient: "seller@example.com",
  approver: { name: "Asha Rao (sample)" },
  approved_at: "2026-11-22T11:18:00Z",
};

export const requests = {
  draft: requestBase,
  approved: { ...requestBase, ...approved, status: "approved" },
  sent: { ...requestBase, ...approved, status: "sent", sent_at: "2026-11-22T11:18:04Z" },
  suppressed: { ...requestBase, ...approved, status: "suppressed_test_mode" },
  failed: {
    ...requestBase,
    ...approved,
    status: "failed",
    failure_reason: "The mail provider rejected the recipient address",
  },
} satisfies Record<string, SellerRequest>;

export const sampleUser = { name: "Asha Rao (sample)" };
