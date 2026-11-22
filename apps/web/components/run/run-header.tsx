"use client";

import { Check, Pause, Play, X } from "lucide-react";
import Link from "next/link";
import { ThinkingOrb } from "thinking-orbs";
import type { RunOut } from "@/lib/api/client";
import { formatCredits, formatDuration, formatTime, plural } from "@/lib/format";
import type { OrbWork, RunActivityView } from "@/lib/run/activity-store";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { CostMeter } from "./cost-meter";
import { NowLine } from "./now-line";
import { RUN_KIND_WORD, modelUsd } from "./wording";

/**
 * The one "analyst working" indicator in the product. It lives in the run header while a
 * run is live and nowhere else, and its state follows the kind of work the latest event
 * was: searching, fetching, reading, applying rules, drafting. Under reduced motion the
 * word "Working" replaces it.
 */
export function WorkingIndicator({
  work = "searching",
  className,
}: {
  work?: OrbWork;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex shrink-0 items-center", className)}>
      {/* The canvas sets its own display inline, so the wrapper is what hides it. */}
      <span className="inline-flex motion-reduce:hidden">
        <ThinkingOrb state={work} size={20} theme="light" aria-hidden />
      </span>
      <span className="hidden rounded-xs border border-line-strong px-1 font-mono text-2xs text-ink-secondary motion-reduce:inline">
        Working
      </span>
    </span>
  );
}

const linkClass =
  "rounded-xs font-sans text-accent underline underline-offset-2 transition-colors hover:text-accent-hover";

export interface RunHeaderProps {
  run: RunOut;
  view: RunActivityView;
  mode: "live" | "replay" | "log";
  nowMs: number;
  startedAt: number | null;
  endedAt: number | null;
  paused?: boolean;
  /** Events received and not shown yet. */
  held?: number;
  onPause?: (paused: boolean) => void;
  logHref?: string;
  sourcesHref?: string;
  costHref?: string;
  onResume?: () => void;
  resuming?: boolean;
  /** The one-row form for short runs: elapsed and cost sit on the title row. */
  compact?: boolean;
  className?: string;
}

/**
 * The header band of a run. While the run is going: the orb, what the run is, the "now"
 * line, elapsed time and the cost meter. When it finishes it is one line, with links to
 * everything that folded away. When it stops with an error it says which step and why.
 */
export function RunHeader({
  run,
  view,
  mode,
  nowMs,
  startedAt,
  endedAt,
  paused = false,
  held = 0,
  onPause,
  logHref,
  sourcesHref,
  costHref,
  onResume,
  resuming = false,
  compact = false,
  className,
}: RunHeaderProps) {
  const kind = RUN_KIND_WORD[run.kind];
  const credits = Math.max(run.cost.crustdata_credits, view.cost.credits ?? 0);
  const usd = Math.max(run.cost.llm_usd, view.cost.usd ?? 0);
  const elapsed =
    startedAt === null ? 0 : Math.max(0, ((endedAt ?? nowMs) - startedAt) / 1000);
  const subject = run.kind === "discover" ? `“${run.subject}”` : run.subject;

  if (run.state === "done") {
    const sourceCount = view.sourceCounts.read + view.sourceCounts.failed;
    return (
      <div
        role="status"
        className={cn(
          "flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 font-mono text-xs text-ink",
          className,
        )}
      >
        <Icon icon={Check} />
        <span>
          {kind} finished · {formatDuration(elapsed)} · {formatCredits(credits)} of{" "}
          {formatCredits(run.budget_credits)} credits
          {usd > 0 ? ` · ${modelUsd(usd)}` : null}
          {run.checks_not_run > 0 ? ` · ${plural(run.checks_not_run, "check")} not run` : null}
        </span>
        <span className="flex flex-wrap items-center gap-x-3">
          {logHref ? (
            <Link href={logHref} className={linkClass}>
              Run log
            </Link>
          ) : null}
          {sourcesHref && sourceCount > 0 ? (
            <Link href={sourcesHref} className={linkClass}>
              Sources ({sourceCount})
            </Link>
          ) : null}
          {costHref ? (
            <Link href={costHref} className={linkClass}>
              Cost
            </Link>
          ) : null}
        </span>
      </div>
    );
  }

  const failed = run.state === "failed";
  const failedStep = run.steps.find((step) => step.state === "failed");
  const reason = failedStep?.error ?? run.error ?? "no reason was recorded";
  const live = mode === "live" && !failed;

  return (
    <header className={cn("flex flex-col gap-1 px-4 py-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p className="flex min-w-0 items-center gap-2 text-sm font-medium text-ink">
          {failed ? <Icon icon={X} className="shrink-0 text-contradicted" /> : null}
          {live ? <WorkingIndicator work={view.work} /> : null}
          <span className="truncate">
            {failed ? "Run stopped" : mode === "live" ? "Analyst working" : "Replay"}
            <span className="font-normal text-ink-secondary">
              {" "}
              · {kind} · {subject}
            </span>
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-mono text-xs whitespace-nowrap text-ink-secondary">
            {formatDuration(elapsed)}
            {run.resumed_at ? ` · Resumed ${formatTime(run.resumed_at)}` : null}
          </span>
          <CostMeter
            credits={credits}
            budget={run.budget_credits}
            usd={usd}
            delta={live ? view.cost.lastDelta : null}
            compact={compact}
          />
          {live && onPause ? (
            <Button
              size="sm"
              variant="quiet"
              aria-pressed={paused}
              onClick={() => onPause(!paused)}
              className="-mr-2"
            >
              <Icon icon={paused ? Play : Pause} />
              {paused ? "Resume updates" : "Pause updates"}
              {paused && held > 0 ? (
                <span className="rounded-xs border border-line-strong px-1 font-mono text-2xs font-normal text-ink-secondary">
                  {held} new
                </span>
              ) : null}
            </Button>
          ) : null}
        </div>
      </div>

      {failed ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <p className="text-dense text-contradicted">
            {failedStep ? `${failedStep.label} did not finish: ${reason}` : `The run stopped: ${reason}`}
          </p>
          {onResume ? (
            <Button size="sm" onClick={onResume} disabled={resuming}>
              {resuming ? "Resuming" : "Resume run"}
            </Button>
          ) : null}
        </div>
      ) : (
        <NowLine
          label={view.now?.label ?? null}
          at={view.now ? Date.parse(view.now.at) : null}
          nowMs={nowMs}
          startedAt={startedAt}
          waitingForWorker={run.state === "pending"}
          provider={view.lastProvider}
          className={live ? "pl-7" : undefined}
        />
      )}
    </header>
  );
}
