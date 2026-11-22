"use client";

import type { RunOut, StepOut } from "@/lib/api/client";
import { deriveView } from "@/lib/run/activity-store";
import type { Run, RunStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Panel } from "@/components/ui/card";
import { RunHeader } from "@/components/run/run-header";
import { StepChecklist } from "@/components/run/step-checklist";

export { WorkingIndicator } from "@/components/run/run-header";

const NO_TOKENS = { input_tokens: 0, output_tokens: 0, unknown_cost_calls: 0 };

function toStepOut(step: RunStep, position: number, runId: string): StepOut {
  return {
    id: step.id,
    run_id: runId,
    key: step.id,
    label: step.label,
    position,
    state: step.status,
    attempts: 1,
    detail: step.detail ?? null,
    result: step.result ?? null,
    error: step.error ?? null,
    from_cache: step.from_cache ?? false,
    cost: { crustdata_credits: step.credits_used ?? 0, llm_usd: step.model_usd ?? 0, ...NO_TOKENS },
    started_at: null,
    finished_at: null,
  };
}

function toRunOut(run: Run): RunOut {
  const steps = run.steps.map((step, index) => toStepOut(step, index, run.id));
  return {
    id: run.id,
    kind: run.kind,
    state: run.status === "finished" ? "done" : run.status,
    subject: run.subject,
    case_id: null,
    thesis_id: null,
    investor_search_id: null,
    budget_credits: run.credit_budget,
    cost: {
      crustdata_credits: run.credits_used,
      llm_usd: steps.reduce((sum, step) => sum + step.cost.llm_usd, 0),
      ...NO_TOKENS,
    },
    checks_not_run: run.checks_not_run ?? 0,
    created_at: "",
    finished_at: null,
    resumed_at: run.resumed_at ?? null,
    error: null,
    steps,
  };
}

/**
 * Run progress from a plain step list: the header band and the step checklist of the
 * live run view (`@/components/run`), for a caller that has no activity stream. It is a
 * thin wrapper kept so existing imports work; a screen that follows a run should render
 * `RunView`, which adds the "now" line, the Crustdata tally, sources and findings.
 */
export function RunProgress({
  run,
  onRetryStep,
  logHref,
  className,
}: {
  run: Run;
  onRetryStep?: (step: RunStep) => void;
  /** Where the finished line links to. */
  logHref?: string;
  className?: string;
}) {
  const out = toRunOut(run);
  const elapsedMs = run.elapsed_seconds * 1000;
  const current = run.steps.find((step) => step.status === "running");
  // With no activity stream, the running step is all that is known about "now".
  const view = {
    ...deriveView([]),
    now: current
      ? { seq: 0, at: new Date(elapsedMs).toISOString(), label: current.detail ?? current.label, stepKey: current.id }
      : null,
  };
  const header = (
    <RunHeader
      run={out}
      view={view}
      mode="live"
      nowMs={elapsedMs}
      startedAt={0}
      endedAt={run.status === "running" ? null : elapsedMs}
      logHref={logHref}
    />
  );

  if (run.status === "finished") {
    return <Panel className={className}>{header}</Panel>;
  }
  return (
    <Panel
      aria-label={`Run for ${run.subject}`}
      className={cn("overflow-hidden", className)}
    >
      {header}
      {out.steps.length > 0 ? (
        <div className="border-t border-line">
          <StepChecklist
            steps={out.steps}
            activity={view.steps}
            onRetry={
              onRetryStep
                ? (step) => {
                    const original = run.steps.find((s) => s.id === step.id);
                    if (original) onRetryStep(original);
                  }
                : undefined
            }
          />
        </div>
      ) : null}
    </Panel>
  );
}
