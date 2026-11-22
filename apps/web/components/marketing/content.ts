/**
 * Home page copy and illustration data.
 *
 * COPY: placeholder wording drawn from `DealProof product description.md`.
 * The final copy is written in docs/content/home.md; when it lands, replace the
 * strings here and keep the shapes.
 *
 * Every company, investor and claim below is an illustration built on the PRD's
 * Pune example. The page labels it as such wherever it appears.
 */
import type { ClaimStatus, Disposition } from "@/lib/types";

export const ILLUSTRATION_LABEL = "Illustration, not a real company";
export const ILLUSTRATION_COMPANY = "Meridian Warehousing";

export const NAV_LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#ledger", label: "The claim ledger" },
  { href: "#principles", label: "Principles" },
  { href: "#limits", label: "What it is not" },
] as const;

export const HERO = {
  eyebrow: "First-pass screening for investors and acquirers",
  title: "Know what is proven before the second meeting",
  lead: "DealProof finds companies that match your thesis, checks each claim against dated, independent evidence, and says plainly what it could not verify",
  primary: "Start a screening",
  secondary: "See how it works",
} as const;

/* ───────────────────────── The claim ledger ───────────────────────── */

export type SourceKind =
  | "registry"
  | "profiles"
  | "announcement"
  | "funding"
  | "document";

export interface SourceRef {
  kind: SourceKind;
  label: string;
  /** Written the one way dates are written: `12 Mar 2014`, or `Oct 2026`. */
  asOf: string;
}

export interface LedgerRow {
  n: number;
  claim: string;
  category: string;
  page: string;
  status: ClaimStatus;
  /** What the record shows, in DealProof's words. */
  record: string;
  estimate?: { value: string; kind: "Estimate" | "Signal" };
  sources: SourceRef[];
  notes?: { label: string; text: string }[];
  settle?: string;
}

export const LEDGER_ROWS: LedgerRow[] = [
  {
    n: 1,
    claim: "Incorporated in 2014, based in Pune",
    category: "Identity",
    page: "Seller deck p. 2",
    status: "supported",
    record: "Incorporated 2014, registered office in Pune",
    sources: [
      { kind: "registry", label: "Registry mirror", asOf: "12 Mar 2014" },
    ],
  },
  {
    n: 2,
    claim: "We employ 250 people",
    category: "Team size",
    page: "Seller deck p. 4",
    status: "cannot_verify",
    record: "A profile-based estimate is lower",
    estimate: { value: "~180 people", kind: "Estimate" },
    sources: [
      { kind: "profiles", label: "Professional profiles", asOf: "Oct 2026" },
    ],
    notes: [
      {
        label: "Why it is open",
        text: "Warehouse staff rarely have professional profiles",
      },
    ],
    settle: "A dated payroll summary",
  },
  {
    n: 3,
    claim: "Our founder ran operations at a national logistics firm",
    category: "Leadership",
    page: "Seller deck p. 5",
    status: "supported",
    record: "A professional record shows the role and the years",
    sources: [
      { kind: "profiles", label: "Professional record", asOf: "Nov 2026" },
    ],
  },
  {
    n: 4,
    claim: "We raised growth funding in 2025",
    category: "Funding",
    page: "Seller deck p. 7",
    status: "supported",
    record: "A funding record and a dated announcement agree",
    sources: [
      { kind: "funding", label: "Funding record", asOf: "3 Jun 2025" },
      { kind: "announcement", label: "Announcement", asOf: "5 Jun 2025" },
    ],
  },
  {
    n: 5,
    claim: "We opened a new facility in October 2026",
    category: "Dated events",
    page: "Seller deck p. 9",
    status: "partially_corroborated",
    record: "A dated announcement describes a planned facility",
    sources: [
      {
        kind: "announcement",
        label: "Company announcement",
        asOf: "9 Sep 2026",
      },
    ],
    notes: [
      { label: "Supported", text: "A facility was announced" },
      { label: "Not supported", text: "That it is operating" },
    ],
    settle: "A lease or occupancy record",
  },
  {
    n: 6,
    claim: "We have no debt",
    category: "Borrowing",
    page: "Seller deck p. 12",
    status: "cannot_verify",
    record: "A lender's registered security is on record",
    sources: [
      { kind: "registry", label: "Charge register mirror", asOf: "Feb 2024" },
    ],
    notes: [
      {
        label: "Why it is open",
        text: "It shows security was given, not that money is owed",
      },
    ],
    settle: "Lender statements",
  },
];

export const LEDGER_SUMMARY = {
  counts: [
    { status: "supported", count: 3 },
    { status: "partially_corroborated", count: 1 },
    { status: "cannot_verify", count: 2 },
  ] satisfies { status: ClaimStatus; count: number }[],
  line: "3 of 6 claims supported · 3 open",
  disposition: "investigate_further" as Disposition,
  next: "A request for three documents is waiting for a manager's approval",
};

/* ───────────────────────── Four steps ───────────────────────── */

export const STEPS_HEAD = {
  eyebrow: "How it works",
  title: "Four steps, one case",
  lead: "Start with a thesis, or go straight to a company you already have in mind. Everything lands in the same case file.",
};

export const STEPS = [
  {
    id: "discover",
    name: "Discover",
    summary:
      "You describe what you are looking for. DealProof returns a shortlist of real companies and explains why each one is on it.",
    give: "An investment thesis in plain words",
    get: "A ranked shortlist with reasons for inclusion and what is still unknown",
  },
  {
    id: "verify",
    name: "Verify",
    summary:
      "You pick a company. DealProof confirms which legal entity it is, then checks its claims one by one.",
    give: "A company from the shortlist, or a name and website, and the seller's presentation",
    get: "A claim ledger: each claim with a status, the exact evidence and its date",
  },
  {
    id: "evaluate",
    name: "Evaluate",
    summary:
      "DealProof turns what it found into a screening assessment you can explain to someone else.",
    give: "Nothing more. The assessment is built from the records already in the case",
    get: "Five separate judgments and one disposition, with the reasons underneath",
  },
  {
    id: "act",
    name: "Act",
    summary:
      "DealProof works out what would settle each open question and helps you ask for it.",
    give: "A named person's approval",
    get: "One consolidated request to the seller, sent once. New documents update the case in the open",
  },
] as const;

export type StepId = (typeof STEPS)[number]["id"];

export const THESIS_EXAMPLE =
  "Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion";

/* ───────────────────────── The problem ───────────────────────── */

export const PROBLEM_HEAD = {
  eyebrow: "The problem",
  title: "Screening breaks in the same eight places",
  lead: "Today this work is spread across databases, registry lookups, seller presentations and an analyst's spreadsheet.",
};

export const PROBLEMS = [
  {
    wrong: "Company information is scattered",
    cost: "Slow, repeated research",
    fix: "One search and research flow",
  },
  {
    wrong: "Companies are compared inconsistently",
    cost: "Subjective screening",
    fix: "The same criteria applied to every candidate",
  },
  {
    wrong: "Growth signals are mistaken for real traction",
    cost: "Overconfident conclusions",
    fix: "Keeps observed signals apart from confirmed results",
  },
  {
    wrong: "Seller presentations go unchecked",
    cost: "Decisions rest on unverified claims",
    fix: "Checks each claim and shows the evidence",
  },
  {
    wrong: "Similar names cause mix-ups",
    cost: "The wrong company's or person's record is attached",
    fix: "Confirms identity first, and says so when it cannot",
  },
  {
    wrong: "Financial information is missing",
    cost: "Valuations built on guesses",
    fix: "Says what is missing instead of filling the gap",
  },
  {
    wrong: "Reports take days to assemble",
    cost: "Analyst time spent compiling",
    fix: "Produces the screening memo itself",
  },
  {
    wrong: "Open questions are never followed up",
    cost: "Screening stays incomplete",
    fix: "Lists exactly what to ask the seller for",
  },
] as const;

/* ───────────────────────── Six answers ───────────────────────── */

export const STATUS_HEAD = {
  eyebrow: "The claim ledger",
  title: "Six answers, including the honest ones",
  lead: "Each claim ends in one of six statuses. Two of them exist so that a gap is never mistaken for a clean result.",
};

export const STATUS_MEANINGS: { status: ClaimStatus; meaning: string }[] = [
  {
    status: "supported",
    meaning: "Adequate evidence directly supports the claim",
  },
  {
    status: "partially_corroborated",
    meaning: "Evidence supports part of the claim, not all of it",
  },
  {
    status: "conflicting_evidence",
    meaning: "Relevant sources disagree with each other",
  },
  {
    status: "contradicted",
    meaning: "Reliable evidence directly conflicts with the precise claim",
  },
  {
    status: "cannot_verify",
    meaning:
      "Available evidence cannot settle the question. DealProof names what would",
  },
  {
    status: "not_checked",
    meaning:
      "The check was not run, for example because a source was unavailable or the budget ran out",
  },
];

export const STATUS_NOTES = {
  cannotVerify: {
    title: "Cannot verify is a real answer",
    body: "It is a legitimate answer, and often the correct one. It always comes with the document that would settle it, and that document goes on the request list.",
  },
  notChecked: {
    title: "Not checked never looks clean",
    body: "A check that was not run is hatched and dashed, says why, and is left out of every settled count.",
    claim: "Our top customer is a national retailer",
    reason: "Not checked · budget reached",
    detail: "No search was run for this claim",
  },
};

/* ───────────────────────── Fit is not evidence ───────────────────────── */

export type Verdict = "met" | "not_met" | "unknown";
export interface CriteriaCell {
  /** Weight, as a share of the full track. */
  w: number;
  verdict: Verdict;
}

export const FIT_HEAD = {
  eyebrow: "Fit and what could be assessed",
  title: "Fit is not evidence",
  lead: "A company can be attractive while its claims remain unverified. Next to every fit score DealProof shows how much of the thesis it could assess, so thin evidence does not look as ready as full evidence.",
  footnote:
    "Fit measures match to your criteria. It says nothing about returns",
};

export const FIT_ROWS: {
  company: string;
  line: string;
  fit: number;
  assessable: number;
  detail: string;
  cells: CriteriaCell[];
}[] = [
  {
    company: ILLUSTRATION_COMPANY,
    line: "Contract warehousing, Pune",
    fit: 82,
    assessable: 70,
    detail:
      "7 of 10 criteria assessable · 3 unknown: ownership, customer type, revenue band",
    cells: [
      { w: 12, verdict: "met" },
      { w: 10, verdict: "met" },
      { w: 10, verdict: "met" },
      { w: 9, verdict: "met" },
      { w: 12.5, verdict: "not_met" },
      { w: 8, verdict: "met" },
      { w: 8.5, verdict: "met" },
      { w: 12, verdict: "unknown" },
      { w: 10, verdict: "unknown" },
      { w: 8, verdict: "unknown" },
    ],
  },
  {
    company: "A second candidate",
    line: "Same thesis, fuller record",
    fit: 82,
    assessable: 100,
    detail: "10 of 10 criteria assessable · none unknown",
    cells: [
      { w: 14, verdict: "met" },
      { w: 12, verdict: "met" },
      { w: 12, verdict: "met" },
      { w: 10, verdict: "met" },
      { w: 10, verdict: "met" },
      { w: 10, verdict: "not_met" },
      { w: 8, verdict: "met" },
      { w: 8, verdict: "met" },
      { w: 8, verdict: "met" },
      { w: 8, verdict: "not_met" },
    ],
  },
];

/* ───────────────────────── Judgments and dispositions ───────────────────────── */

export const JUDGMENT_HEAD = {
  eyebrow: "The assessment",
  title: "Five judgments, never one score",
  lead: "DealProof keeps five judgments separate and never blends them. Each one answers a different question, so each one is drawn differently.",
};

export const JUDGMENTS = [
  {
    name: "Opportunity fit",
    question: "How well does this company match our strategy?",
  },
  {
    name: "Evidence sufficiency",
    question: "Do the available records support what we need to know?",
  },
  {
    name: "Business assessment",
    question: "What do observable operating indicators suggest?",
  },
  {
    name: "Financial assessment",
    question:
      "What do reliable financial inputs show, under stated assumptions?",
  },
  {
    name: "Screening disposition",
    question: "What should we do next?",
  },
] as const;

export const DISPOSITIONS_HEAD = {
  title: "Four dispositions",
  note: "Missing public evidence never leads to Deprioritise by itself.",
};

export const DISPOSITION_ORDER: Disposition[] = [
  "prioritise",
  "investigate_further",
  "deprioritise",
  "cannot_assess",
];

/* ───────────────────────── Investors ───────────────────────── */

export const INVESTOR_HEAD = {
  eyebrow: "For businesses raising money",
  title: "It also works in the other direction",
  lead: "A business describes itself and what it wants to raise. DealProof returns a shortlist of investors who have backed comparable companies, with the round and the date for each.",
  points: [
    "An investor appears only when a dated funding record supports it",
    "DealProof does not collect investors' personal contact details",
    "Any message to an investor waits for a person's approval",
  ],
  caveat:
    "This ranking describes past investments. It does not predict whether an investor will invest",
};

export const INVESTOR_ROW = {
  name: "Northgate Ventures",
  label: "Illustration, not a real investor",
  lead: "4 comparable investments · last in sector Aug 2026",
  backed: [
    {
      company: "Cold Chain Logix",
      round: "Series A",
      date: "12 Aug 2026",
    },
    { company: "Fleetwise", round: "Seed", date: "3 Mar 2025" },
  ],
  more: "+ 2 more",
  why: "4 rounds in warehousing technology in India since 2024",
  unknown: "Current fund status, cheque size",
};

/* ───────────────────────── Principles ───────────────────────── */

export const PRINCIPLES_HEAD = {
  eyebrow: "Principles",
  title: "How DealProof decides",
  lead: "A company can be attractive while its claims remain unverified. DealProof keeps those two things apart.",
};

export const PRINCIPLES = [
  {
    title: "Every fact has a source and a date",
    body: "Nothing comes from the AI's memory. If no record states it, DealProof does not say it.",
  },
  {
    title: "The right source for the right question",
    body: "A company registry is strong on incorporation. An audited statement is strong on past revenue. A customer's own confirmation is strong on a customer relationship. A company's announcement shows that it announced something, not that it happened.",
  },
  {
    title: "Estimates are labelled as estimates",
    body: "Team size drawn from professional profiles is a signal, not a payroll count.",
  },
  {
    title: "Identity comes first",
    body: "DealProof does not attach a record to a company or a person on a matching name alone. When it cannot tell two apart, it says so.",
  },
  {
    title: "Gaps are stated, not filled",
    body: "Missing information stays missing, and it is never counted against a company as poor performance.",
  },
  {
    title: "Rules decide, not AI confidence",
    body: "The same records under the same policy give the same assessment every time.",
  },
  {
    title: "A person approves anything that leaves",
    body: "No message goes to a seller without a named approver.",
  },
  {
    title: "Confidential documents stay confidential",
    body: "Uploaded files are used only for that case. They are not used to train AI, not shared across customers, stripped of personal details that are not needed, and deleted on a set schedule.",
  },
  {
    title: "New evidence changes the assessment in the open",
    body: "The earlier view is kept, and the reason for the change is shown.",
  },
] as const;

/* ───────────────────────── What it is not ───────────────────────── */

export const LIMITS_HEAD = {
  eyebrow: "Limits",
  title: "What it is not",
  lead: "DealProof is the screening that happens before formal due diligence. It makes that later work better aimed. It does not replace it.",
};

export const LIMITS = [
  {
    title: "Not financial, legal or tax due diligence",
    body: "Those rest on the seller's confidential books and on signed professional opinions.",
  },
  {
    title: "Not a prediction",
    body: "It does not predict returns or say whether an investment will succeed.",
  },
  {
    title: "Not a valuation",
    body: "Where financial figures are supplied, it can run stated scenarios, never a verified fair value.",
  },
  {
    title: "Not legal advice",
    body: "It does not give legal advice or recommend deal terms.",
  },
  {
    title: "Not a judgment of people",
    body: "It reports what records show about roles and dates.",
  },
  {
    title: "Not a view of what is off the record",
    body: "Private company financials, tax positions and many customer relationships are not public in India, and DealProof says so case by case.",
  },
] as const;

/* ───────────────────────── How it differs ───────────────────────── */

export const DIFFERS_HEAD = {
  eyebrow: "Where it sits",
  title: "How it differs from what exists",
  lead: "The difference is the connection: discovery, independent verification and transparent evaluation in one case.",
  close:
    "DealProof does not compete on how many companies it lists or how many metrics it shows. It competes on the quality of the finished screening job.",
};

export const DIFFERS = [
  {
    option: "Company discovery platforms",
    good: "Finding companies, market maps, signals",
    adds: "Checks the claims behind a company, not only its profile",
  },
  {
    option: "M&A workflow platforms",
    good: "Pipelines, document rooms, coordinating a diligence team",
    adds: "Does the first-pass research itself, against outside evidence",
  },
  {
    option: "Company registry reports",
    good: "A profile of what is on file for a company",
    adds: "Starts from what the seller claimed and reconciles each claim",
  },
  {
    option: "Pitch-deck screening tools",
    good: "Fast summaries of a presentation",
    adds: "Indian records, a dated source on every finding, and Cannot verify as a real answer",
  },
  {
    option: "An analyst working by hand",
    good: "Judgment and context",
    adds: "The same checks every time, with the evidence attached",
  },
] as const;

/* ───────────────────────── Who it is for ───────────────────────── */

export const AUDIENCE_HEAD = {
  eyebrow: "Who it is for",
  title:
    "Small teams that screen targets every month with only a few analysts",
  lead: "The first customers are small M&A advisory firms and corporate development teams. The person using it is an investment associate or a corporate development analyst who wants to spend less time compiling and be more certain of what they pass upward.",
};

export const AUDIENCE = [
  {
    who: "Private equity funds",
    need: "Screening established businesses consistently",
  },
  {
    who: "Early-stage venture funds",
    need: "Finding startups that match a thesis, and checking founders and traction",
  },
  {
    who: "Roll-up operators",
    need: "Assessing many similar targets against one strategy",
  },
  {
    who: "Family offices",
    need: "Independent checks on private businesses",
  },
  {
    who: "Search funds",
    need: "Finding and first-pass screening of acquisition targets",
  },
  {
    who: "Business brokers",
    need: "Credible, evidence-backed company profiles",
  },
] as const;

export const FIRST_CUSTOMER = {
  label: "The first customer, at ContextCon",
  body: "A mid-sized Indian logistics company that runs warehousing and transport for other businesses. Its CFO office is considering buying or investing in regional logistics, warehousing and supply-chain technology companies.",
};

/* ───────────────────────── Close ───────────────────────── */

export const CTA = {
  title: "Screen your next target with the evidence attached",
  lead: "Every opportunity that reaches a decision-maker should arrive with its claims already checked and its unknowns already named.",
  primary: "Start a screening",
};

export const FOOTER = {
  line: "Discover opportunities. Verify the evidence. Evaluate with confidence",
  built: "Built at ContextCon 2026",
  disclaimer: "Screening only. Not financial, legal or tax due diligence",
};
