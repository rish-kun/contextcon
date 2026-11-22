// Run with `pnpm --filter web test` (Node's built-in runner; Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { appendActivities, deriveView, visibleEvents } from "./activity-store.ts";
import { RevealQueue } from "./reveal-queue.ts";

function fakeClock() {
  let now = 0;
  let timers = [];
  return {
    now: () => now,
    setTimer: (fn, ms) => {
      const timer = { fn, at: now + ms };
      timers.push(timer);
      return timer;
    },
    clearTimer: (timer) => {
      timers = timers.filter((t) => t !== timer);
    },
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const next = timers.filter((t) => t.at <= end).sort((a, b) => a.at - b.at)[0];
        if (!next) break;
        timers = timers.filter((t) => t !== next);
        now = next.at;
        next.fn();
      }
      now = end;
    },
  };
}

const base = { run_id: "r", step_id: "s1", step_key: "discover.search", at: "2026-11-22T11:00:00Z", detail: null, progress: null, source: null, call: null, counts: null, highlights: null, items: null, subject: null, code: null, ref: null };

test("reveal queue shows one item per interval", () => {
  const clock = fakeClock();
  const queue = new RevealQueue(clock);
  for (const seq of [1, 2, 3]) queue.push(seq);
  assert.equal(queue.snapshot().upto, 0);
  clock.advance(150);
  assert.equal(queue.snapshot().upto, 1);
  clock.advance(300);
  assert.equal(queue.snapshot().upto, 3);
  assert.equal(queue.snapshot().settledUpto, 0);
});

test("reveal queue is never more than the delay limit behind", () => {
  const clock = fakeClock();
  const queue = new RevealQueue(clock);
  for (let seq = 1; seq <= 24; seq += 1) queue.push(seq);
  // 10 fit inside 1.5 s; the 14 older ones appear at once, settled.
  const snapshot = queue.snapshot();
  assert.equal(snapshot.upto, 14);
  assert.equal(snapshot.settledUpto, 14);
  assert.deepEqual(snapshot.skipped, { count: 14, seq: 14 });
  clock.advance(1500);
  assert.equal(queue.snapshot().upto, 24);
});

test("backlog is settled at once, pause holds, flush shows everything", () => {
  const clock = fakeClock();
  const queue = new RevealQueue(clock);
  queue.push(1, true);
  assert.deepEqual([queue.snapshot().upto, queue.snapshot().settledUpto], [1, 1]);
  queue.setPaused(true);
  queue.push(2);
  queue.push(3);
  clock.advance(1000);
  assert.equal(queue.snapshot().upto, 1);
  assert.equal(queue.snapshot().held, 2);
  queue.flush();
  assert.deepEqual([queue.snapshot().upto, queue.snapshot().settledUpto, queue.snapshot().held], [3, 3, 0]);
});

test("reduced motion reveals one settled batch per 400 ms", () => {
  const clock = fakeClock();
  const queue = new RevealQueue({ ...clock, reduced: true });
  queue.push(1);
  queue.push(2);
  clock.advance(399);
  assert.equal(queue.snapshot().upto, 0);
  clock.advance(1);
  assert.deepEqual([queue.snapshot().upto, queue.snapshot().settledUpto], [2, 2]);
});

test("activities are appended once and kept in seq order", () => {
  const a = { ...base, seq: 1, kind: "status", label: "A" };
  const b = { ...base, seq: 2, kind: "status", label: "B" };
  const log = appendActivities(appendActivities([], [b]), [a, b]);
  assert.deepEqual(log.map((e) => e.seq), [1, 2]);
  assert.equal(appendActivities(log, [a]), log);
});

test("the view adds up call counts and merges company rows by id", () => {
  const call = (seq, fresh, credits) => ({
    ...base, seq, kind: "call", label: "Company search",
    call: { provider: "crustdata", endpoint: "company_search", ok: true, error: null, from_cache: false, attempts: 1, duration_ms: 1, credits, usd: null, credits_total: credits * seq, usd_total: 0 },
    counts: { returned: fresh, new: fresh },
  });
  const view = deriveView([
    { ...base, seq: 1, kind: "status", label: "Searching companies" },
    call(2, 24, 2),
    { ...base, seq: 3, kind: "finding", label: "Found", subject: "company", counts: { found: 24 }, items: [{ id: "c1", stage: "found", name: "One", headcount: 40 }] },
    call(4, 16, 2),
    { ...base, seq: 5, kind: "finding", label: "Scored", subject: "company", step_key: "discover.score", counts: { scored: 1 }, items: [{ id: "c1", stage: "scored", fit: 82, rank: 1 }] },
    { ...base, seq: 6, kind: "source", label: "Read the uploaded document", source: { type: "seller_document", domain: null, url: null, title: "Seller document · presentation", source_class: "seller_document", as_of: null, state: "read", reason: null } },
  ]);
  const row = view.tally.rows.get("company_search");
  assert.equal(row.calls, 2);
  assert.equal(row.counts.new, 40);
  assert.equal(view.tally.credits, 4);
  assert.equal(view.cost.credits, 8);
  const company = view.companies.rows[0];
  assert.deepEqual([company.name, company.headcount, company.fit, company.stage, company.firstSeq], ["One", 40, 82, "scored", 3]);
  assert.equal(view.companiesScoredStep, "discover.score");
  // An uploaded document is never a ticker row, and never the "now" line.
  assert.equal(view.sources.length, 0);
  assert.equal(view.now.label, "Company search");
  assert.equal(view.steps.get("discover.search").document, "Seller document · presentation");
});

test("a claim's stage follows its findings and its sub-line follows its ref", () => {
  const ref = { type: "claim", id: "k1" };
  const view = deriveView([
    { ...base, seq: 1, kind: "finding", label: "Queued", subject: "claim", items: [{ id: "k1", stage: "queued", category: "funding" }] },
    { ...base, seq: 2, kind: "finding", label: "Checking", subject: "claim", items: [{ id: "k1", stage: "checking" }], ref },
    { ...base, seq: 3, kind: "status", label: "Reading example.org", ref, progress: { done: 2, total: 4 } },
  ]);
  const claim = view.claims.get("k1");
  assert.deepEqual([claim.stage, claim.category, claim.line, claim.progress.done], ["checking", "funding", "Reading example.org", 2]);
});

test("paced regions are cut at their watermark; the rest is shown in full", () => {
  const events = [
    { ...base, seq: 1, kind: "status", label: "A" },
    { ...base, seq: 2, kind: "finding", label: "F", subject: "company", items: [] },
    { ...base, seq: 3, kind: "status", label: "B" },
  ];
  assert.deepEqual(visibleEvents(events, { sources: 0, findings: 0 }).map((e) => e.seq), [1, 3]);
});

/* The API's own recorded fixture streams, replayed through the store. */
const fixtures = JSON.parse(
  (await import("node:fs")).readFileSync(new URL("../api/fixtures.json", import.meta.url), "utf8"),
);

test("the Discover fixture stream builds candidates, then ranks them", () => {
  const events = fixtures.activity["fx-run-discover"];
  const view = deriveView(events);
  assert.equal(view.total, events.length);
  assert.equal(view.companies.counts.found, 48);
  assert.equal(view.companiesScoredStep, "discover.score");
  const kestrel = view.companies.rows.find((row) => row.id === "fx-sl-kestrel");
  assert.deepEqual([kestrel.rank, kestrel.fit, kestrel.location, kestrel.marks.funding], [1, 82, "Pune, India", "found"]);
  assert.ok(view.companies.rows.some((row) => row.stage === "dropped" && row.reason));
  // Before the score event there is no rank on any row.
  const before = deriveView(events.filter((event) => event.step_key !== "discover.score" && event.step_key !== "discover.cards"));
  assert.equal(before.companiesScoredSeq, null);
  assert.ok(before.companies.rows.every((row) => row.rank == null && row.fit == null));
  assert.equal(view.tally.rows.get("company_search").counts.new, 48);
});

test("the investor fixture stream groups rounds by investor and ranks once", () => {
  const view = deriveView(fixtures.activity["fx-run-investors"]);
  assert.equal(view.investors.length, 3);
  assert.ok(view.investors.every((investor) => investor.ranked && investor.rounds.length === 1));
  assert.equal(view.investorsRankedStep, "investors.rank");
  assert.deepEqual(view.investors.map((investor) => investor.rank).sort(), [1, 2, 3]);
});

test("the Verify fixture stream settles claims and keeps documents out of the ticker", () => {
  const events = fixtures.activity["fx-run-verify"];
  const view = deriveView(events);
  const stages = [...view.claims.values()].map((claim) => claim.stage);
  assert.equal(stages.filter((stage) => stage === "settled").length, 7);
  assert.equal(stages.filter((stage) => stage === "queued").length, 1);
  assert.equal(view.identity.stage, "confirmed");
  assert.equal(view.assessment.items[0].disposition, "investigate_further");
  assert.ok(view.sources.every((row) => row.source.type !== "seller_document"));
  assert.equal(view.sourceCounts.failed, 1);
  // Midway: the first claim has a page read for it and is not settled yet.
  const midway = deriveView(events.filter((event) => event.seq <= 22));
  const first = midway.claims.get("fx-claim-1");
  assert.deepEqual([first.stage, first.line], ["checking", "Read registry.example"]);
  assert.equal(midway.sources.filter((row) => row.claimId === "fx-claim-1").length, 1);
});

test("a recheck event with no ref is tied to its claim by the step key", () => {
  const view = deriveView(fixtures.activity["fx-run-recheck"]);
  const claim = view.claims.get("fx-claim-2");
  assert.deepEqual([claim.stage, claim.status, claim.previousStatus], ["settled", "supported", "cannot_verify"]);
  assert.equal(view.sources.length, 0);
  assert.ok(view.steps.get("claims.extract_text:fx-doc-payroll").document);
});
