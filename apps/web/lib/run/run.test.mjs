// Run with `pnpm --filter web test` (Node's built-in runner; Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { appendActivities, deriveView, visibleEvents } from "./activity-store.ts";
import { isPublicAddress, publicHost } from "./favicon-rules.ts";
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

test("the favicon proxy only asks public hosts", () => {
  assert.equal(publicHost("Example.COM."), "example.com");
  for (const bad of ["localhost", "10.0.0.1", "[::1]", "intranet", "site.local", "foo.example", "a..b.com", "evil.com/path", "evil.com:8080", "metadata.google.internal", ""]) {
    assert.equal(publicHost(bad), null, bad);
  }
  for (const address of ["127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "::1", "fd00::1", "fe80::1", "::ffff:10.0.0.1"]) {
    assert.equal(isPublicAddress(address), false, address);
  }
  assert.equal(isPublicAddress("93.184.216.34"), true);
  assert.equal(isPublicAddress("2606:2800:220:1:248:1893:25c8:1946"), true);
});
