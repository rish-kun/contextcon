// Run with `node --test` (Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { deriveView } from "../../lib/run/activity-store.ts";
import { claimLiveState } from "./claim-live-state.ts";

const step = (id, state, position, detail = null) => ({ id: `s-${id}`, key: `checks.claim:${id}`, state, position, detail, label: "Check", result: null });
const detail = (identity, statuses) => ({
  identity: { state: identity },
  claims: Object.entries(statuses).map(([id, status]) => ({ id, status })),
});
const base = { run_id: "r", step_id: null, step_key: null, at: "2026-11-22T11:00:00Z", detail: null, progress: null, source: null, call: null, counts: null, highlights: null, items: null, subject: null, code: null, ref: null };
const live = (claimId, { identity = "confirmed", statuses = { a: "not_checked", b: "not_checked", c: "not_checked" }, steps = [], events = [], runActive = true, kind = "verify" } = {}) =>
  claimLiveState(claimId, { detail: detail(identity, statuses), run: { kind, steps }, runActive, view: deriveView(events), events, settledSeq: 0 });

test("a claim is Checking only when its own step is running", () => {
  const steps = [step("a", "running", 1, "Checking: funding"), step("b", "pending", 2), step("c", "pending", 3)];
  assert.equal(live("a", { steps }).phase, "gathering");
  assert.equal(live("a", { steps }).line, "Checking: funding");
  assert.equal(live("a", { steps }).detailed, false);
  assert.deepEqual([live("b", { steps }).phase, live("b", { steps }).ahead], ["queued", 1]);
  assert.deepEqual([live("c", { steps }).phase, live("c", { steps }).ahead], ["queued", 2]);
});

test("with identity open, a claim waits and never says Checking", () => {
  const steps = [{ id: "i", key: "verify.identity", state: "running", position: 0, detail: "Matching the name" }];
  const waiting = live("a", { identity: "ambiguous", steps });
  assert.deepEqual([waiting.phase, waiting.identityRunning, waiting.line], ["waiting_identity", true, "Matching the name"]);
  const blocked = live("a", { identity: "ambiguous", steps: [{ ...steps[0], state: "done" }] });
  assert.deepEqual([blocked.phase, blocked.identityRunning], ["waiting_identity", false]);
});

test("no run, or a run that does not touch the claim, leaves the stored state", () => {
  assert.equal(live("a", { runActive: false }), null);
  assert.equal(live("a", { kind: "recheck" }), null);
  assert.equal(live("a", { statuses: { a: "supported" } }), null);
  // A run with no step for the claim says nothing about it, even a verify run.
  assert.equal(live("a"), null);
});

test("claim-scoped events move the phase and collect what was read", () => {
  const ref = { type: "claim", id: "a" };
  const steps = [step("a", "running", 1)];
  const source = { type: "web_page", domain: "example.org", url: "https://example.org/a", title: "Series A reported", source_class: "news", as_of: "2024-02-09", state: "read", reason: null };
  const events = [
    { ...base, seq: 1, kind: "finding", label: "Checking", subject: "claim", items: [{ id: "a", stage: "checking", category: "funding" }], ref },
    { ...base, seq: 2, kind: "status", label: "Searching news", ref },
  ];
  assert.equal(live("a", { steps, events }).phase, "gathering");
  events.push({ ...base, seq: 3, kind: "source", label: "Read example.org", source, ref });
  const reading = live("a", { steps, events });
  assert.deepEqual([reading.phase, reading.sources.length, reading.facts[0].asOf, reading.detailed], ["reading", 1, "2024-02-09", true]);
  events.push({ ...base, seq: 4, kind: "model", label: "Extracted 2 facts", counts: { facts: 2, rejected_no_span: 1 }, ref });
  const deciding = live("a", { steps, events });
  assert.deepEqual([deciding.phase, deciding.factCount, deciding.rejected], ["deciding", 2, 1]);
  events.push({ ...base, seq: 5, kind: "finding", label: "Settled", subject: "claim", source, items: [{ id: "a", stage: "settled", status: "conflicting_evidence", snippet: "closed its Series A" }], ref });
  const settled = live("a", { steps, events });
  assert.deepEqual([settled.phase, settled.status, settled.evidence.snippet, settled.fresh], ["settled", "conflicting_evidence", "closed its Series A", true]);
});

test("a re-check step with a suffix is still this claim's step", () => {
  const done = { ...step("a", "done", 1) };
  const again = { ...step("a", "running", 5, "Checking: funding"), id: "s-a2", key: "checks.claim:a@2" };
  const deferred = { ...step("b", "pending", 6), key: "checks.claim:b~1" };
  const state = live("a", { statuses: { a: "cannot_verify", b: "not_checked" }, steps: [done, again, deferred] });
  assert.deepEqual([state.phase, state.line], ["gathering", "Checking: funding"]);
  assert.deepEqual([live("b", { steps: [done, again, deferred] }).phase, live("b", { steps: [done, again, deferred] }).ahead], ["queued", 1]);
});

test("a replayed checking finding says nothing once the run has ended", () => {
  const ref = { type: "claim", id: "a" };
  const events = [{ ...base, seq: 1, kind: "finding", label: "Checking", subject: "claim", items: [{ id: "a", stage: "checking" }], ref }];
  assert.equal(live("a", { events, runActive: false }), null);
  assert.equal(live("a", { events, runActive: false, steps: [step("a", "running", 1)] }), null);
  // While the run is going and no step exists yet, the finding is all there is.
  assert.equal(live("a", { events }).phase, "gathering");
});

test("an earlier attempt's settled finding does not mask the check running now", () => {
  const ref = { type: "claim", id: "a" };
  const first = step("a", "done", 1);
  const again = { ...step("a", "running", 5, "Checking: funding"), id: "s-a2", key: "checks.claim:a@2" };
  const events = [
    { ...base, seq: 1, kind: "source", label: "Read example.org", step_key: "checks.claim:a", ref, source: { type: "web_page", domain: "example.org", url: "https://example.org/a", title: "Old", source_class: "news", as_of: null, state: "read", reason: null } },
    { ...base, seq: 2, kind: "finding", label: "Settled", subject: "claim", step_key: "checks.claim:a", items: [{ id: "a", stage: "settled", status: "cannot_verify" }], ref },
  ];
  const state = live("a", { statuses: { a: "cannot_verify" }, steps: [first, again], events });
  assert.deepEqual([state.phase, state.line, state.sources.length], ["gathering", "Checking: funding", 0]);
  // The same finding stands once its own step is the latest.
  assert.equal(live("a", { statuses: { a: "cannot_verify" }, steps: [first], events }).phase, "settled");
});
