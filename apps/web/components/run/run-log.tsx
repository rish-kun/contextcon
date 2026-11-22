"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import type { RunOut, StepOut } from "@/lib/api/client";
import { formatCredits } from "@/lib/format";
import type { Activity } from "@/lib/run/types";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";
import { Segmented } from "@/components/ui/toolbar";
import { StepMark } from "./step-mark";
import { clockTime, failedReadText, modelUsd, sourceTitle, stepCost } from "./wording";

type KindFilter = "all" | "calls" | "sources" | "findings" | "notices";

const KIND_FILTER: Record<Exclude<KindFilter, "all">, Activity["kind"][]> = {
  calls: ["call", "model"],
  sources: ["source"],
  findings: ["finding"],
  notices: ["notice"],
};

function isProblem(event: Activity): boolean {
  if (event.call && !event.call.ok) return true;
  if (event.kind === "source" && event.source && event.source.state !== "read") return true;
  return event.kind === "notice" && (event.code === "budget_reached" || event.code === "identity_blocked");
}

function eventCost(event: Activity): string | null {
  const call = event.call;
  if (!call) return null;
  if (call.from_cache) return "0 cr · cache";
  if (call.provider === "anthropic") return call.usd !== null ? modelUsd(call.usd) : null;
  return call.credits !== null ? `${formatCredits(call.credits)} cr` : "cost not reported";
}

function eventText(event: Activity): { text: string; tone: "ink" | "muted" | "problem" } {
  if (event.kind === "source" && event.source) {
    if (event.source.state !== "read") {
      return { text: `${event.label} · ${failedReadText(event.source).replace(/^.* · /, "")}`, tone: "muted" };
    }
    const title = sourceTitle(event.source);
    return { text: title ? `${event.label} · ${title}` : event.label, tone: "ink" };
  }
  if (event.kind === "model") {
    const rejected = event.counts?.rejected_no_span ?? 0;
    return {
      text: rejected > 0 ? `${event.label} · ${rejected} discarded: no matching passage` : event.label,
      tone: "ink",
    };
  }
  const text = event.detail ? `${event.label} · ${event.detail}` : event.label;
  if (event.call && !event.call.ok) return { text, tone: "problem" };
  if (event.kind === "status" || event.kind === "notice") return { text, tone: "muted" };
  return { text, tone: "ink" };
}

function duration(step: StepOut, events: Activity[]): string | null {
  const start = Date.parse(step.started_at ?? events[0]?.at ?? "");
  const end = Date.parse(step.finished_at ?? events.at(-1)?.at ?? "");
  // Fixture steps carry whole-minute stamps; the events are the finer record.
  const first = Date.parse(events[0]?.at ?? "");
  const last = Date.parse(events.at(-1)?.at ?? "");
  const ms = Number.isFinite(first) && Number.isFinite(last) && last > first ? last - first : end - start;
  if (!Number.isFinite(ms) || ms < 0) return null;
  return `${(ms / 1000).toFixed(1)} s`;
}

function StepGroup({ step, events, total }: { step: StepOut; events: Activity[]; total: Activity[] }) {
  const [open, setOpen] = useState(true);
  const skipped = step.state === "skipped_budget";
  return (
    <li className={cn("border-b border-line last:border-b-0", skipped && "hatch")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="focus-inset grid w-full grid-cols-[4.5rem_1rem_minmax(0,1fr)_auto_auto] items-start gap-x-3 px-4 py-2 text-left text-dense transition-colors hover:bg-surface-raised"
      >
        <span className="font-mono text-xs leading-5 text-ink-muted">
          {clockTime(total[0]?.at ?? step.started_at)}
        </span>
        <StepMark state={step.state} fromCache={step.from_cache} className="mt-0.5" />
        <span className="flex min-w-0 flex-col">
          <span className={cn("font-medium", skipped ? "text-not-checked" : step.state === "failed" ? "text-contradicted" : "text-ink")}>
            {step.label}
          </span>
          <span className="text-xs text-ink-secondary">
            {skipped
              ? "Skipped · budget reached"
              : step.state === "failed"
                ? (step.error ?? "No reason was recorded")
                : step.state === "done"
                  ? step.result
                  : "Did not finish"}
          </span>
        </span>
        <span className="text-right font-mono text-xs leading-5 whitespace-nowrap text-ink-secondary">
          {stepCost(step)}
          {duration(step, total) ? <span className="pl-3 text-ink-muted">{duration(step, total)}</span> : null}
        </span>
        <Icon icon={ChevronDown} className={cn("mt-0.5 text-ink-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && events.length > 0 ? (
        <ol className="flex flex-col pb-2">
          {events.map((event) => {
            const { text, tone } = eventText(event);
            return (
              <li
                key={event.seq}
                className="grid grid-cols-[4.5rem_1rem_minmax(0,1fr)_auto] items-baseline gap-x-3 px-4 py-0.5 text-xs"
              >
                <span className="font-mono text-ink-muted">{clockTime(event.at)}</span>
                <span />
                <span
                  className={cn(
                    "min-w-0",
                    tone === "ink" && "text-ink",
                    tone === "muted" && "text-ink-secondary",
                    tone === "problem" && "text-contradicted",
                  )}
                >
                  {text}
                </span>
                <span className="text-right font-mono whitespace-nowrap text-ink-secondary">
                  {eventCost(event)}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </li>
  );
}

/**
 * The timeline of a finished run: each step with the events it recorded, in order, with
 * absolute times, per-event cost and per-step duration. Static and fully settled, so it
 * prints. A run from before activity was recorded shows its steps and says so.
 */
export function RunLog({ run, events, className }: { run: RunOut; events: Activity[]; className?: string }) {
  const [kind, setKind] = useState<KindFilter>("all");
  const [problems, setProblems] = useState(false);
  const steps = [...run.steps].sort((a, b) => a.position - b.position);
  const passes = (event: Activity) =>
    (kind === "all" || KIND_FILTER[kind].includes(event.kind)) && (!problems || isProblem(event));
  const problemCount =
    events.filter(isProblem).length +
    steps.filter((step) => step.state === "failed" || step.state === "skipped_budget").length;
  const visibleSteps = steps.filter(
    (step) => !problems || step.state === "failed" || step.state === "skipped_budget" || events.some((e) => e.step_id === step.id && isProblem(e)),
  );

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {events.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <Segmented
            label="Filter events by kind"
            value={kind}
            onChange={setKind}
            options={[
              { value: "all", label: "All" },
              { value: "calls", label: "Calls" },
              { value: "sources", label: "Sources" },
              { value: "findings", label: "Findings" },
              { value: "notices", label: "Notices" },
            ]}
          />
          <button
            type="button"
            aria-pressed={problems}
            onClick={() => setProblems((value) => !value)}
            className={cn(
              "inline-flex h-8 items-center gap-2 rounded-md border px-3 text-dense transition-colors",
              problems
                ? "border-accent-line bg-accent-tint font-medium text-accent"
                : "border-line-strong bg-surface text-ink-secondary hover:bg-surface-raised hover:text-ink",
            )}
          >
            Only problems
            <span className="font-mono text-2xs font-normal">{problemCount}</span>
          </button>
        </div>
      ) : (
        <p className="text-dense text-ink-secondary">Detailed activity was not recorded for this run</p>
      )}
      {visibleSteps.length > 0 ? (
        <ol className="rounded-lg border border-line bg-surface">
          {visibleSteps.map((step) => {
            const total = events.filter((event) => event.step_id === step.id);
            return <StepGroup key={step.id} step={step} total={total} events={total.filter(passes)} />;
          })}
        </ol>
      ) : (
        <p className="text-dense text-ink-secondary">
          {problems ? "No failed calls, unread pages or skipped steps in this run" : "This run recorded no steps"}
        </p>
      )}
    </div>
  );
}
