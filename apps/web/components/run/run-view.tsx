"use client";

import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { RunOut, StepOut } from "@/lib/api/client";
import { CLAIM_STATUS_LABEL } from "@/lib/labels";
import {
  deriveView,
  visibleEvents,
  type RunActivityView,
} from "@/lib/run/activity-store";
import type { Activity } from "@/lib/run/types";
import { type RunFeedSnapshot, useNow } from "@/lib/run/use-run-activity";
import { transition } from "@/lib/transitions";
import type { ClaimStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/components/insight/hooks";
import { Panel, PanelHeader } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { CrustdataTally } from "./crustdata-tally";
import { useLatestAtMost } from "./now-line";
import { RunHeader } from "./run-header";
import { SourceTicker } from "./source-ticker";
import { StepChecklist, stepsDone } from "./step-checklist";
import { RUN_KIND_WORD } from "./wording";

const SETTLED = new Set<StepOut["state"]>(["done", "failed", "skipped_budget"]);

/** What a findings stream is given to draw from. */
export interface FindingsContext {
  run: RunOut;
  view: RunActivityView;
  /** The events on screen, oldest first. */
  events: Activity[];
  /** True for a row whose event arrived in front of the reader: it may animate in. */
  isNew: (seq: number) => boolean;
  /** The run reported done or failed. */
  terminal: boolean;
  /** True once the step with this key has settled, or the run has ended. */
  stepSettled: (stepKey: string | null) => boolean;
  /** The last burst of findings shown at once. */
  skipped: { count: number; seq: number } | null;
  nowMs: number;
}

export interface RunViewProps {
  run: RunOut;
  feed: RunFeedSnapshot;
  /** `replay` plays stored events: no orb, no pause control, and the columns stay open. */
  mode?: "live" | "replay";
  /** `compact` is the docked form for short runs: one panel, steps on one line. */
  form?: "full" | "compact";
  /** The clock for relative times. Defaults to the wall clock; a replay passes its own. */
  nowMs?: number;
  onPause?: (paused: boolean) => void;
  /** The findings stream for this pipeline. It is the result, being assembled. */
  findings?: (context: FindingsContext) => React.ReactNode;
  logHref?: string;
  sourcesHref?: string;
  costHref?: string;
  onResume?: () => void;
  resuming?: boolean;
  onRetryStep?: (step: StepOut) => void;
  /** Sits above the header: the replay banner. */
  banner?: React.ReactNode;
  className?: string;
}

/** What a screen reader hears when a finding settles. At most one every two seconds. */
function findingAnnouncement(view: RunActivityView, stepSettled: (key: string | null) => boolean): string {
  let latest: { seq: number; text: string } = { seq: 0, text: "" };
  for (const claim of view.claims.values()) {
    if (claim.stage !== "settled" || claim.seq <= latest.seq || !claim.status) continue;
    const status = CLAIM_STATUS_LABEL[claim.status as ClaimStatus] ?? claim.status;
    latest = { seq: claim.seq, text: `Claim, ${claim.detail ?? "checked"}: ${status}` };
  }
  if (view.companiesScoredSeq !== null && view.companiesScoredSeq > latest.seq && stepSettled(view.companiesScoredStep)) {
    latest = { seq: view.companiesScoredSeq, text: "Shortlist ranked" };
  }
  if (view.investorsRankedSeq !== null && view.investorsRankedSeq > latest.seq && stepSettled(view.investorsRankedStep)) {
    latest = { seq: view.investorsRankedSeq, text: "Investor shortlist ranked" };
  }
  return latest.text;
}

/**
 * The live run view: header band, step checklist, the findings stream, the Crustdata
 * tally and the source ticker. One component draws every kind of run; only the findings
 * differ, and they are passed in.
 *
 * Every region is fed by stored events. A region with nothing to show yet says so in one
 * muted line and never shows a skeleton that implies content. When the run finishes the
 * header folds to one line, the side columns fade away and the findings widen in place:
 * the findings were the result all along, so nothing is swapped.
 */
export function RunView({
  run,
  feed,
  mode = "live",
  form = "full",
  nowMs: nowOverride,
  onPause,
  findings,
  logHref,
  sourcesHref,
  costHref,
  onResume,
  resuming,
  onRetryStep,
  banner,
  className,
}: RunViewProps) {
  const reduced = useReducedMotion() ?? false;
  const wide = useMediaQuery("(min-width: 48rem)");
  const terminal = run.state === "done" || run.state === "failed";
  const wallClock = useNow(mode === "live" && !terminal);
  const nowMs = nowOverride ?? (terminal && feed.endedAt ? feed.endedAt : wallClock);
  // Relative times still move under reduced motion, but only every ten seconds.
  const tickerNow = reduced ? Math.floor(nowMs / 10_000) * 10_000 : nowMs;
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [stepsOpen, setStepsOpen] = useState(false);

  const shown = useMemo(() => visibleEvents(feed.events, feed.upto), [feed.events, feed.upto]);
  const view = useMemo(() => deriveView(shown), [shown]);
  const scoped = useMemo(
    () => (selectedStep ? deriveView(shown.filter((event) => event.step_key === selectedStep)) : view),
    [shown, selectedStep, view],
  );

  const stepSettled = (key: string | null) => {
    if (terminal) return true;
    const step = key ? run.steps.find((s) => s.key === key) : undefined;
    return step ? SETTLED.has(step.state) : false;
  };
  const context: FindingsContext = {
    run,
    view,
    events: shown,
    isNew: (seq) => seq > feed.settled.findings,
    terminal,
    stepSettled,
    skipped: feed.skipped.findings,
    nowMs,
  };
  const announcement = useLatestAtMost(findingAnnouncement(view, stepSettled), 2000);

  // A finished live run folds. A failed one stays open: the steps and sources are the diagnosis.
  const folded = mode === "live" && run.state === "done";
  const selectedLabel = selectedStep ? (run.steps.find((s) => s.key === selectedStep)?.label ?? null) : null;

  // Keep the reader's place when the columns fold: the findings column moves up as the
  // side columns leave, so the page scrolls by the same amount.
  const findingsRef = useRef<HTMLDivElement>(null);
  const lastTop = useRef<number | null>(null);
  const wasFolded = useRef(folded);
  useLayoutEffect(() => {
    const node = findingsRef.current;
    if (!node) return;
    const top = node.getBoundingClientRect().top;
    if (folded && !wasFolded.current && lastTop.current !== null && lastTop.current < 0) {
      window.scrollBy(0, top - lastTop.current);
    }
    wasFolded.current = folded;
    lastTop.current = node.getBoundingClientRect().top;
  });

  const header = (
    <RunHeader
      run={run}
      view={view}
      mode={mode}
      nowMs={nowMs}
      startedAt={feed.startedAt}
      endedAt={terminal ? feed.endedAt : null}
      paused={feed.paused}
      held={feed.held}
      onPause={onPause}
      logHref={logHref}
      sourcesHref={sourcesHref}
      costHref={costHref}
      onResume={onResume}
      resuming={resuming}
      compact={form === "compact" || !wide}
    />
  );
  const liveRegion = (
    <p className="sr-only" aria-live="polite">
      {mode === "live" ? announcement : null}
    </p>
  );
  const label = `${RUN_KIND_WORD[run.kind]} run for ${run.subject}`;
  const body = findings ? findings(context) : null;

  if (form === "compact") {
    return (
      <section aria-label={label} className={cn("flex flex-col gap-3", className)}>
        {banner}
        <Panel>
          {header}
          {folded ? null : (
            <div className="border-t border-line px-4 py-2">
              {run.steps.length > 0 ? (
                <StepChecklist steps={run.steps} activity={view.steps} orientation="line" announce={mode === "live"} />
              ) : (
                <p className="text-dense text-ink-muted">Waiting for the first step</p>
              )}
            </div>
          )}
          {body ? <div className="border-t border-line">{body}</div> : null}
          {folded ? null : (
            <CrustdataTally kind={run.kind} view={view} form="line" className="border-t border-line px-4 py-2" />
          )}
        </Panel>
        {liveRegion}
      </section>
    );
  }

  const running = run.steps.find((step) => step.state === "running");
  const stepsPanel = (
    <Panel aria-label="Steps">
      {wide ? (
        <PanelHeader title="Steps" meta={run.steps.length > 0 ? stepsDone(run.steps) : undefined} />
      ) : (
        <button
          type="button"
          aria-expanded={stepsOpen}
          onClick={() => setStepsOpen((value) => !value)}
          className={cn(
            "focus-inset flex min-h-11 w-full items-center justify-between gap-3 px-4 py-2 text-left text-dense text-ink",
            stepsOpen ? "rounded-t-lg border-b border-line" : "rounded-lg",
          )}
        >
          <span>
            <span className="font-mono text-xs text-ink-muted">
              Step {run.steps.length > 0 ? stepsDone(run.steps) : "0 of 0"}
            </span>
            {running ? ` · ${running.label}` : null}
          </span>
          <Icon icon={ChevronDown} className={cn("text-ink-muted transition-transform", stepsOpen && "rotate-180")} />
        </button>
      )}
      {wide || stepsOpen ? (
        run.steps.length > 0 ? (
          <StepChecklist
            steps={run.steps}
            activity={view.steps}
            selected={selectedStep}
            onSelect={setSelectedStep}
            onRetry={onRetryStep}
            announce={mode === "live"}
          />
        ) : (
          <p className="px-4 py-3 text-dense text-ink-muted">Waiting for the first step</p>
        )
      ) : null}
    </Panel>
  );

  const ticker = (
    <SourceTicker
      sources={scoped.sources}
      counts={scoped.sourceCounts}
      nowMs={tickerNow}
      settledSeq={feed.settled.sources}
      skipped={feed.skipped.sources}
      live={!terminal}
      filterLabel={selectedLabel}
      onClearFilter={() => setSelectedStep(null)}
      form={wide ? "panel" : "strip"}
    />
  );

  return (
    <section aria-label={label} className={cn("flex flex-col gap-4", className)}>
      {banner}
      <motion.div layout="position" transition={transition.slow}>
        <Panel>{header}</Panel>
      </motion.div>

      <div
        className={cn(
          "relative grid grid-cols-1 items-start gap-4",
          !folded && "md:grid-cols-[17.5rem_minmax(0,1fr)] xl:grid-cols-[17.5rem_minmax(0,1fr)_20rem]",
        )}
      >
        <AnimatePresence mode="popLayout" initial={false}>
          {folded ? null : (
            <motion.aside
              key="steps"
              exit={{ opacity: 0 }}
              transition={transition.base}
              className="md:sticky md:top-20 md:row-span-2 md:max-h-[calc(100dvh-6rem)] md:overflow-y-auto xl:row-span-1"
            >
              {stepsPanel}
            </motion.aside>
          )}
          {folded ? null : (
            <motion.aside
              key="side"
              exit={{ opacity: 0 }}
              transition={transition.base}
              className="grid grid-cols-1 items-start gap-4 md:col-start-2 md:row-start-1 md:grid-cols-2 xl:sticky xl:top-20 xl:col-start-3 xl:grid-cols-1"
            >
              <CrustdataTally kind={run.kind} view={scoped} form={wide ? "panel" : "line"} />
              {wide ? ticker : null}
            </motion.aside>
          )}
          <motion.div
            key="findings"
            ref={findingsRef}
            layout="position"
            transition={transition.slow}
            className={cn("min-w-0", !folded && "md:col-start-2 md:row-start-2 xl:row-start-1")}
          >
            {body}
          </motion.div>
          {folded || wide ? null : (
            <motion.div key="strip" exit={{ opacity: 0 }} transition={transition.base}>
              {ticker}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      {liveRegion}
    </section>
  );
}
