/**
 * Fixture mode only: `?state=empty|budget|failed|running` on a search page reshapes the
 * fixture search so each state of the screen can be opened and reviewed without a
 * backend. Never applied outside `NEXT_PUBLIC_API_MODE=fixtures`.
 */
import { type InvestorSearchOut, isFixtureMode } from "@/lib/api/client";

export const FIXTURE_STATES = ["empty", "budget", "failed", "running"] as const;
export type FixtureState = (typeof FIXTURE_STATES)[number];

export function parseFixtureState(value: string | undefined): FixtureState | null {
  if (!isFixtureMode) return null;
  return FIXTURE_STATES.find((state) => state === value) ?? null;
}

const NO_COST = {
  crustdata_credits: 0,
  llm_usd: 0,
  input_tokens: 0,
  output_tokens: 0,
  unknown_cost_calls: 0,
};

export function applyFixtureState(
  search: InvestorSearchOut,
  state: FixtureState | null,
): InvestorSearchOut {
  const run = search.run;
  if (!state || state === "running" || !run) return search;
  const last = run.steps.length - 1;

  if (state === "empty") {
    return {
      ...search,
      entries: [],
      run: {
        ...run,
        steps: run.steps.map((s, i) => (i === last ? { ...s, result: "0 investors" } : s)),
      },
    };
  }

  if (state === "budget") {
    const first = run.steps[0]?.cost.crustdata_credits ?? 0;
    return {
      ...search,
      run: {
        ...run,
        cost: { ...run.cost, crustdata_credits: run.budget_credits },
        steps: run.steps.map((s, i) =>
          i === 1
            ? {
                ...s,
                result: "18 of 40 companies read before the budget was reached",
                cost: { ...s.cost, crustdata_credits: run.budget_credits - first },
              }
            : s,
        ),
      },
    };
  }

  return {
    ...search,
    status: "failed",
    entries: [],
    run: {
      ...run,
      state: "failed",
      error: "TimeoutError",
      cost: { ...run.cost, crustdata_credits: run.steps[0]?.cost.crustdata_credits ?? 0 },
      steps: run.steps.map((s, i) => {
        if (i === 0) return s;
        if (i === 1) {
          return { ...s, state: "failed", result: null, error: "TimeoutError", cost: NO_COST };
        }
        return { ...s, state: "pending", result: null, cost: NO_COST, started_at: null };
      }),
    },
  };
}
