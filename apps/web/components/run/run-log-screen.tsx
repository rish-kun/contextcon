"use client";

import { Play, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getRun, listAllRunActivity, type RunOut } from "@/lib/api/client";
import { formatCredits, formatDateTime, formatDuration, formatTime, plural } from "@/lib/format";
import { RUN_KIND_LABEL } from "@/lib/labels";
import { deriveView } from "@/lib/run/activity-store";
import type { Activity } from "@/lib/run/types";
import { useRunReplay } from "@/lib/run/use-run-activity";
import type { CaseCost } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CostReadout } from "@/components/dealproof/cost-readout";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CrustdataTally } from "./crustdata-tally";
import { ReplayBanner, ReplayControls } from "./replay-controls";
import { RunLog } from "./run-log";
import { RunView, type FindingsContext } from "./run-view";
import { SourceTicker } from "./source-ticker";
import { RUN_KIND_WORD, modelUsd } from "./wording";

/** Enough of a run to list it and load it. */
export interface RunRef {
  id: string;
  kind: RunOut["kind"];
  state: RunOut["state"];
  created_at: string;
  finished_at: string | null;
}

function toCost(run: RunOut): CaseCost {
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

function seconds(run: RunOut): number | null {
  if (!run.finished_at) return null;
  const value = (Date.parse(run.finished_at) - Date.parse(run.created_at)) / 1000;
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/** "Verify · Harbourline · 22 Nov 2026, 16:42 IST to 16:45 IST · 2 min 51 s · 61 of 150 cr · $0.09". */
function summaryLine(run: RunOut): string {
  const took = seconds(run);
  const parts = [
    RUN_KIND_WORD[run.kind],
    run.subject.length > 60 ? `${run.subject.slice(0, 60)}…` : run.subject,
    `${formatDateTime(run.created_at) ?? "time not recorded"}${
      run.finished_at ? ` to ${formatTime(run.finished_at)}` : ""
    }`,
    took !== null ? formatDuration(took) : null,
    `${formatCredits(run.cost.crustdata_credits)} of ${formatCredits(run.budget_credits)} cr`,
    run.cost.llm_usd > 0 ? modelUsd(run.cost.llm_usd) : null,
    run.checks_not_run > 0 ? `${plural(run.checks_not_run, "check")} not run` : null,
    run.state === "failed" ? "stopped with an error" : run.state !== "done" ? "still running" : null,
  ];
  return parts.filter(Boolean).join(" · ");
}

function Loaded({
  run,
  events,
  findings,
}: {
  run: RunOut;
  events: Activity[];
  findings?: (context: FindingsContext) => React.ReactNode;
}) {
  const [replaying, setReplaying] = useState(false);
  const replay = useRunReplay(run, events);
  const view = useMemo(() => deriveView(events), [events]);
  const lastSeq = events.at(-1)?.seq ?? 0;
  const endMs = Date.parse(events.at(-1)?.at ?? run.finished_at ?? run.created_at);

  if (replaying && replay.feed.run) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ReplayControls replay={replay} className="min-w-0 flex-1" />
          <Button
            size="sm"
            variant="quiet"
            onClick={() => {
              replay.pause();
              setReplaying(false);
            }}
          >
            <Icon icon={X} />
            Close replay
          </Button>
        </div>
        <RunView
          run={replay.feed.run}
          feed={replay.feed}
          mode="replay"
          form={run.kind === "recheck" || run.kind === "evaluate" ? "compact" : "full"}
          nowMs={replay.nowMs}
          findings={findings}
          banner={<ReplayBanner startedAt={run.created_at} />}
        />
      </div>
    );
  }

  return (
    <Tabs defaultValue="timeline">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <TabsList className="min-w-0 flex-1">
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="sources">
            Sources <span className="font-mono text-xs font-normal text-ink-muted">{view.sources.length}</span>
          </TabsTrigger>
          <TabsTrigger value="crustdata">
            Crustdata{" "}
            <span className="font-mono text-xs font-normal text-ink-muted">{plural(view.tally.calls, "call")}</span>
          </TabsTrigger>
          <TabsTrigger value="cost">Cost</TabsTrigger>
        </TabsList>
        {events.length > 0 ? (
          <Button
            size="sm"
            className="print:hidden"
            onClick={() => {
              replay.seek(0);
              setReplaying(true);
              replay.play();
            }}
          >
            <Icon icon={Play} />
            Replay · {replay.speed}×
          </Button>
        ) : null}
      </div>
      <TabsContent value="timeline">
        <RunLog run={run} events={events} />
      </TabsContent>
      <TabsContent value="sources">
        <SourceTicker
          sources={view.sources}
          counts={view.sourceCounts}
          nowMs={Number.isFinite(endMs) ? endMs : 0}
          settledSeq={lastSeq}
          absolute
          className="max-w-3xl"
        />
      </TabsContent>
      <TabsContent value="crustdata">
        <CrustdataTally kind={run.kind} view={view} className="max-w-3xl" />
      </TabsContent>
      <TabsContent value="cost">
        <CostReadout cost={toCost(run)} title="This run cost" />
      </TabsContent>
    </Tabs>
  );
}

type LoadState =
  | { status: "loading"; id: string }
  | { status: "error"; id: string }
  | { status: "ready"; id: string; run: RunOut; events: Activity[] };

export interface RunLogScreenProps {
  /** The runs to choose from, newest first. */
  runs: RunRef[];
  /** The findings stream for a replay, by the run being replayed. */
  findings?: (context: FindingsContext) => React.ReactNode;
  /** Said when there is no run at all. */
  empty?: string;
  className?: string;
}

/**
 * The run log: a finished run opened for inspection, with the same components that drew
 * it live. Timeline, sources, the Crustdata tally and cost are tabs; Replay plays the
 * stored events back through the live layout. It is also the record of every source a
 * run used.
 */
export function RunLogScreen({ runs, findings, empty = "No run has been recorded yet", className }: RunLogScreenProps) {
  const [selected, setSelected] = useState<string | null>(runs[0]?.id ?? null);
  const [load, setLoad] = useState<LoadState | null>(null);
  const [attempt, setAttempt] = useState(0);
  const id = selected && runs.some((run) => run.id === selected) ? selected : (runs[0]?.id ?? null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    void Promise.all([getRun(id), listAllRunActivity(id)]).then(
      ([run, events]) => {
        if (!cancelled) setLoad({ status: "ready", id, run, events });
      },
      () => {
        if (!cancelled) setLoad({ status: "error", id });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  if (!id) return <p className="text-dense text-ink-secondary">{empty}</p>;
  const current: LoadState = load && load.id === id ? load : { status: "loading", id };

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {runs.length > 1 ? (
        <ul aria-label="Runs, newest first" className="flex flex-wrap gap-2 print:hidden">
          {runs.map((run) => {
            const active = run.id === id;
            return (
              <li key={run.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSelected(run.id)}
                  className={cn(
                    "flex flex-col items-start rounded-md border px-3 py-1 text-left text-dense transition-colors",
                    active
                      ? "border-accent-line bg-accent-tint text-ink"
                      : "border-line-strong bg-surface text-ink-secondary hover:bg-surface-raised hover:text-ink",
                  )}
                >
                  <span className={cn(active && "font-medium")}>{RUN_KIND_WORD[run.kind]}</span>
                  <span className="font-mono text-2xs text-ink-muted">
                    {formatDateTime(run.created_at)}
                    {run.state === "failed" ? " · stopped" : run.state !== "done" ? " · running" : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {current.status === "loading" ? (
        <div role="status" aria-label="Loading the run log" className="flex flex-col gap-3">
          <Skeleton className="h-5 w-2/3 max-w-xl" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : null}
      {current.status === "error" ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-dense text-ink">The run log did not load. Nothing was changed</p>
          <Button size="sm" onClick={() => setAttempt((value) => value + 1)}>
            Try again
          </Button>
        </div>
      ) : null}
      {current.status === "ready" ? (
        <>
          <p className="font-mono text-xs text-ink-secondary">{summaryLine(current.run)}</p>
          <Loaded key={current.run.id} run={current.run} events={current.events} findings={findings} />
        </>
      ) : null}
    </div>
  );
}
