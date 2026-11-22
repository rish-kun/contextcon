/**
 * Home page copy and illustration data.
 *
 * Copy comes from docs/content/home.md; keep the two in step.
 *
 * Every company, investor, claim and source below is an illustration built on the
 * PRD's Pune example, shaped like real API data so the page renders the product's own
 * components. The page labels it as an illustration wherever it appears.
 */
import type {
  Assessment,
  Claim,
  ClaimStatus,
  ClaimStatusCounts,
  Disposition,
  Evidence,
  FitResult,
  ReliabilityClass,
} from "@/lib/types";

export const ILLUSTRATION_LABEL = "Illustration, not a real company";
export const ILLUSTRATION_COMPANY = "Meridian Warehousing";

export const NAV = {
  links: [
    { href: "#how", label: "How it works" },
    { href: "#case", label: "The claim ledger" },
    { href: "#principles", label: "Principles" },
  ],
  login: "Log in",
  signup: "Sign up",
} as const;

export const HERO = {
  eyebrow: "First-pass screening for investors and acquirers",
  title: "Know what is proven before the second meeting",
  lead: "DealProof finds companies that match your thesis, checks each claim against dated, independent evidence, and says plainly what it could not verify.",
  primary: "Sign up",
  secondary: "See a finished case",
} as const;

/* ───────────────────────── Illustration: evidence ───────────────────────── */

const RETRIEVED_AT = "2026-11-22T11:12:00+05:30";

function ev(
  label: string,
  asOf: string | null,
  reliability: ReliabilityClass,
): Evidence {
  return {
    source: {
      provider: "Illustration",
      label,
      as_of: asOf,
      retrieved_at: RETRIEVED_AT,
      reliability,
    },
  };
}

const deck = (page: number) =>
  ev(`Seller deck p. ${page}`, "2026-11", "seller_document");

const SRC = {
  registry: ev("Registry mirror", "2014-03-12", "registry"),
  profiles: ev(
    "Crustdata profiles",
    "2026-10",
    "professional_profile_signal",
  ),
  career: ev("Professional record", "2026-11", "professional_profile_signal"),
  funding: ev("Funding record", "2025-06-03", "news"),
  fundingNews: ev("Announcement", "2025-06-05", "company_announcement"),
  facility: ev("Company announcement", "2026-09-09", "company_announcement"),
  charge: ev("Registry mirror", "2025-08-18", "registry"),
};

const HEADCOUNT_BASIS = "from professional profiles, not a payroll count";

/* ───────────────────────── Illustration: the claim ledger ───────────────────────── */

export const CLAIMS: Claim[] = [
  {
    id: "c1",
    number: 1,
    text: "Incorporated in 2014, based in Pune",
    category: "Identity",
    stated_in: deck(2),
    status: "supported",
    record: [
      {
        text: "The company registry record states both",
        evidence: [SRC.registry],
      },
    ],
  },
  {
    id: "c2",
    number: 2,
    text: "We employ 250 people",
    category: "Team size",
    stated_in: deck(4),
    status: "cannot_verify",
    record: [
      {
        text: "180 people",
        estimate: { kind: "estimate", basis: HEADCOUNT_BASIS },
        evidence: [SRC.profiles],
      },
    ],
    note: "A profile-based estimate is lower, but warehouse staff rarely have professional profiles.",
    what_would_settle: "Dated payroll summary",
  },
  {
    id: "c3",
    number: 3,
    text: "Our founder ran operations at a national logistics firm",
    category: "Leadership",
    stated_in: deck(5),
    status: "supported",
    record: [
      {
        text: "A professional record shows the role and the years",
        evidence: [SRC.career],
      },
    ],
  },
  {
    id: "c4",
    number: 4,
    text: "We raised growth funding in 2025",
    category: "Funding",
    stated_in: deck(7),
    status: "supported",
    record: [
      {
        text: "A funding record and a dated announcement agree",
        evidence: [SRC.funding, SRC.fundingNews],
      },
    ],
  },
  {
    id: "c5",
    number: 5,
    text: "We opened a new facility in October 2026",
    category: "Dated events",
    stated_in: deck(9),
    status: "partially_corroborated",
    record: [
      {
        text: "A dated announcement describes a planned facility",
        evidence: [SRC.facility],
        part: "supported",
      },
      {
        text: "Nothing found shows it is operating",
        evidence: [SRC.facility],
        part: "not_supported",
      },
    ],
    what_would_settle: "Lease or occupancy record",
  },
  {
    id: "c6",
    number: 6,
    text: "We have no debt",
    category: "Borrowing",
    stated_in: deck(12),
    status: "cannot_verify",
    record: [
      {
        text: "A lender's registered security is on record",
        evidence: [SRC.charge],
      },
    ],
    note: "A registered security shows security was given, not that money is owed.",
    what_would_settle: "Lender statements",
  },
];

/** The hero shows the first four claims of the copy deck's preview: 1, 2, 5 and 6. */
export const HERO_CLAIMS: Claim[] = [1, 2, 5, 6].map(
  (n) => CLAIMS.find((c) => c.number === n)!,
);

export const CLAIM_COUNTS: ClaimStatusCounts = {
  supported: 3,
  partially_corroborated: 1,
  conflicting_evidence: 0,
  contradicted: 0,
  cannot_verify: 2,
  not_checked: 0,
};

/** A claim that was never searched, for the "Not checked never looks clean" cell. */
export const NOT_CHECKED_CLAIM: Claim = {
  id: "c7",
  number: 7,
  text: "Our top customer is a national retailer",
  category: "Customers",
  stated_in: deck(11),
  status: "not_checked",
  not_checked_reason: "budget_reached",
  record: [],
};

/* ───────────────────────── Illustration: fit and assessment ───────────────────────── */

export const FIT_THIN: FitResult = {
  fit: 82,
  assessable_share: 0.7,
  criteria: [
    { id: "hq", label: "Headquartered in India", kind: "must", weight: 12, verdict: "met" },
    { id: "act", label: "Warehousing or supply-chain activity", kind: "must", weight: 10, verdict: "met" },
    { id: "age", label: "Operating for five years or more", kind: "preference", weight: 10, verdict: "met" },
    { id: "exp", label: "Recent expansion", kind: "preference", weight: 9, verdict: "met" },
    { id: "sw", label: "Own software product", kind: "preference", weight: 12.5, verdict: "not_met" },
    { id: "fund", label: "Institutional funding", kind: "preference", weight: 8, verdict: "met" },
    { id: "team", label: "Team above 100", kind: "preference", weight: 8.5, verdict: "met" },
    { id: "own", label: "Ownership", kind: "must", weight: 12, verdict: "unknown" },
    { id: "cust", label: "Customer type", kind: "preference", weight: 10, verdict: "unknown" },
    { id: "rev", label: "Revenue band", kind: "preference", weight: 8, verdict: "unknown" },
  ],
};

export const FIT_FULL: FitResult = {
  fit: 82,
  assessable_share: 1,
  criteria: [
    { id: "hq", label: "Headquartered in India", kind: "must", weight: 14, verdict: "met" },
    { id: "act", label: "Warehousing or supply-chain activity", kind: "must", weight: 12, verdict: "met" },
    { id: "own", label: "Ownership", kind: "must", weight: 12, verdict: "met" },
    { id: "age", label: "Operating for five years or more", kind: "preference", weight: 10, verdict: "met" },
    { id: "exp", label: "Recent expansion", kind: "preference", weight: 10, verdict: "met" },
    { id: "sw", label: "Own software product", kind: "preference", weight: 10, verdict: "not_met" },
    { id: "fund", label: "Institutional funding", kind: "preference", weight: 8, verdict: "met" },
    { id: "team", label: "Team above 100", kind: "preference", weight: 8, verdict: "met" },
    { id: "cust", label: "Customer type", kind: "preference", weight: 8, verdict: "met" },
    { id: "rev", label: "Revenue band", kind: "preference", weight: 8, verdict: "not_met" },
  ],
};

export const ASSESSMENT: Assessment = {
  version: 1,
  policy_version: "1.0",
  created_at: RETRIEVED_AT,
  fit: FIT_THIN,
  sufficiency: {
    settled: 6,
    required: 6,
    counts: CLAIM_COUNTS,
    gaps: ["payroll summary", "lender statements", "occupancy record"],
  },
  business: [
    {
      id: "s1",
      text: "180 people",
      estimate: { kind: "estimate", basis: HEADCOUNT_BASIS },
      evidence: [SRC.profiles],
    },
    {
      id: "s2",
      text: "Growth funding recorded in 2025",
      evidence: [SRC.funding],
    },
    {
      id: "s3",
      text: "Planned facility",
      estimate: {
        kind: "signal",
        basis: "an announcement of a plan, not an opening",
      },
      evidence: [SRC.facility],
    },
  ],
  financial: {
    state: "not_assessed",
    reason: "no reliable financial inputs",
    would_need: ["audited statements"],
  },
  disposition: {
    disposition: "investigate_further",
    reasons: [
      {
        text: "Strong fit with the client's strategy, with three of six claims supported and three open",
      },
    ],
    rests_on_claims: [2, 5, 6],
    policy_version: "1.0",
  },
};

/* ───────────────────────── The problem ───────────────────────── */

export const PROBLEM_HEAD = {
  eyebrow: "The problem",
  title: "Why first-pass screening breaks down",
  lead: "Today, screening a private company is spread across databases, registry lookups, seller presentations, and an analyst's spreadsheet. Between the first call and the memo, eight things routinely go wrong.",
};

export const PROBLEMS = [
  {
    wrong: "Company information is scattered",
    cost: "Slow, repeated research across disconnected tools",
    fix: "One connected search and research flow",
  },
  {
    wrong: "Companies are compared inconsistently",
    cost: "Subjective screening from one target to the next",
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
    cost: "Analyst time spent compiling instead of judging",
    fix: "Produces the screening memo itself",
  },
  {
    wrong: "Open questions are never followed up",
    cost: "Screening stays incomplete",
    fix: "Lists exactly what to ask the seller for",
  },
] as const;

/* ───────────────────────── Four steps ───────────────────────── */

export const STEPS_HEAD = {
  eyebrow: "How it works",
  title: "Four steps, one case",
  lead: "Start with an investment thesis, or go straight to a company you already have in mind.",
};

export const STEPS = [
  {
    id: "discover",
    name: "Discover",
    title: "Turn a thesis into a shortlist of real companies",
    lead: "Describe what you are looking for in plain words. DealProof returns companies that match your criteria and explains why each one is on the list.",
    rows: [
      {
        label: "What you give",
        text: "An investment thesis in plain words.",
      },
      {
        label: "What it does",
        text: "Turns the thesis into clear criteria, separating must-haves from preferences. Lets you edit them before anything runs, searches live company data, removes duplicates, drops companies that fail a must-have, and ranks the rest by fit.",
      },
      {
        label: "What you get",
        text: "A shortlist with each company's business, location, size and growth estimates, funding history, hiring activity, reasons for inclusion, and what is still unknown. Every item shows its source and date.",
      },
    ],
    note: "The fit score measures how well a company matches your requirements. It says nothing about expected returns. Hiring and headcount growth are never treated as proof of revenue.",
  },
  {
    id: "verify",
    name: "Verify",
    title: "Check every claim against independent records",
    lead: "Pick a company from the shortlist, or enter a name and website directly. DealProof confirms the legal entity and checks each claim one by one.",
    rows: [
      {
        label: "What you give",
        text: "A shortlisted company, or a company name and website. You can upload the seller's presentation and documents, or type in individual claims.",
      },
      {
        label: "What it does",
        text: "Confirms which legal entity you are looking at, builds a public profile, tests each factual claim against independent evidence, compares seller documents with each other, gathers recent dated events, and places the company beside comparable firms.",
      },
      {
        label: "What you get",
        text: "A claim ledger. Every claim carries a status, the exact evidence, the date of that evidence, and the document needed if it could not be settled.",
      },
    ],
    note: "What it checks first: identity, business and industry, funding events, team size and growth, leadership and founders' career history, and dated public events such as launches and expansions.",
  },
  {
    id: "evaluate",
    name: "Evaluate",
    title: "Keep five judgments separate",
    lead: "DealProof turns what it found into a screening assessment you can defend to a decision-maker. It never blends separate judgments into one score.",
    rows: [
      {
        label: "What you give",
        text: "Nothing more. The assessment is built from the records already in the case.",
      },
      {
        label: "What you get",
        text: "Opportunity fit, evidence sufficiency, a business assessment, a financial assessment when reliable inputs exist, and one screening disposition.",
      },
    ],
    note: "The evaluation adapts to the company. A young startup is judged on thesis fit, founder relevance, team development, and funding history. An established business is judged on strategic fit, identity, operating scale, financial performance, commercial position, and leadership continuity.",
  },
  {
    id: "act",
    name: "Act",
    title: "Ask for what is missing, once, after approval",
    lead: "DealProof works out which documents would settle each open question and drafts one consolidated request to the seller.",
    rows: [
      {
        label: "What you give",
        text: "Your review, the recipient address, and a named person's approval.",
      },
      {
        label: "What it does",
        text: "Lists the exact documents tied to open claims, waits until a named approver signs off, and sends the request once. When the seller's documents arrive, they attach to the same case.",
      },
      {
        label: "What you get",
        text: "Re-checked claims, an updated assessment, and an open diff showing what changed, what was believed before, and why it changed.",
      },
    ],
    note: null,
  },
] as const;

export type StepId = (typeof STEPS)[number]["id"];

export const THESIS_EXAMPLE =
  "Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion";

/* ───────────────────────── The claim ledger and its six answers ───────────────────────── */

export const CASE_HEAD = {
  eyebrow: "The claim ledger",
  title: "What a claim ledger looks like",
  lead: "A mid-sized Indian logistics company's CFO office is reviewing a regional warehousing operator in Pune after a first meeting. DealProof checks six claims from the meeting and seller presentation against independent records.",
  summary:
    "Strong fit with the client's strategy, with three of six claims supported and three open. A consolidated request list of three documents waits for the manager's approval.",
  disposition: "investigate_further" as Disposition,
};

export const STATUS_HEAD = {
  title: "Six answers, including the honest ones",
};

export const STATUS_MEANINGS: { status: ClaimStatus; meaning: string }[] = [
  {
    status: "supported",
    meaning: "Adequate evidence directly supports the claim.",
  },
  {
    status: "partially_corroborated",
    meaning: "Evidence supports part of the claim, not all of it.",
  },
  {
    status: "conflicting_evidence",
    meaning: "Relevant sources disagree with each other.",
  },
  {
    status: "contradicted",
    meaning: "Reliable evidence directly conflicts with the precise claim.",
  },
  {
    status: "cannot_verify",
    meaning:
      "Available evidence cannot settle the question. DealProof names what would.",
  },
  {
    status: "not_checked",
    meaning:
      "The check was not run, for example because a source was unavailable or the budget ran out.",
  },
];

export const STATUS_NOTES = {
  cannotVerify: {
    title: "Cannot verify is a real answer",
    body: "Private company records in India rarely cover payroll, customer contracts, or current debt balances. When available evidence cannot settle a claim, DealProof says so plainly and names the document that would.",
  },
  notChecked: {
    title: "Not checked never looks clean",
    body: "A check that was not run is marked with a dashed border, a hatched fill, and the reason it stopped, such as budget reached or source unavailable. It is never counted as settled and never hidden from the summary.",
  },
};

/* ───────────────────────── Fit is not evidence ───────────────────────── */

export const FIT_HEAD = {
  eyebrow: "Fit and what could be assessed",
  title: "Fit is not evidence",
  lead: "Next to every fit score, DealProof shows how much of your thesis it could actually assess. A company with thin public records never looks as ready as one with full records, and missing evidence never triggers Deprioritise on its own.",
  label: "Illustration, not real companies",
};

export const FIT_ROWS = [
  {
    id: "thin",
    fit: FIT_THIN,
    caption: "Attractive on what is known, with three criteria still open.",
  },
  {
    id: "full",
    fit: FIT_FULL,
    caption: "Same fit score, backed by complete criteria coverage.",
  },
];

/* ───────────────────────── Judgments and dispositions ───────────────────────── */

export const JUDGMENT_HEAD = {
  eyebrow: "The assessment",
  title: "Keep five judgments separate",
  lead: "DealProof turns what it found into a screening assessment you can defend to a decision-maker. It never blends separate judgments into one score.",
  note: "The evaluation adapts to the company. A young startup is judged on thesis fit, founder relevance, team development, and funding history. An established business is judged on strategic fit, identity, operating scale, financial performance, commercial position, and leadership continuity.",
};

export const DISPOSITIONS_HEAD = {
  title: "One of four outcomes",
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
  eyebrow: "The other direction",
  title: "For businesses raising money",
  lead: "DealProof also works in the other direction. Small and mid-sized businesses looking for capital, and the advisers representing them, often spend months approaching investors who do not back their sector or stage.",
  body: "Describe your sector, location, stage, size, and the funding you are seeking. DealProof finds comparable companies that have raised money, reads who invested in them and when, and ranks investors by how many comparable investments they have made and how recently.",
  shows: [
    "Comparable companies the investor backed, with the round and the date",
    "When the investor last invested in the sector",
    "Why they fit your profile, and what is still unknown",
  ],
  guardrails:
    "An investor appears only when a dated funding record supports it. The ranking describes past investments and does not predict whether an investor will invest. DealProof does not collect investors' personal contact details, and any message to an investor waits for a person's approval.",
};

export const INVESTOR_ROW = {
  name: "Northgate Ventures",
  label: "Illustration, not a real investor",
  lead: "4 comparable investments · last in sector Aug 2026",
  backed: [
    {
      company: "Cold Chain Logix",
      round: "Series A",
      evidence: ev("Funding record", "2026-08-12", "news"),
    },
    {
      company: "Fleetwise",
      round: "Seed",
      evidence: ev("Funding record", "2025-03-03", "news"),
    },
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
    body: "Team size drawn from professional profiles is a signal, not a payroll count. Every inferred figure carries the Estimate or Signal label and its basis.",
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
    body: "No message goes to a seller or investor without a named approver.",
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
    title: "Not financial, legal, or tax due diligence",
    body: "Formal diligence rests on the seller's confidential books and on signed professional opinions. DealProof does the first-pass research that comes before accountants and lawyers step in.",
  },
  {
    title: "Not a return predictor",
    body: "DealProof measures fit against your criteria and checks factual claims. It does not predict returns or say whether an investment will succeed.",
  },
  {
    title: "Not a valuation",
    body: "Where reliable financial figures are supplied, DealProof can run stated scenarios under stated assumptions. It never produces a verified fair value.",
  },
  {
    title: "Not legal advice or deal terms",
    body: "DealProof does not give legal advice, draft contracts, or recommend deal structure or terms.",
  },
  {
    title: "Not a judgment on people",
    body: "DealProof reports what records show about roles, career history, and dates. It does not score or judge individuals.",
  },
  {
    title: "Not a window into private records",
    body: "DealProof cannot see what is not on record. Private company financials, tax positions, and many customer relationships are not public in India, and DealProof says so case by case.",
  },
] as const;

/* ───────────────────────── How it differs ───────────────────────── */

export const DIFFERS_HEAD = {
  eyebrow: "Where it sits",
  title: "How it differs from what exists",
  lead: "DealProof does not compete on how many companies it lists or how many metrics it shows. It competes on the quality of the finished screening job.",
  close:
    "The difference is the connection: discovery, independent verification, and transparent evaluation in one reproducible case.",
};

export const DIFFERS = [
  {
    option: "Company discovery platforms",
    good: "Finding companies, building market maps, and surfacing growth signals",
    adds: "Checks the claims behind a company, not only its profile",
  },
  {
    option: "M&A workflow platforms",
    good: "Managing pipelines, document rooms, and diligence teams",
    adds: "Does the first-pass research itself against outside evidence",
  },
  {
    option: "Company registry reports",
    good: "Giving a static profile of what is on file for an entity",
    adds: "Starts from what the seller claimed and reconciles each claim one by one",
  },
  {
    option: "Pitch-deck screening tools",
    good: "Summarising a seller presentation quickly",
    adds: "Indian records, a dated source on every finding, and Cannot verify as a real answer",
  },
  {
    option: "An analyst working by hand",
    good: "Judgment, nuance, and context",
    adds: "The same checks every time, in minutes, with every source attached",
  },
] as const;

/* ───────────────────────── Who it is for ───────────────────────── */

export const AUDIENCE_HEAD = {
  eyebrow: "Customers",
  title: "Who it is for",
  lead: "Built first for small M&A advisory firms and corporate development teams, including mid-market CFO offices screening regional targets in sectors such as logistics, warehousing, and supply-chain technology, that review acquisition opportunities every month with only a few analysts.",
  body: "The primary user is an investment associate or corporate development analyst who wants to spend less time compiling and be more certain of what they pass upward: no wrong facts in the memo, no recommendation they cannot back up, and no confidential file ending up where it should not.",
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
  {
    who: "Businesses raising money and their advisers",
    need: "A shortlist of relevant investors backed by dated funding records",
  },
] as const;

/* ───────────────────────── Close ───────────────────────── */

export const CTA = {
  title: "Screen your next target with the evidence attached",
  lead: "Every investment or acquisition opportunity that reaches a decision-maker should arrive with its claims already checked and its unknowns already named.",
  primary: "Sign up",
  secondary: "See a finished case",
};

export const FOOTER = {
  built: "Built at ContextCon 2026",
  links: [
    { href: "/app/policy", label: "Scoring policy" },
    { href: "#principles", label: "Confidentiality" },
    { href: "https://github.com/rish-kun/contextcon", label: "GitHub" },
  ],
  scope: "Screening only. Not financial, legal or tax due diligence.",
};
