/**
 * Recorded activity for the fixture runs, in the event shape of
 * `docs/design/iterations/D-live-run-experience.md` §2. Fixture mode only.
 *
 * This stands in for the API's own recorded fixture stream until that lands; once
 * `fixtures.json` carries `activities`, `lib/api/fixtures.ts` uses those and this file can
 * go. Every row is built from the fixture data itself (the shortlist, the investor
 * entries, the case's claims and evidence), so ids join with the result endpoints and the
 * totals match the fixture run's own step results. Every company is fictional.
 */
import type {
  CaseDetail,
  ClaimOut,
  InvestorSearchOut,
  RunOut,
  StepOut,
  ThesisOut,
} from "@/lib/api/client";
import type { Activity, ActivityCall, ActivityItem, ActivitySource } from "./types";

export interface FixtureSources {
  thesis: ThesisOut;
  investorSearch: InvestorSearchOut;
  caseDetails: Record<string, CaseDetail>;
}

type Draft = Partial<Omit<Activity, "seq" | "run_id" | "step_id" | "step_key" | "at">> & {
  kind: Activity["kind"];
  label: string;
  /** Milliseconds since the previous event. */
  gap?: number;
};

type CallDraft = Partial<ActivityCall> & Pick<ActivityCall, "endpoint">;

const CATEGORY_WORDS: Record<string, string> = {
  identity_incorporation: "incorporation",
  team_size: "team size",
  leadership_history: "leadership history",
  funding: "funding",
  dated_event: "dated event",
  customer_partnership: "customers",
  location: "location",
  debt_security: "debt",
};

const STEP_RESULT_STATUS: Record<string, string> = {
  supported: "supported",
  "cannot verify": "cannot_verify",
  conflicting: "conflicting_evidence",
  partial: "partially_corroborated",
  contradicted: "contradicted",
};

const GAP_SENTENCE: Record<string, string> = {
  cannot_verify: "No independent record settles this",
  partially_corroborated: "Nothing found shows the facility is operating",
  conflicting_evidence: "Two records give different dates",
  contradicted: "The registry record states a different place",
};

class Recorder {
  readonly events: Activity[] = [];
  private clock: number;
  private credits = 0;
  private usd = 0;

  constructor(
    private readonly run: RunOut,
    private step: StepOut,
  ) {
    this.clock = Date.parse(run.created_at);
  }

  at(step: StepOut): this {
    this.step = step;
    return this;
  }

  emit(draft: Draft): void {
    const { gap = 900, ...rest } = draft;
    this.clock += gap;
    this.events.push({
      seq: this.events.length + 1,
      run_id: this.run.id,
      step_id: this.step.id,
      step_key: this.step.key,
      at: new Date(this.clock).toISOString(),
      detail: null,
      progress: null,
      source: null,
      call: null,
      counts: null,
      highlights: null,
      items: null,
      subject: null,
      code: null,
      ref: null,
      ...rest,
    });
  }

  status(label: string, extra: Partial<Draft> = {}): void {
    this.emit({ kind: "status", label, gap: 500, ...extra });
  }

  call(label: string, call: CallDraft, extra: Partial<Draft> = {}): void {
    const provider = call.provider ?? "crustdata";
    const credits = provider === "crustdata" ? (call.credits ?? 0) : null;
    const usd = provider === "anthropic" ? (call.usd ?? 0) : null;
    this.credits += credits ?? 0;
    this.usd += usd ?? 0;
    this.emit({
      kind: provider === "anthropic" ? "model" : "call",
      label,
      gap: 1400,
      ...extra,
      call: {
        provider,
        ok: true,
        error: null,
        from_cache: false,
        attempts: 1,
        duration_ms: 1200,
        ...call,
        credits,
        usd,
        credits_total: Math.round(this.credits * 10) / 10,
        usd_total: Math.round(this.usd * 10000) / 10000,
      },
    });
  }

  model(label: string, usd: number, counts: Record<string, number>, extra: Partial<Draft> = {}): void {
    this.call(label, { provider: "anthropic", endpoint: "messages", usd }, { counts, gap: 1100, ...extra });
  }

  source(label: string, source: Partial<ActivitySource>, extra: Partial<Draft> = {}): void {
    this.emit({
      kind: "source",
      label,
      gap: 700,
      ...extra,
      source: {
        type: "web_page",
        domain: null,
        url: null,
        title: null,
        source_class: "news",
        as_of: null,
        state: "read",
        reason: null,
        ...source,
      },
    });
  }

  finding(
    subject: Activity["subject"],
    label: string,
    items: ActivityItem[],
    counts: Record<string, number>,
    extra: Partial<Draft> = {},
  ): void {
    this.emit({ kind: "finding", label, subject, items, counts, gap: 400, ...extra });
  }

  notice(code: string, label: string, detail: string): void {
    this.emit({ kind: "notice", code, label, detail, gap: 200 });
  }
}

const record = (name: string): Partial<ActivitySource> => ({
  type: "crustdata_record",
  title: name,
  source_class: "professional_profile_signal",
  as_of: "2026-11-01",
});

function domainOf(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/* ───────────────────────── Discover ───────────────────────── */

/** Named in the search and never enriched: found, then dropped or left outside the top 15. */
const EXTRA_CANDIDATES: { id: string; name: string; location: string; headcount: number; drop?: string }[] = [
  { id: "fx-cand-ridgeway", name: "Ridgeway Cold Chain (fixture)", location: "Pune, India", headcount: 210 },
  { id: "fx-cand-lattice", name: "Lattice Yards (fixture)", location: "Chennai, India", headcount: 64 },
  { id: "fx-cand-portside", name: "Portside Freight Systems (fixture)", location: "Mumbai, India", headcount: 480, drop: "Failed must-have: privately held" },
  { id: "fx-cand-kestrel-in", name: "Kestrel Supply Systems India (fixture)", location: "Bengaluru, India", headcount: 85, drop: "Duplicate of Kestrel Supply Systems (fixture)" },
  { id: "fx-cand-anchor", name: "Anchorline WMS (fixture)", location: "Hyderabad, India", headcount: 120 },
  { id: "fx-cand-quay", name: "Quayside Logistics Tech (fixture)", location: "Ahmedabad, India", headcount: 95, drop: "Failed must-have: warehousing or supply-chain software" },
  { id: "fx-cand-morrow-2", name: "Morrow Docks Pvt Ltd (fixture)", location: "Kochi, India", headcount: 40, drop: "Duplicate of Morrow Docks (fixture)" },
  { id: "fx-cand-varuna", name: "Varuna Stockrooms (fixture)", location: "Jaipur, India", headcount: 58 },
];

function discover(run: RunOut, { thesis }: FixtureSources): Activity[] {
  const step = (suffix: string) => run.steps.find((s) => s.key.endsWith(suffix)) ?? run.steps[0];
  const rec = new Recorder(run, run.steps[0]);
  const shortlist = thesis.shortlist;
  const known: ActivityItem[] = shortlist.map((item) => ({
    id: item.id,
    stage: "found",
    name: item.name,
    domain: item.domain,
    location: item.card.location?.value ?? null,
    headcount: item.card.headcount?.value ?? null,
    headcount_is_estimate: item.card.headcount?.is_estimate ?? true,
  }));
  const extras: ActivityItem[] = EXTRA_CANDIDATES.map((c) => ({
    id: c.id,
    stage: "found",
    name: c.name,
    domain: null,
    location: c.location,
    headcount: c.headcount,
    headcount_is_estimate: true,
  }));
  const counts = { found: 0, in_play: 0, dropped: 0, enriched: 0, scored: 0 };

  // Search: three passes, 48 companies in all.
  rec.at(step(".search"));
  rec.status("Resolving filter values");
  rec.status("Searching companies in India · warehousing and supply-chain software · 50 to 1,000 people");
  const passes: { fresh: number; credits: number; items: ActivityItem[]; detail: string }[] = [
    { fresh: 24, credits: 2.2, items: [...known, ...extras.slice(0, 3)].slice(0, 8), detail: "primary pass" },
    { fresh: 16, credits: 2.0, items: extras.slice(3, 6), detail: "second pass" },
    { fresh: 8, credits: 2.0, items: extras.slice(6), detail: "widened pass" },
  ];
  passes.forEach((pass, index) => {
    if (index === 2) {
      rec.notice(
        "search_widened",
        "Widened the search",
        "The strict filters returned 40 companies; preferences were relaxed",
      );
      rec.status("Searching companies in India · logistics software");
    }
    rec.call(
      `Company search returned ${pass.fresh} new companies`,
      { endpoint: "company_search", credits: pass.credits },
      { detail: pass.detail, counts: { returned: pass.fresh + index * 3, new: pass.fresh } },
    );
    counts.found += pass.fresh;
    counts.in_play = counts.found;
    rec.finding("company", `Found ${pass.fresh} companies`, pass.items, { ...counts }, { detail: pass.detail });
  });

  // Gate: 41 kept, 7 dropped.
  rec.at(step(".dedupe_gate"));
  rec.status("Removing duplicates and must-have failures");
  counts.dropped = 7;
  counts.in_play = 41;
  rec.finding(
    "company",
    "Dropped 7 companies",
    EXTRA_CANDIDATES.filter((c) => c.drop).map((c) => ({
      id: c.id,
      stage: "dropped",
      name: c.name,
      reason: c.drop,
    })),
    { ...counts },
    { detail: "3 duplicates · 4 failed a must-have", gap: 900 },
  );

  // Enrich: one call for the top 15, then job postings per company.
  rec.at(step(".enrich"));
  rec.status("Enriching 15 companies");
  rec.finding(
    "company",
    "Enriching the top 15",
    shortlist.map((item) => ({
      id: item.id,
      stage: "enriching",
      marks: { funding: "pending", headcount: "pending", hiring: "pending" },
    })),
    { ...counts },
    { gap: 200 },
  );
  rec.call(
    "Enriched 15 companies",
    { endpoint: "company_enrich", credits: 26 },
    {
      detail: "funding, headcount and web traffic",
      gap: 2400,
      counts: {
        requested: 15,
        returned: 15,
        with_funding: 6,
        funding_rounds: 9,
        with_investors: 5,
        with_headcount_series: 11,
        with_web_traffic: 4,
      },
      highlights: [
        "Harbourline Warehousing (fixture) · Series A · Nov 2023",
        "Kestrel Supply Systems (fixture) · about 85 people",
      ],
    },
  );
  shortlist.forEach((item, index) => {
    const hasFunding = item.card.funding_rounds.length > 0;
    const hasSeries = (item.card.headcount_series?.points.length ?? 0) > 1;
    const openings = item.card.hiring?.openings?.value ?? null;
    rec.source(`Read the company record of ${item.name}`, record(`${item.name} · company record`), {
      detail: "funding, headcount and web traffic",
    });
    rec.status(`Reading job postings for ${item.name}`, {
      progress: { done: index + 1, total: 15 },
    });
    rec.call(
      openings ? `Job search returned ${openings} postings` : "Job search returned no postings",
      { endpoint: "job_search", credits: 1 },
      {
        gap: 900,
        counts: { postings: openings ?? 0, companies: 1 },
        highlights: openings ? [`${item.name} · ${openings} open roles`] : null,
      },
    );
    counts.enriched = index + 1;
    const round = item.card.funding_rounds[0];
    rec.finding(
      "company",
      `Enriched ${item.name}`,
      [
        {
          id: item.id,
          stage: "enriched",
          name: item.name,
          marks: {
            funding: hasFunding ? "found" : "none",
            headcount: hasSeries ? "found" : "none",
            hiring: openings ? "found" : "none",
          },
          highlight: round
            ? `${round.round_type?.replace(/_/g, " ") ?? "Round"} · ${round.date?.slice(0, 7) ?? "no date"}${openings ? ` · ${openings} open roles` : ""}`
            : openings
              ? `${openings} open roles`
              : "No funding record returned",
        },
      ],
      { ...counts },
    );
  });
  counts.enriched = 15;
  rec.finding("company", "Enriched 15 companies", [], { ...counts }, { gap: 300 });

  // Score: rank in one event. One company fails a must-have on its record.
  rec.at(step(".score"));
  rec.status("Applying your criteria to 15 companies", { gap: 700 });
  counts.scored = shortlist.filter((item) => !item.excluded).length;
  counts.dropped += shortlist.filter((item) => item.excluded).length;
  counts.in_play = 41 - shortlist.filter((item) => item.excluded).length;
  rec.finding(
    "company",
    `Ranked ${counts.scored} companies`,
    shortlist.map((item) =>
      item.excluded
        ? { id: item.id, stage: "dropped", name: item.name, reason: item.exclusion_reason ?? "Failed a must-have" }
        : {
            id: item.id,
            stage: "scored",
            name: item.name,
            fit: item.fit,
            assessable: item.assessable_pct / 100,
            rank: item.rank,
          },
    ),
    { ...counts },
    { gap: 1200 },
  );

  // Cards: one model read per company on the list.
  rec.at(step(".cards"));
  const ranked = shortlist.filter((item) => !item.excluded);
  ranked.forEach((item, index) => {
    rec.status("Writing why each company is on the list", {
      progress: { done: index + 1, total: ranked.length },
    });
    rec.model(`Explained ${item.name}`, 0.0007, { explained: 1 });
    const met = item.criterion_results.filter((result) => result.state === "pass").map((r) => r.label);
    rec.finding(
      "company",
      `Explained ${item.name}`,
      [
        {
          id: item.id,
          stage: "explained",
          name: item.name,
          why: met.length > 0 ? `Meets: ${met.slice(0, 3).join(" · ")}` : "No criterion could be assessed from the record",
        },
      ],
      { ...counts },
      { gap: 200 },
    );
  });
  return rec.events;
}

/* ───────────────────────── Investor search ───────────────────────── */

function investors(run: RunOut, { investorSearch }: FixtureSources): Activity[] {
  const step = (suffix: string) => run.steps.find((s) => s.key.endsWith(suffix)) ?? run.steps[0];
  const rec = new Recorder(run, run.steps[0]);
  const rounds = investorSearch.entries.flatMap((entry) =>
    entry.comparable_rounds.map((round) => ({ entry, round })),
  );
  const companies = [...new Map(rounds.map(({ round }) => [round.company_id, round.company_name])).entries()];

  rec.at(step(".comparables"));
  rec.status("Searching for comparable companies that raised money");
  rec.call(
    "Company search returned 40 companies",
    { endpoint: "company_search", credits: 6.5 },
    { detail: "India · warehousing and supply-chain software · Series A", counts: { returned: 40, new: 40 } },
  );
  rec.finding(
    "company",
    "Found 40 comparable companies",
    [
      ...companies.map(([id, name]) => ({ id: `cmp_${id}`, stage: "found", name })),
      { id: "cmp_morrow", stage: "found", name: "Morrow Docks (fixture)" },
      { id: "cmp_anchor", stage: "found", name: "Anchorline WMS (fixture)" },
      { id: "cmp_varuna", stage: "found", name: "Varuna Stockrooms (fixture)" },
    ],
    { found: 40 },
  );

  rec.at(step(".enrich"));
  rec.status("Reading funding rounds of 25 companies", { progress: { done: 0, total: 25 } });
  rec.call(
    "Enriched 25 companies",
    { endpoint: "company_enrich", credits: 50 },
    {
      detail: "funding rounds and investors",
      gap: 2600,
      counts: {
        requested: 25,
        returned: 25,
        with_funding: companies.length + 1,
        funding_rounds: rounds.length + 1,
        with_investors: companies.length + 1,
      },
      highlights: rounds.slice(0, 2).map(
        ({ round }) => `${round.company_name} · ${(round.round_type ?? "round").replace(/_/g, " ")} · ${round.date.slice(0, 7)}`,
      ),
    },
  );
  const seen = new Set<string>();
  const counts = { companies: 25, rounds: 0, rounds_dated: 0, investors: 0 };
  companies.forEach(([companyId, companyName], index) => {
    const own = rounds.filter(({ round }) => round.company_id === companyId);
    rec.source(`Read the funding record of ${companyName}`, record(`${companyName} · funding record`), {
      progress: { done: index + 1, total: 25 },
    });
    counts.rounds += own.length;
    counts.rounds_dated += own.length;
    for (const { entry } of own) seen.add(entry.investor_key);
    counts.investors = seen.size;
    rec.finding(
      "round",
      `Read ${own.length} funding ${own.length === 1 ? "round" : "rounds"} of ${companyName}`,
      own.map(({ entry, round }) => ({
        id: `rnd_${companyId}_${round.date}`,
        stage: "found",
        company: companyName,
        company_id: String(companyId),
        round: round.round_type,
        date: round.date,
        amount_usd: round.amount_usd,
        investors: [{ key: entry.investor_key, name: entry.investor_name }],
      })),
      { ...counts },
      { progress: { done: index + 1, total: 25 } },
    );
  });
  // One round with no date: counted, never ranked on.
  rec.source("Read the funding record of Morrow Docks (fixture)", record("Morrow Docks (fixture) · funding record"), {
    progress: { done: companies.length + 1, total: 25 },
  });
  counts.rounds += 1;
  counts.investors += 1;
  rec.finding(
    "round",
    "Read 1 funding round of Morrow Docks (fixture)",
    [
      {
        id: "rnd_morrow_undated",
        stage: "found",
        company: "Morrow Docks (fixture)",
        company_id: "cmp_morrow",
        round: "seed",
        date: null,
        amount_usd: null,
        investors: [{ key: "name:coastline angels (fixture)", name: "Coastline Angels (fixture)" }],
      },
    ],
    { ...counts },
    { progress: { done: 25, total: 25 } },
  );

  rec.at(step(".rank"));
  rec.status("Grouping investors and ranking by dated comparable rounds", { gap: 900 });
  rec.finding(
    "investor",
    `Ranked ${investorSearch.entries.length} investors`,
    investorSearch.entries.map((entry) => ({
      id: entry.investor_key,
      stage: "ranked",
      name: entry.investor_name,
      rank: entry.rank,
      comparable_rounds: entry.comparable_rounds.length,
      last_round_date: entry.latest_sector_investment_found,
    })),
    { investors: counts.investors, ranked: investorSearch.entries.length, not_ranked: 1 },
    { gap: 1200 },
  );
  return rec.events;
}

/* ───────────────────────── Verify and recheck ───────────────────────── */

function claimIdOf(step: StepOut): string | null {
  const [head, id] = step.key.split(":");
  return id && /(^|\.)(claim|facts)$/.test(head) ? id : null;
}

function evidenceSource(claim: ClaimOut): { source: ActivitySource; snippet: string | null } | null {
  const evidence = claim.evidence.find((e) => e.source.source_class !== "seller_document") ?? claim.evidence[0];
  if (!evidence) return null;
  const ref = evidence.source;
  const isWeb = /^https?:\/\//.test(ref.url_or_endpoint);
  if (ref.source_class === "seller_document" || ref.source_class === "seller_statement") {
    return {
      source: {
        type: "seller_document",
        domain: null,
        url: null,
        title: "Seller document · payroll summary",
        source_class: "seller_document",
        as_of: evidence.as_of,
        state: "read",
        reason: null,
      },
      snippet: null,
    };
  }
  return {
    source: {
      type: isWeb ? "web_page" : "crustdata_record",
      domain: isWeb ? domainOf(ref.url_or_endpoint) : null,
      url: isWeb ? ref.url_or_endpoint : null,
      title: ref.label,
      source_class: ref.source_class,
      as_of: evidence.as_of,
      state: "read",
      reason: null,
    },
    snippet: evidence.quote ? evidence.quote.slice(0, 200) : null,
  };
}

function verify(run: RunOut, { caseDetails }: FixtureSources): Activity[] {
  const detail = Object.values(caseDetails).find((d) => d.runs.some((r) => r.id === run.id));
  if (!detail) return [];
  const rec = new Recorder(run, run.steps[0]);
  const name = detail.identity.entity_name ?? "the company";
  const domain = detail.identity.keys.find((key) => key.key === "domain")?.value ?? null;
  const claimIds = run.steps.map(claimIdOf).filter((id): id is string => id !== null);
  const stage: Record<string, string> = {};
  const claimCounts = () => ({
    queued: Object.values(stage).filter((s) => s === "queued").length,
    checking: Object.values(stage).filter((s) => s === "checking").length,
    settled: Object.values(stage).filter((s) => s === "settled").length,
    not_checked: Object.values(stage).filter((s) => s === "not_checked").length,
  });
  const steps = [...run.steps].sort((a, b) => a.position - b.position);

  for (const step of steps) {
    rec.at(step);
    const claimId = claimIdOf(step);
    const claim = claimId ? detail.claims.find((c) => c.id === claimId) : undefined;

    if (step.key === "verify.identity") {
      rec.status(domain ? `Matching the domain ${domain}` : "Matching the name");
      const candidates = Math.max(detail.identity.candidates.length, 1);
      rec.call(
        `Company identify returned ${candidates} ${candidates === 1 ? "candidate" : "candidates"}`,
        { endpoint: "company_identify", credits: step.cost.crustdata_credits },
        { counts: { candidates } },
      );
      if (detail.identity.state === "confirmed") {
        rec.finding(
          "identity",
          "Identity confirmed",
          [
            {
              id: String(detail.identity.crustdata_company_id ?? "identity"),
              stage: "confirmed",
              name,
              domain,
              matched_keys: detail.identity.keys.map((key) => key.key),
            },
          ],
          { candidates },
          { detail: step.result ?? null },
        );
      } else {
        rec.finding(
          "identity",
          "More than one company matches",
          detail.identity.candidates.slice(0, 5).map((candidate) => ({
            id: String(candidate.crustdata_company_id),
            stage: "ambiguous",
            name: candidate.name,
            matched_keys: candidate.matching.map((key) => key.key),
          })),
          { candidates },
          { detail: step.result ?? null },
        );
        rec.notice(
          "identity_blocked",
          "The run stops at identity",
          "Checks start once one company is picked",
        );
      }
    } else if (step.key === "verify.registry") {
      rec.status("Searching public registry records");
      rec.call("Web search returned 6 results", { endpoint: "web_search", credits: 1 }, { counts: { hits: 6, news_hits: 0 } });
      rec.status("Reading registry-mirror.example");
      rec.call("Fetched 2 pages", { endpoint: "web_fetch", credits: 3 }, { counts: { requested: 2, read: 2, failed: 0 } });
      for (const [title, asOf] of [
        [`${name} · company master data`, "2016-03-14"],
        [`${name} · charges`, "2025-06-11"],
      ]) {
        rec.source("Read registry-mirror.example", {
          domain: "registry-mirror.example",
          url: "https://registry-mirror.example/company/harbourline-warehousing",
          title,
          source_class: "registry_mirror",
          as_of: asOf,
        });
      }
      rec.model("Extracted 4 dated facts from the registry pages", step.cost.llm_usd, { facts: 4, rejected_no_span: 1 });
    } else if (step.key === "verify.profile") {
      rec.status("Reading the company record");
      rec.call("Enriched 1 company", { endpoint: "company_enrich", credits: step.cost.crustdata_credits }, {
        detail: "funding, headcount and web traffic",
        counts: { requested: 1, returned: 1, with_funding: 1, funding_rounds: 1, with_headcount_series: 1 },
      });
      rec.source("Read the company record", { ...record(`${name} · company record`) }, { detail: "4 field groups" });
    } else if (step.key === "verify.people") {
      rec.status("Searching professional records");
      rec.call("Person search returned 6 people", { endpoint: "person_search", credits: step.cost.crustdata_credits }, {
        counts: { returned: 6, current_leadership: 6 },
      });
      rec.source("Read 6 leadership records", record(`${name} · people`), { detail: "6 leadership records" });
    } else if (step.key === "verify.jobs") {
      rec.status("Reading dated job postings");
      rec.call("Job search returned 10 postings", { endpoint: "job_search", credits: step.cost.crustdata_credits }, {
        counts: { postings: 10, companies: 1 },
      });
      rec.source("Read 10 job postings", record(`${name} · job postings`), { detail: "10 postings" });
    } else if (step.key.startsWith("claims.extract")) {
      rec.status("Reading the uploaded document", { progress: { done: 14, total: 14 } });
      rec.source("Read the uploaded document", {
        type: "seller_document",
        title: "Seller document · presentation",
        source_class: "seller_document",
      });
      rec.model("Read 8 claims from the uploaded presentation", step.cost.llm_usd, { claims: claimIds.length, pages: 14 });
      for (const id of claimIds) stage[id] = "queued";
      rec.finding(
        "claim",
        `Queued ${claimIds.length} claims`,
        claimIds.map((id) => ({
          id,
          stage: "queued",
          category: detail.claims.find((c) => c.id === id)?.category ?? null,
        })),
        claimCounts(),
      );
    } else if (claim && claimId) {
      const words = CATEGORY_WORDS[claim.category] ?? claim.category.replace(/_/g, " ");
      const ref = { type: "claim", id: claimId };
      if (step.state === "skipped_budget") {
        stage[claimId] = "not_checked";
        rec.notice("budget_reached", "Budget reached", "1 check was not run and is marked Not checked");
        rec.finding(
          "claim",
          "Claim not checked: budget reached",
          [{ id: claimId, stage: "not_checked", category: claim.category, status: "not_checked" }],
          claimCounts(),
          { detail: words, ref },
        );
        continue;
      }
      stage[claimId] = "checking";
      rec.finding("claim", `Checking: ${words}`, [{ id: claimId, stage: "checking", category: claim.category }], claimCounts(), { ref, gap: 300 });
      rec.status(`Checking: ${words}`, { ref });
      const found = evidenceSource(claim);
      const credits = step.cost.crustdata_credits;
      if (credits > 0) {
        rec.status("Searching public pages", { ref });
        rec.call("Web search returned 9 results", { endpoint: "web_search", credits: 1 }, { counts: { hits: 9, news_hits: 4 }, ref });
        if (credits > 1) {
          rec.call(`Fetched ${credits - 1} ${credits - 1 === 1 ? "page" : "pages"}`, { endpoint: "web_fetch", credits: credits - 1 }, {
            counts: { requested: credits, read: credits - 1, failed: 1 },
            ref,
          });
          rec.source("Could not read linkedin.com", {
            domain: "linkedin.com",
            url: null,
            source_class: "company_announcement",
            state: "failed",
            reason: "http_403",
          }, { ref, progress: { done: 1, total: credits } });
        }
      }
      if (found && found.source.type !== "seller_document") {
        rec.status(found.source.domain ? `Reading ${found.source.domain}` : "Reading the company record", { ref });
        rec.source(found.source.domain ? `Read ${found.source.domain}` : "Read the company record", found.source, { ref });
      }
      rec.model(`Extracted facts for the ${words} claim`, step.cost.llm_usd, { facts: found ? 2 : 0, rejected_no_span: found ? 0 : 1 }, { ref });
      const status = STEP_RESULT_STATUS[step.result ?? ""] ?? claim.status;
      stage[claimId] = "settled";
      const publicSource = found && found.source.type !== "seller_document" ? found : null;
      rec.finding(
        "claim",
        `Claim settled: ${status.replace(/_/g, " ")}`,
        [
          {
            id: claimId,
            stage: "settled",
            category: claim.category,
            status,
            previous_status: null,
            evidence_count: claim.evidence.length,
            snippet: status === "cannot_verify" ? null : (publicSource?.snippet ?? null),
            gap: GAP_SENTENCE[status] ?? null,
          },
        ],
        claimCounts(),
        { detail: words, ref, source: status === "cannot_verify" ? null : (publicSource?.source ?? null) },
      );
    } else if (step.key.endsWith(".events")) {
      rec.status("Searching news about the company");
      rec.call("Web search returned 12 results", { endpoint: "web_search", credits: 0, from_cache: true }, { counts: { hits: 12, news_hits: 7 } });
      detail.events.forEach((event, index) => {
        const url = event.evidence?.source.url_or_endpoint ?? "";
        const host = domainOf(url);
        if (host) {
          rec.status(`Reading ${host}`);
          rec.source(`Read ${host}`, {
            domain: host,
            url,
            title: event.evidence?.source.label ?? null,
            source_class: event.evidence?.source.source_class ?? "news",
            as_of: event.event_date,
          });
        }
        rec.finding(
          "event",
          "Found a dated event",
          [{ id: event.id, stage: "found", date: event.event_date, event_kind: event.kind, title: event.title, domain: host }],
          { events: index + 1 },
        );
      });
      rec.model(`Extracted ${detail.events.length} dated facts`, step.cost.llm_usd, { facts: detail.events.length, rejected_no_span: 1 });
    } else if (step.key.endsWith(".comparables")) {
      rec.status("Searching for comparable companies");
      rec.call("Company search returned 2 companies", { endpoint: "company_search", credits: step.cost.crustdata_credits }, {
        counts: { returned: 2, new: 2 },
      });
      const peers = detail.comparables?.companies ?? [];
      rec.finding(
        "peer",
        `Found ${peers.length} comparable ${peers.length === 1 ? "company" : "companies"}`,
        peers.map((peer) => ({ id: String(peer.crustdata_company_id), stage: "found", name: peer.name })),
        { peers: peers.length },
      );
    } else if (step.key.startsWith("evaluate")) {
      rec.status("Applying the screening rules", { gap: 800 });
      const settled = detail.claims.filter((c) => c.status !== "not_checked").length;
      rec.finding(
        "assessment",
        `Assessment written: ${(step.result ?? "").replace(/^./, (c) => c.toUpperCase())}`,
        [
          {
            id: `asm_${run.id}`,
            stage: "written",
            version: Number(/version (\d+)/.exec(step.label)?.[1] ?? 1),
            disposition: (step.result ?? "").replace(/ /g, "_"),
            previous_disposition: run.kind === "recheck" ? (step.result ?? "").replace(/ /g, "_") : null,
          },
        ],
        { supported: detail.claims.filter((c) => c.status === "supported").length, open: detail.claims.length - settled },
        { gap: 900 },
      );
    }
  }
  return rec.events;
}

function recheck(run: RunOut, { caseDetails }: FixtureSources): Activity[] {
  const detail = Object.values(caseDetails).find((d) => d.runs.some((r) => r.id === run.id));
  if (!detail) return [];
  const rec = new Recorder(run, run.steps[0]);
  for (const step of [...run.steps].sort((a, b) => a.position - b.position)) {
    rec.at(step);
    const claimId = claimIdOf(step);
    const claim = claimId ? detail.claims.find((c) => c.id === claimId) : undefined;
    if (step.key.startsWith("claims.extract")) {
      rec.status("Reading the uploaded document", { progress: { done: 1, total: 1 } });
      rec.source("Read the uploaded document", {
        type: "seller_document",
        title: "Seller document · payroll summary",
        source_class: "seller_document",
      });
      if (claimId === null) {
        const targets = run.steps.map(claimIdOf).filter((id): id is string => id !== null);
        rec.finding(
          "claim",
          `Queued ${targets.length} ${targets.length === 1 ? "claim" : "claims"}`,
          targets.map((id) => ({
            id,
            stage: "queued",
            category: detail.claims.find((c) => c.id === id)?.category ?? null,
            previous_status: "cannot_verify",
          })),
          { queued: targets.length, checking: 0, settled: 0, not_checked: 0 },
        );
      }
    } else if (claim && claimId) {
      const words = CATEGORY_WORDS[claim.category] ?? claim.category;
      const ref = { type: "claim", id: claimId };
      rec.finding("claim", `Checking: ${words}`, [{ id: claimId, stage: "checking", category: claim.category, previous_status: "cannot_verify" }], { queued: 0, checking: 1, settled: 0, not_checked: 0 }, { ref });
      rec.status("Reading the uploaded document", { ref });
      rec.model(`Extracted 1 fact for the ${words} claim`, step.cost.llm_usd, { facts: 1, rejected_no_span: 0 }, { ref });
      rec.status(`Applying status rules to ${words}`, { ref });
      rec.finding(
        "claim",
        "Claim settled: supported",
        [
          {
            id: claimId,
            stage: "settled",
            category: claim.category,
            status: STEP_RESULT_STATUS[step.result ?? ""] ?? claim.status,
            previous_status: "cannot_verify",
            evidence_count: claim.evidence.length,
            snippet: null,
            gap: null,
          },
        ],
        { queued: 0, checking: 0, settled: 1, not_checked: 0 },
        {
          detail: words,
          ref,
          source: {
            type: "seller_document",
            domain: null,
            url: null,
            title: "Seller document · payroll summary",
            source_class: "seller_document",
            as_of: "2026-10-31",
            state: "read",
            reason: null,
          },
        },
      );
    } else if (step.key.startsWith("evaluate")) {
      rec.status("Applying the screening rules", { gap: 800 });
      const disposition = (step.result ?? "").replace(/ /g, "_");
      rec.finding(
        "assessment",
        `Assessment written: ${(step.result ?? "").replace(/^./, (c) => c.toUpperCase())}`,
        [{ id: `asm_${run.id}`, stage: "written", version: 2, disposition, previous_disposition: disposition }],
        { supported: detail.claims.filter((c) => c.status === "supported").length, open: 0 },
        { gap: 900 },
      );
    }
  }
  return rec.events;
}

/** The recorded activity of one fixture run. Empty when the run kind has no recording. */
export function buildFixtureActivities(run: RunOut, sources: FixtureSources): Activity[] {
  if (run.steps.length === 0) return [];
  switch (run.kind) {
    case "discover":
      return discover(run, sources);
    case "investor_discover":
      return investors(run, sources);
    case "verify":
      return verify(run, sources);
    case "recheck":
    case "evaluate":
      return recheck(run, sources);
    default:
      return [];
  }
}
