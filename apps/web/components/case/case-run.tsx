"use client";

import { useState } from "react";
import type { CaseDetail } from "@/lib/api/client";
import { useNow } from "@/lib/run/use-run-activity";
import { deriveView, visibleEvents } from "@/lib/run/activity-store";
import { cn } from "@/lib/utils";
import { CrustdataTally } from "@/components/run/crustdata-tally";
import { RunLogScreen } from "@/components/run/run-log-screen";
import { RunView, type FindingsContext } from "@/components/run/run-view";
import { SourceTicker } from "@/components/run/source-ticker";
import { StepChecklist, stepsDone } from "@/components/run/step-checklist";
import { Panel, PanelHeader } from "@/components/ui/card";
import { useCase, useCaseDetail } from "./case-context";
import { ClaimStream } from "./claim-stream";
import { RecheckStream } from "./recheck-stream";

const isShort = (kind: string) => kind === "recheck" || kind === "evaluate";

function caseFindings(detail: CaseDetail, basePath: string) {
  return function Findings(context: FindingsContext) {
    return isShort(context.run.kind) ? (
      <RecheckStream context={context} detail={detail} basePath={basePath} />
    ) : (
      <ClaimStream context={context} detail={detail} basePath={basePath} />
    );
  };
}

/**
 * The run band in the case header, on every tab: what the analyst is doing now, elapsed
 * time, cost, and the steps on one line. A recheck also shows its before → after rows
 * here, since a recheck is short and its result is the change itself. The claim ledger on
 * the Claims tab is the findings of a Verify run; from `xl` the steps, the Crustdata tally
 * and the sources sit beside it in `RunRail`.
 *
 * The finished line stays only for a run this session watched, so a past run adds no noise.
 */
export function CaseRun({ className }: { className?: string }) {
  const { run, runActive, runError, feed, setFeedPaused, basePath, verify, detail, readOnly } =
    useCase();
  const [watched, setWatched] = useState<string | null>(null);
  if (runActive && run && watched !== run.id) setWatched(run.id);
  const shown = feed.run && run && feed.run.id === run.id && (runActive || watched === run.id) ? feed.run : null;

  return (
    <>
      {runError ? (
        <p role="alert" className="text-dense text-contradicted">
          The run did not start: {runError}
        </p>
      ) : null}
      {shown && detail ? (
        <RunView
          run={shown}
          feed={feed}
          form="compact"
          onPause={setFeedPaused}
          findings={
            isShort(shown.kind)
              ? (context) => <RecheckStream context={context} detail={detail} basePath={basePath} />
              : undefined
          }
          logHref={`${basePath}/log`}
          sourcesHref={`${basePath}/sources`}
          costHref={`${basePath}/cost`}
          onResume={readOnly ? undefined : () => void verify()}
          className={cn("print:hidden", className)}
        />
      ) : null}
    </>
  );
}

/** True while the case's right rail should show the run and not the assessment. */
export function useRunRail(): boolean {
  const { run, runActive, feed } = useCase();
  return runActive && run !== null && feed.run?.id === run.id && !isShort(run.kind);
}

/**
 * The steps, the Crustdata tally and the sources of the run being followed, in the
 * case's right rail while the run is going. Clicking a step filters the tally and the
 * sources to what that step read.
 */
export function RunRail({ className }: { className?: string }) {
  const { feed, activity, run } = useCase();
  const [selected, setSelected] = useState<string | null>(null);
  const nowMs = useNow(true);
  const current = feed.run ?? run;
  if (!current) return null;
  const events = selected
    ? visibleEvents(feed.events, feed.upto).filter((event) => event.step_key === selected)
    : null;
  const scoped = events ? deriveView(events) : activity;
  const label = selected ? (current.steps.find((step) => step.key === selected)?.label ?? null) : null;

  return (
    <aside className={cn("flex flex-col gap-4", className)} aria-label="The run in progress">
      <Panel aria-label="Steps">
        <PanelHeader title="Steps" meta={current.steps.length > 0 ? stepsDone(current.steps) : undefined} />
        {current.steps.length > 0 ? (
          <StepChecklist
            steps={current.steps}
            activity={activity.steps}
            selected={selected}
            onSelect={setSelected}
            announce={false}
          />
        ) : (
          <p className="px-4 py-3 text-dense text-ink-muted">Waiting for the first step</p>
        )}
      </Panel>
      <CrustdataTally kind={current.kind} view={scoped} />
      <SourceTicker
        sources={scoped.sources}
        counts={scoped.sourceCounts}
        nowMs={nowMs}
        settledSeq={feed.settled.sources}
        skipped={feed.skipped.sources}
        live
        filterLabel={label}
        onClearFilter={() => setSelected(null)}
      />
    </aside>
  );
}

/** The Run log tab: every run of this case, newest first, opened with the live view's own parts. */
export function CaseRunLog() {
  const detail = useCaseDetail();
  const { basePath } = useCase();
  const runs = [...detail.runs].reverse();
  return <RunLogScreen runs={runs} findings={caseFindings(detail, basePath)} empty="Run verification to record the first run" />;
}
