"use client";

import { Check, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import type { RunOut, ShortlistItemOut, StepOut } from "@/lib/api/client";
import {
  formatCredits,
  formatDateTime,
  formatDuration,
  formatShare,
  plural,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { asLiveSeed, useRunActivity } from "@/lib/run/use-run-activity";
import { HatchedBlock, RunProgress } from "@/components/dealproof";
import { RunView } from "@/components/run/run-view";
import { formatModelUsd, runDuration, toRun } from "./adapt";
import { CandidateStream } from "./candidate-stream";
import { ErrorNotice } from "./notice";

/**
 * A search run, followed live. Steps, the "now" line, the Crustdata tally and the sources
 * sit around the candidates as they are found, dropped, enriched and ranked. Every row and
 * figure is a stored event of the run; there is no bar and no percentage.
 *
 * `onSettled` fires once, when the run reports done or failed. Once the thesis has been
 * read again, pass its shortlist as `settled`: the side columns fold away and each
 * candidate row becomes its card in place, so the result is not swapped in.
 */
export function LiveRun({
  seed,
  thesisId,
  onSettled,
  settled,
  finishedRun,
}: {
  seed: RunOut;
  thesisId: string;
  onSettled: (run: RunOut) => void;
  settled?: ShortlistItemOut[];
  /** The run as the thesis now records it, for the overview's cost line. */
  finishedRun?: RunOut | null;
}) {
  const { feed, setPaused } = useRunActivity(seed, { onSettled });
  const run = feed.run ?? asLiveSeed(seed);

  return (
    <div className="flex flex-col gap-3">
      <RunView
        run={run}
        feed={feed}
        onPause={setPaused}
        logHref={`/app/discover/${encodeURIComponent(thesisId)}/log`}
        findings={(context) => (
          <CandidateStream
            context={context}
            thesisId={thesisId}
            settled={run.state === "done" ? settled : undefined}
            run={finishedRun}
          />
        )}
      />
      {run.state === "done" ? null : (
        <p className="px-4 text-xs text-ink-muted">
          You can leave this page. The run keeps its steps and what it has found
        </p>
      )}
    </div>
  );
}

/** A run that stopped with an error. Earlier steps are kept, and resuming is explicit. */
export function FailedRun({
  run,
  onResume,
  resuming,
  resumeError,
}: {
  run: RunOut;
  onResume: () => void;
  resuming: boolean;
  resumeError: string | null;
}) {
  const failed = run.steps.find((step) => step.state === "failed");
  const reason = failed?.error ?? run.error ?? "no reason was recorded";

  return (
    <div className="flex flex-col gap-3">
      <RunProgress run={toRun(run, runDuration(run) ?? 0)} />
      <ErrorNotice
        title={
          failed ? `${failed.label} did not finish: ${reason}` : `The search stopped: ${reason}`
        }
        actions={
          <Button size="sm" onClick={onResume} disabled={resuming}>
            {resuming ? "Resuming" : "Resume run"}
          </Button>
        }
      >
        Previous steps are kept. Resuming continues from the step that stopped and can spend
        more credits.
      </ErrorNotice>
      {resumeError ? (
        <ErrorNotice title="The run could not be resumed">{resumeError}</ErrorNotice>
      ) : null}
    </div>
  );
}

function stepCost(step: StepOut): string {
  if (step.from_cache) return "0 · cache";
  const parts: string[] = [];
  if (step.cost.crustdata_credits > 0) parts.push(`${formatCredits(step.cost.crustdata_credits)} cr`);
  if (step.cost.llm_usd > 0) parts.push(formatModelUsd(step.cost.llm_usd));
  return parts.length > 0 ? parts.join(" · ") : "0 cr";
}

function StepLine({ step }: { step: StepOut }) {
  const skipped = step.state === "skipped_budget";
  return (
    <li
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 px-4 py-2 text-dense",
        skipped && "hatch border-y border-dashed border-not-checked-line",
      )}
    >
      <span className={cn("text-ink", skipped && "text-not-checked")}>{step.label}</span>
      <span className="text-right font-mono text-xs text-ink-secondary">
        {step.state === "done" ? stepCost(step) : null}
      </span>
      <span className="col-span-2 text-xs text-ink-secondary">
        {step.state === "done" ? (step.result ?? "Done") : null}
        {skipped ? <span className="font-medium text-not-checked">Skipped · budget reached</span> : null}
        {step.state === "failed" ? (
          <span className="text-contradicted">
            Step failed · {step.error ?? "no reason recorded"}
          </span>
        ) : null}
        {step.state === "pending" || step.state === "running" ? "Did not finish" : null}
      </span>
    </li>
  );
}

/** True when the run stopped short because the credit budget ran out. */
export function budgetReached(run: RunOut): boolean {
  return (
    run.checks_not_run > 0 ||
    run.steps.some((step) => step.state === "skipped_budget") ||
    (run.budget_credits > 0 && run.cost.crustdata_credits >= run.budget_credits)
  );
}

/**
 * Said at the top of the shortlist when the budget ran out. It is a stated limit, not an
 * error, so it uses the hatched "not run" family and nothing turns red.
 */
export function BudgetNotice({ run }: { run: RunOut }) {
  if (!budgetReached(run)) return null;
  const skipped = run.steps.filter((step) => step.state === "skipped_budget");

  return (
    <HatchedBlock role="status">
      <p className="text-sm font-medium">
        Credit budget reached
        {run.checks_not_run > 0
          ? `. ${plural(run.checks_not_run, "check")} ${
              run.checks_not_run === 1 ? "was" : "were"
            } not run and ${run.checks_not_run === 1 ? "is" : "are"} marked Not checked`
          : null}
      </p>
      <p className="text-dense">
        {skipped.length > 0
          ? `Skipped: ${skipped.map((step) => step.label).join(", ")}. `
          : null}
        What those steps would have added is missing below, and criteria they would have
        settled read as unknown. Nothing skipped is counted as met.
      </p>
    </HatchedBlock>
  );
}

/**
 * The finished run in one place: how long it took, what it cost, and its steps.
 * Crustdata credits and model dollars are two currencies and are never added together.
 */
export function RunSummary({ run, className }: { run: RunOut; className?: string }) {
  const [open, setOpen] = useState(false);
  const stepsId = useId();
  const duration = runDuration(run);
  const used = run.cost.crustdata_credits;
  const budget = run.budget_credits;
  const share = budget > 0 ? Math.min(1, used / budget) : 0;
  const reached = budgetReached(run);
  const finishedAt = formatDateTime(run.finished_at);

  return (
    <section
      aria-label="Search run and its cost"
      className={cn("rounded-lg border border-line bg-surface", className)}
    >
      <div className="flex flex-col gap-3 p-4">
        <p className="flex items-start gap-2 text-sm font-medium text-ink">
          <Icon icon={Check} className="mt-0.5 shrink-0" />
          <span>
            Discover finished
            {duration !== null ? (
              <span className="font-mono text-xs font-normal text-ink-secondary">
                {" "}
                · {formatDuration(duration)}
              </span>
            ) : null}
          </span>
        </p>

        <div className="flex flex-col gap-2">
          <h3 className="text-xs text-ink-muted">This search cost</h3>
          <p className="font-mono text-sm font-medium text-ink">
            {formatCredits(used)} of {formatCredits(budget)} credits
            <span className="text-ink-muted"> · </span>
            {formatModelUsd(run.cost.llm_usd)} model usage
          </p>
          <div
            role="meter"
            aria-label="Crustdata credits used against the run budget"
            aria-valuemin={0}
            aria-valuemax={budget}
            aria-valuenow={Math.min(used, budget)}
            aria-valuetext={`${formatCredits(used)} of ${formatCredits(budget)} credits`}
            className="h-2 w-full overflow-hidden rounded-xs border border-line-strong bg-surface-sunken"
          >
            <div className="h-full origin-left bg-ink" style={{ width: `${share * 100}%` }} />
          </div>
          <p className="text-xs text-ink-secondary">
            {reached
              ? `Budget reached${
                  run.checks_not_run > 0 ? ` · ${plural(run.checks_not_run, "check")} not run` : ""
                }`
              : `${formatShare(share)} of the credit budget`}
          </p>
          {run.cost.unknown_cost_calls > 0 ? (
            <p className="text-xs text-not-checked">
              {plural(run.cost.unknown_cost_calls, "call")} returned no cost and{" "}
              {run.cost.unknown_cost_calls === 1 ? "is" : "are"} not in these totals
            </p>
          ) : null}
        </div>

        {finishedAt ? (
          <p className="font-mono text-2xs text-ink-muted">Finished {finishedAt}</p>
        ) : null}
        {run.thesis_id ? (
          <Link
            href={`/app/discover/${encodeURIComponent(run.thesis_id)}/log`}
            className="self-start rounded-xs text-dense text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Run log
          </Link>
        ) : null}
      </div>

      {run.steps.length > 0 ? (
        <div className="border-t border-line">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={stepsId}
            onClick={() => setOpen((value) => !value)}
            className={cn(
              "focus-inset flex h-9 w-full items-center justify-between gap-2 px-4 text-dense text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink",
              !open && "rounded-b-lg",
            )}
          >
            {open ? "Hide" : "Show"} {plural(run.steps.length, "step")}
            <Icon
              icon={ChevronDown}
              className={cn("transition-transform", open && "rotate-180")}
            />
          </button>
          {open ? (
            <ol id={stepsId} className="divide-y divide-line border-t border-line">
              {run.steps.map((step) => (
                <StepLine key={step.id} step={step} />
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
