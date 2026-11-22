"use client";

import { Check, ChevronRight, X } from "lucide-react";
import { ThinkingOrb } from "thinking-orbs";
import { formatCredits, formatDuration, formatTime, formatUsd, plural } from "@/lib/format";
import { RUN_KIND_LABEL } from "@/lib/labels";
import type { Run, RunStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { NumberTween } from "./number-tween";
import { PendingGlyph, StatusGlyph } from "./glyphs";

/**
 * The one "analyst working" indicator in the product. It lives in the run header while a
 * run is live and nowhere else. Under reduced motion the word "Working" replaces it.
 */
export function WorkingIndicator({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center", className)}>
      <ThinkingOrb
        state="searching"
        size={20}
        theme="light"
        aria-hidden
        className="motion-reduce:hidden"
      />
      <span className="hidden rounded-xs border border-line-strong px-1 font-mono text-2xs text-ink-secondary motion-reduce:inline">
        Working
      </span>
    </span>
  );
}

function stepCost(step: RunStep): string | null {
  if (step.from_cache) return "from cache · 0 cr";
  if (step.model_usd != null) return formatUsd(step.model_usd);
  if (step.credits_used != null) return `${formatCredits(step.credits_used)} cr`;
  return null;
}

function StepRow({ step, onRetry }: { step: RunStep; onRetry?: (step: RunStep) => void }) {
  const cost = step.status === "done" ? stepCost(step) : null;

  return (
    <li
      className={cn(
        "grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-x-3 gap-y-1 px-4 py-2 text-dense transition-colors sm:grid-cols-[1rem_minmax(0,14rem)_minmax(0,1fr)_auto]",
        step.status === "skipped_budget" && "hatch border-y border-dashed border-not-checked-line",
      )}
    >
      <span className="mt-0.5 inline-flex">
        {step.status === "done" ? <Icon icon={Check} className="text-ink" /> : null}
        {step.status === "running" ? <Icon icon={ChevronRight} className="text-ink" /> : null}
        {step.status === "pending" ? <PendingGlyph className="text-ink-muted" /> : null}
        {step.status === "failed" ? <Icon icon={X} className="text-contradicted" /> : null}
        {step.status === "skipped_budget" ? (
          <StatusGlyph status="not_checked" className="text-not-checked" />
        ) : null}
      </span>

      <span
        className={cn(
          step.status === "pending" && "text-ink-muted",
          step.status === "running" && "font-medium text-ink",
          step.status === "done" && "text-ink",
          step.status === "failed" && "text-contradicted",
          step.status === "skipped_budget" && "text-not-checked",
        )}
      >
        {step.label}
        <span className="sr-only">
          {step.status === "pending" ? ", not started" : null}
          {step.status === "running" ? ", running" : null}
          {step.status === "done" ? ", done" : null}
        </span>
      </span>

      <span className="col-start-2 min-w-0 text-ink-secondary sm:col-start-3">
        {step.status === "running" ? step.detail : null}
        {step.status === "done" ? step.result : null}
        {step.status === "failed" ? (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-contradicted">Failed · {step.error ?? "no reason recorded"}</span>
            {onRetry ? (
              <Button size="sm" onClick={() => onRetry(step)}>
                Retry step
              </Button>
            ) : null}
          </span>
        ) : null}
        {step.status === "skipped_budget" ? (
          <span className="font-medium text-not-checked">Skipped · budget reached</span>
        ) : null}
      </span>

      <span className="col-start-3 row-start-1 text-right font-mono text-xs text-ink-secondary sm:col-start-4">
        {cost}
      </span>
    </li>
  );
}

/**
 * Run progress: the steps, in order, as they happen. There is no progress bar and no
 * percentage: the step list is the progress.
 *
 * - While running: the working indicator, elapsed time and credits against the budget.
 * - After a resume: "Resumed 16:51 IST · 5 steps kept, continuing from Gather evidence".
 * - When finished: one line, with a link to the full run log.
 * A screen reader hears one announcement per step change, not per sub-line.
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
  const kind = RUN_KIND_LABEL[run.kind];
  const current = run.steps.find((s) => s.status === "running");
  const failed = run.steps.find((s) => s.status === "failed");
  const kept = run.steps.filter((s) => s.from_cache).length;
  const next = current ?? run.steps.find((s) => s.status === "pending");
  const notRun = run.checks_not_run ?? 0;

  if (run.status === "finished") {
    const line = (
      <>
        {kind} finished · {formatDuration(run.elapsed_seconds)} ·{" "}
        {formatCredits(run.credits_used)} credits
        {notRun > 0 ? ` · ${plural(notRun, "check")} not run` : null}
      </>
    );
    return (
      <div
        role="status"
        className={cn(
          "flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-surface px-4 py-2 font-mono text-xs text-ink",
          className,
        )}
      >
        <Icon icon={Check} />
        <span>{line}</span>
        {logHref ? (
          <a
            href={logHref}
            className="rounded-xs font-sans text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Run log
          </a>
        ) : null}
      </div>
    );
  }

  const announcement =
    run.status === "failed"
      ? `${kind} stopped. ${failed ? `${failed.label} failed` : ""}`
      : current
        ? `${kind}: ${current.label}`
        : `${kind} started`;

  return (
    <section
      aria-label={`${kind} run for ${run.subject}`}
      className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}
    >
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-3">
        <p className="flex min-w-0 items-center gap-2 text-sm font-medium text-ink">
          {run.status === "running" ? <WorkingIndicator /> : <Icon icon={X} className="text-contradicted" />}
          <span className="truncate">
            {run.status === "running" ? "Analyst working" : "Run stopped"}
            <span className="font-normal text-ink-secondary">
              {" "}
              · {kind} · {run.subject}
            </span>
          </span>
        </p>
        <p className="font-mono text-xs text-ink-secondary">
          {formatDuration(run.elapsed_seconds)} ·{" "}
          <NumberTween value={run.credits_used} format={formatCredits} /> of{" "}
          {formatCredits(run.credit_budget)} credits
        </p>
      </header>

      {run.resumed_at ? (
        <p className="border-b border-line bg-surface-raised px-4 py-2 text-xs text-ink-secondary">
          Resumed {formatTime(run.resumed_at)} · {plural(kept, "step")} kept
          {next ? `, continuing from ${next.label}` : null}
        </p>
      ) : null}

      <ol className="flex flex-col py-2">
        {run.steps.map((step) => (
          <StepRow key={step.id} step={step} onRetry={onRetryStep} />
        ))}
      </ol>

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
    </section>
  );
}
