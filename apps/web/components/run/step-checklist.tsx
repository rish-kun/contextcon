"use client";

import { ChevronDown } from "lucide-react";
import { Fragment, useId, useState } from "react";
import type { StepOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import type { StepActivity } from "@/lib/run/activity-store";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { StepMark } from "./step-mark";
import { claimStepId, stepCost } from "./wording";

const SETTLED = new Set<StepOut["state"]>(["done", "failed", "skipped_budget"]);
const STATE_WORD: Record<StepOut["state"], string> = {
  pending: "not started",
  running: "running",
  done: "done",
  failed: "failed",
  skipped_budget: "skipped, budget reached",
};

/** Claim checks fold under one parent row once there are this many. */
const GROUP_FROM = 4;

function subLine(step: StepOut, activity: StepActivity | undefined): string | null {
  if (step.state === "running") {
    const line = activity?.line ?? step.detail;
    const progress = activity?.progress;
    if (!line) return null;
    return progress ? `${line} · ${progress.done} of ${progress.total}` : line;
  }
  if (step.state === "done") return step.result;
  return null;
}

function StepRow({
  step,
  activity,
  selected,
  onSelect,
  onRetry,
  nested = false,
}: {
  step: StepOut;
  activity: StepActivity | undefined;
  selected: boolean;
  onSelect?: (key: string | null) => void;
  onRetry?: (step: StepOut) => void;
  nested?: boolean;
}) {
  const line = subLine(step, activity);
  const cost = stepCost(step);
  const skipped = step.state === "skipped_budget";
  const body = (
    <>
      <span
        className={cn(
          "transition-colors duration-(--duration-base)",
          step.state === "pending" && "text-ink-muted",
          step.state === "running" && "font-medium text-ink",
          step.state === "done" && "text-ink",
          step.state === "failed" && "text-contradicted",
          skipped && "text-not-checked",
        )}
      >
        {step.label}
        <span className="sr-only">, {STATE_WORD[step.state]}</span>
      </span>
      {line ? <span className="text-xs text-ink-secondary">{line}</span> : null}
      {skipped ? <span className="text-xs font-medium text-not-checked">Skipped · budget reached</span> : null}
      {step.state === "failed" ? (
        <span className="text-xs text-contradicted">{step.error ?? "No reason was recorded"}</span>
      ) : null}
      {activity?.notices.map((notice) => (
        <span key={notice.seq} className="text-xs text-ink-muted">
          {notice.label}
          {notice.detail ? ` · ${notice.detail}` : null}
        </span>
      ))}
    </>
  );

  return (
    <li
      className={cn(
        "grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-x-2 px-4 py-2 text-dense",
        nested && "pl-10",
        skipped && "hatch border-y border-dashed border-not-checked-line",
        selected && "selected-bar bg-accent-tint",
      )}
    >
      <StepMark state={step.state} fromCache={step.from_cache} className="mt-0.5" />
      {onSelect ? (
        <button
          type="button"
          aria-pressed={selected}
          title={selected ? "Show every step" : "Show only what this step read"}
          onClick={() => onSelect(selected ? null : step.key)}
          className="flex min-w-0 flex-col items-start gap-0.5 rounded-xs text-left"
        >
          {body}
        </button>
      ) : (
        <span className="flex min-w-0 flex-col items-start gap-0.5">{body}</span>
      )}
      <span className="pt-0.5 text-right font-mono text-xs whitespace-nowrap text-ink-secondary">
        {cost}
      </span>
      {step.state === "failed" && onRetry ? (
        <span className="col-start-2 pt-1">
          <Button size="sm" onClick={() => onRetry(step)}>
            Retry step
          </Button>
        </span>
      ) : null}
    </li>
  );
}

/** "Check 12 claims · 7 settled": the claim checks, folded under one row. */
function ClaimGroup({
  steps,
  activity,
  selected,
  onSelect,
  onRetry,
}: {
  steps: StepOut[];
  activity: Map<string, StepActivity>;
  selected: string | null;
  onSelect?: (key: string | null) => void;
  onRetry?: (step: StepOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const settled = steps.filter((step) => SETTLED.has(step.state)).length;
  const started = steps.some((step) => step.state !== "pending");
  const failed = steps.some((step) => step.state === "failed");
  const state: StepOut["state"] =
    settled === steps.length ? (failed ? "failed" : "done") : started ? "running" : "pending";
  // A failed check must be reachable, so the group opens itself when one fails.
  const shown = open || failed || steps.some((step) => step.key === selected);

  return (
    <li className="flex flex-col">
      <button
        type="button"
        aria-expanded={shown}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
        className="focus-inset grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-x-2 px-4 py-2 text-left text-dense transition-colors hover:bg-surface-raised"
      >
        <StepMark state={state} className="mt-0.5" />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className={cn(state === "pending" ? "text-ink-muted" : "text-ink", state === "running" && "font-medium")}>
            Check {plural(steps.length, "claim")}
          </span>
          {started ? <span className="text-xs text-ink-secondary">{settled} settled</span> : null}
        </span>
        <Icon icon={ChevronDown} className={cn("mt-0.5 text-ink-muted transition-transform", shown && "rotate-180")} />
      </button>
      {shown ? (
        <ol id={listId} className="flex flex-col">
          {steps.map((step) => (
            <StepRow
              key={step.id}
              step={step}
              activity={activity.get(step.key)}
              selected={selected === step.key}
              onSelect={onSelect}
              onRetry={onRetry}
              nested
            />
          ))}
        </ol>
      ) : null}
    </li>
  );
}

/** One announcement per step change: "Enrich the top 15, done, 15 enriched". */
function useStepAnnouncement(steps: StepOut[]): string {
  const signature = steps.map((step) => `${step.id}:${step.state}`).join("|");
  const [seen, setSeen] = useState({ signature, states: new Map(steps.map((s) => [s.id, s.state])), text: "" });
  if (seen.signature !== signature) {
    const changed = steps.findLast((step) => seen.states.get(step.id) !== step.state);
    setSeen({
      signature,
      states: new Map(steps.map((s) => [s.id, s.state])),
      text: changed
        ? [changed.label, STATE_WORD[changed.state], changed.state === "done" ? changed.result : null]
            .filter(Boolean)
            .join(", ")
        : seen.text,
    });
  }
  return seen.text;
}

export interface StepChecklistProps {
  steps: StepOut[];
  /** Per step key: the latest status line, progress and notices from the activity stream. */
  activity: Map<string, StepActivity>;
  /** The step the sources and tally are filtered to. */
  selected?: string | null;
  onSelect?: (key: string | null) => void;
  onRetry?: (step: StepOut) => void;
  /** `line` is the one-row form used by short runs: steps joined by a rule. */
  orientation?: "list" | "line";
  /** False for a replay or the log: nothing is announced. */
  announce?: boolean;
  className?: string;
}

/**
 * The steps of a run, in order. The list is the progress: there is no bar and no
 * percentage. A sub-line appears only when the run reported one, and "9 of 15" only when
 * the server sent both numbers.
 */
export function StepChecklist({
  steps,
  activity,
  selected = null,
  onSelect,
  onRetry,
  orientation = "list",
  announce = true,
  className,
}: StepChecklistProps) {
  const announcement = useStepAnnouncement(steps);
  const claimSteps = steps.filter((step) => claimStepId(step.key) !== null);
  const grouped = orientation === "list" && claimSteps.length >= GROUP_FROM;
  const firstClaim = grouped ? claimSteps.reduce((a, b) => (a.position <= b.position ? a : b)) : null;

  if (orientation === "line") {
    const settledClaims = claimSteps.filter((step) => SETTLED.has(step.state)).length;
    const shown =
      claimSteps.length > 1
        ? steps.filter((step) => claimStepId(step.key) === null || step.id === claimSteps[0].id)
        : steps;
    return (
      <>
        <ol className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 text-dense", className)}>
          {shown.map((step, index) => {
            const isClaims = claimSteps.length > 1 && step.id === claimSteps[0].id;
            const state: StepOut["state"] = isClaims
              ? settledClaims === claimSteps.length
                ? "done"
                : claimSteps.some((s) => s.state !== "pending")
                  ? "running"
                  : "pending"
              : step.state;
            return (
              <Fragment key={step.id}>
                {index > 0 ? <li aria-hidden className="h-px w-6 bg-line-strong" /> : null}
                <li className="inline-flex items-center gap-2">
                  <StepMark state={state} fromCache={step.from_cache} />
                  <span className={cn(state === "pending" ? "text-ink-muted" : "text-ink", state === "running" && "font-medium")}>
                    {isClaims ? `Check ${plural(claimSteps.length, "claim")} · ${settledClaims} settled` : step.label}
                    <span className="sr-only">, {STATE_WORD[state]}</span>
                  </span>
                </li>
              </Fragment>
            );
          })}
        </ol>
        {announce ? (
          <p className="sr-only" aria-live="polite">
            {announcement}
          </p>
        ) : null}
      </>
    );
  }

  return (
    <>
      <ol className={cn("flex flex-col py-1", className)}>
        {steps.map((step) => {
          if (grouped && claimStepId(step.key) !== null) {
            return step.id === firstClaim?.id ? (
              <ClaimGroup
                key="claim-checks"
                steps={claimSteps}
                activity={activity}
                selected={selected}
                onSelect={onSelect}
                onRetry={onRetry}
              />
            ) : null;
          }
          return (
            <StepRow
              key={step.id}
              step={step}
              activity={activity.get(step.key)}
              selected={selected === step.key}
              onSelect={onSelect}
              onRetry={onRetry}
            />
          );
        })}
      </ol>
      {announce ? (
        <p className="sr-only" aria-live="polite">
          {announcement}
        </p>
      ) : null}
    </>
  );
}

/** "2 of 5", for the head of the step panel. */
export function stepsDone(steps: StepOut[]): string {
  return `${steps.filter((step) => SETTLED.has(step.state)).length} of ${steps.length}`;
}
