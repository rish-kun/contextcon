// Run with `node --test` (Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { organiseChanges, shortPolicyPair } from "./change-groups.ts";

const policy = { kind: "policy", from: "2026-11-22.2", to: "2026-11-22.3" };
const claim = (n, before, after, cause, evidence = []) => ({
  kind: "claim_status",
  claim_number: n,
  claim_text: `claim ${n}`,
  before,
  after,
  reason: "",
  cause,
  evidence,
});

test("a policy update that touched several claims is one group, counted by status", () => {
  const out = organiseChanges([
    claim(1, null, "cannot_verify", policy),
    claim(2, null, "cannot_verify", policy),
    claim(4, null, "contradicted", { kind: "evidence" }, [{ source: {} }]),
    claim(5, null, "contradicted", policy),
  ]);
  assert.equal(out.groups.length, 1);
  assert.equal(out.groups[0].allFirst, true);
  assert.deepEqual(out.groups[0].counts, [
    { status: "contradicted", count: 1 },
    { status: "cannot_verify", count: 2 },
  ]);
  assert.deepEqual(out.groups[0].changes.map((c) => c.claim_number), [5, 1, 2]);
  assert.deepEqual(out.claims.map((c) => c.claim_number), [4]);
});

test("evidence-driven claims stay single and the decision-relevant ones lead", () => {
  const ev = [{ source: {} }];
  const out = organiseChanges([
    claim(1, "cannot_verify", "partially_corroborated", { kind: "evidence" }, ev),
    { kind: "value", label: "Evidence sufficiency", before: "50%", after: "75%" },
    claim(2, "cannot_verify", "supported", { kind: "evidence" }, ev),
    claim(3, "supported", "contradicted", { kind: "evidence" }, ev),
    { kind: "disposition", before: "investigate_further", after: "prioritise", reason: "r" },
  ]);
  assert.equal(out.disposition.length, 1);
  assert.equal(out.judgments.length, 1);
  assert.deepEqual(out.claims.map((c) => c.claim_number), [3, 2, 1]);
  assert.equal(out.groups.length, 0);
});

test("one policy-caused claim is a row, not a group of one", () => {
  const out = organiseChanges([claim(1, null, "cannot_verify", policy)]);
  assert.equal(out.groups.length, 0);
  assert.equal(out.claims.length, 1);
});

test("policy versions of one month are shortened to their tails", () => {
  assert.deepEqual(shortPolicyPair("2026-11-22.2", "2026-11-22.3"), ["22.2", "22.3"]);
  assert.deepEqual(shortPolicyPair("2026-10-30.1", "2026-11-22.3"), ["2026-10-30.1", "2026-11-22.3"]);
  assert.deepEqual(shortPolicyPair("1.0", "1.1"), ["1.0", "1.1"]);
});
