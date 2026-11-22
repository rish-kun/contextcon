// Run with `node --test` (Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { effectOf, flipItemsFor, requestRow, summarise } from "./request-effect.ts";

const outcome = (disposition) => ({ hypothetical: true, disposition, rule: "r", reasons: [], changes_disposition: false });
const flipItem = (over) => ({
  id: "claim:c1",
  kind: "claim",
  claim_id: "c1",
  decision_blocker: false,
  disqualifier_risk: false,
  flips_alone: false,
  settle_with: [],
  if_supported: outcome("investigate_further"),
  if_contradicted: outcome("investigate_further"),
  est_effort: "medium",
  ...over,
});
const flipOf = (items, over = {}) => ({
  current: "investigate_further",
  target: "prioritise",
  ceiling: outcome("prioritise"),
  minimum_evidence: null,
  items,
  ...over,
});
const doc = (over) => ({ id: "d1", document: "Term sheet", claim_ids: ["c1"], group: "needed", ...over });

test("a blocker that needs the others moves to the target with them", () => {
  const item = flipItem({ decision_blocker: true });
  assert.deepEqual(effectOf(item, flipOf([item])), {
    kind: "moves",
    from: "investigate_further",
    to: "prioritise",
    withOthers: true,
  });
});

test("a blocker that flips alone takes its own supported outcome", () => {
  const item = flipItem({ decision_blocker: true, flips_alone: true, if_supported: outcome("prioritise") });
  assert.deepEqual(effectOf(item, flipOf([item])), {
    kind: "moves",
    from: "investigate_further",
    to: "prioritise",
    withOthers: false,
  });
});

test("an answer that can rule the case out shows both branches", () => {
  const item = flipItem({ decision_blocker: true, if_contradicted: outcome("deprioritise") });
  const effect = effectOf(item, flipOf([item]));
  assert.equal(effect.kind, "branches");
  assert.deepEqual(effect.holds, { to: "prioritise", withOthers: true });
  assert.deepEqual(effect.fails, { to: "deprioritise", withOthers: false });
});

test("a conditional item whose answers change nothing stays put", () => {
  const item = flipItem({ conditional_action: "If it shows X the criterion passes; otherwise it fails." });
  assert.deepEqual(effectOf(item, flipOf([item])), { kind: "stays", at: "investigate_further" });
});

test("a document matches by claim or by name, blockers first", () => {
  const byName = flipItem({ id: "criterion:k", kind: "criterion", claim_id: null, settle_with: ["Term sheet"], decision_blocker: true });
  const byClaim = flipItem({});
  const other = flipItem({ id: "claim:c9", claim_id: "c9" });
  assert.deepEqual(
    flipItemsFor(doc({}), flipOf([byClaim, other, byName])).map((entry) => entry.id),
    ["criterion:k", "claim:c1"],
  );
});

test("a row without an analysis item carries no effect or effort", () => {
  assert.deepEqual(requestRow(doc({ claim_ids: ["zz"] }), flipOf([flipItem({})])), {
    item: doc({ claim_ids: ["zz"] }),
    effect: null,
    effort: null,
    condition: null,
  });
  assert.equal(requestRow(doc({}), null).effect, null);
});

test("the summary counts the needed documents and reads the ceiling", () => {
  const list = { items: [doc({}), doc({ id: "d2", group: "also_helpful" })] };
  assert.deepEqual(summarise(list, flipOf([])), {
    total: 2,
    critical: 1,
    current: "investigate_further",
    ifAllClean: "prioritise",
  });
  assert.deepEqual(summarise(list, null), { total: 2, critical: null, current: null, ifAllClean: null });
});
