// Run with `pnpm --filter web test` (Node's built-in runner; Node strips the TS types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { withStepSpend } from "./run-cost.ts";

const cost = (credits, usd = 0, unknown = 0) => ({
  crustdata_credits: credits,
  llm_usd: usd,
  input_tokens: 0,
  output_tokens: 0,
  unknown_cost_calls: unknown,
});
const run = (runCost, stepCosts) => ({
  id: "r",
  cost: runCost,
  steps: stepCosts.map((c, i) => ({ id: `s${i}`, position: i, cost: c })),
});

test("a live header that lags the steps shows the steps' spend", () => {
  // The bug: "0 of 60 credits" while the step rows already showed 4 + 3 cr.
  const out = withStepSpend(run(cost(0), [cost(4), cost(3, 0.01, 1)]));
  assert.equal(out.cost.crustdata_credits, 7);
  assert.equal(out.cost.llm_usd, 0.01);
  assert.equal(out.cost.unknown_cost_calls, 1);
});

test("the server total wins when it already covers the steps", () => {
  const input = run(cost(9), [cost(4), cost(3)]);
  assert.equal(withStepSpend(input), input);
});

test("a run event without steps is left alone", () => {
  const input = run(cost(2), []);
  assert.equal(withStepSpend(input), input);
});
