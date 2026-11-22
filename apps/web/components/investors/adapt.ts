/**
 * Turns API run shapes into the props the shared run and cost components take.
 * Crustdata credits and model dollars stay two separate figures all the way through.
 */
import type { RunOut, StepOut } from "@/lib/api/client";
import { withStepSpend } from "@/lib/api/run-cost";
import { RUN_KIND_LABEL } from "@/lib/labels";
import type { CaseCost, Run, RunStep } from "@/lib/types";

export const isTerminal = (run: RunOut) => run.state === "done" || run.state === "failed";

/** Seconds between creation and finish. Null while the run is still going. */
export function finishedSeconds(run: RunOut): number | null {
  if (!run.finished_at) return null;
  const seconds = (Date.parse(run.finished_at) - Date.parse(run.created_at)) / 1000;
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null;
}

function toStep(step: StepOut): RunStep {
  return {
    id: step.id,
    label: step.label,
    status: step.state,
    detail: step.detail,
    result: step.result,
    credits_used: step.cost.crustdata_credits,
    model_usd: step.cost.llm_usd > 0 ? step.cost.llm_usd : null,
    from_cache: step.from_cache,
    error: step.error,
  };
}

export function toRun(run: RunOut, elapsedSeconds: number): Run {
  return {
    id: run.id,
    kind: run.kind,
    subject: run.subject,
    status: run.state === "done" ? "finished" : run.state === "failed" ? "failed" : "running",
    steps: [...run.steps].sort((a, b) => a.position - b.position).map(toStep),
    elapsed_seconds: elapsedSeconds,
    credits_used: run.cost.crustdata_credits,
    credit_budget: run.budget_credits,
    resumed_at: run.resumed_at,
    checks_not_run: run.checks_not_run,
  };
}

/** Steps the run skipped because the credit budget ran out. */
export function skippedForBudget(run: RunOut): StepOut[] {
  return run.steps.filter((step) => step.state === "skipped_budget");
}

export function budgetReached(run: RunOut): boolean {
  return (
    skippedForBudget(run).length > 0 ||
    (run.budget_credits > 0 && run.cost.crustdata_credits >= run.budget_credits)
  );
}

export function toCost(run: RunOut): CaseCost {
  return {
    credits_used: run.cost.crustdata_credits,
    credit_budget: run.budget_credits,
    model_usd: run.cost.llm_usd,
    checks_not_run: run.checks_not_run,
    lines: [...run.steps]
      .sort((a, b) => a.position - b.position)
      .filter((step) => step.state === "done")
      .map((step) => ({
        id: step.id,
        run_label: RUN_KIND_LABEL[run.kind],
        step_label: step.label,
        credits: step.cost.crustdata_credits,
        model_usd: step.cost.llm_usd > 0 ? step.cost.llm_usd : null,
        from_cache: step.from_cache,
        at: step.finished_at ?? step.started_at ?? run.created_at,
      })),
  };
}

/** Applies one stream event to the run we are showing. */
export function mergeStep(run: RunOut, step: StepOut): RunOut {
  const steps = run.steps.some((s) => s.id === step.id)
    ? run.steps.map((s) => (s.id === step.id ? step : s))
    : [...run.steps, step];
  return withStepSpend({ ...run, steps });
}

/** A `run` event from the stream may carry no steps; a polling snapshot carries all of them. */
export function mergeRun(previous: RunOut | null, next: RunOut): RunOut {
  if (next.steps.length > 0 || !previous) return withStepSpend(next);
  return withStepSpend({ ...next, steps: previous.steps });
}
