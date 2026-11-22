import type { RunOut } from "./client";

/**
 * The run with its settled spend raised to at least the sum of its steps' spend.
 *
 * Step events arrive before the next `run` event, so a live header that read only
 * `run.cost` lagged behind the step rows (the "0 of 60 credits" bug). The server's run
 * total also counts spend recorded outside a step, so the larger of the two wins.
 * Credits and model dollars stay separate currencies.
 */
export function withStepSpend(run: RunOut): RunOut {
  if (run.steps.length === 0) return run;
  let credits = 0;
  let usd = 0;
  let unknown = 0;
  for (const step of run.steps) {
    credits += step.cost.crustdata_credits;
    usd += step.cost.llm_usd;
    unknown += step.cost.unknown_cost_calls;
  }
  const cost = run.cost;
  if (
    credits <= cost.crustdata_credits &&
    usd <= cost.llm_usd &&
    unknown <= cost.unknown_cost_calls
  ) {
    return run;
  }
  return {
    ...run,
    cost: {
      ...cost,
      crustdata_credits: Math.max(cost.crustdata_credits, credits),
      llm_usd: Math.max(cost.llm_usd, usd),
      unknown_cost_calls: Math.max(cost.unknown_cost_calls, unknown),
    },
  };
}
