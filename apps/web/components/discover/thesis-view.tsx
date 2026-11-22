"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  getThesis,
  resumeRun,
  type CriterionOut,
  type RunOut,
  type ThesisOut,
} from "@/lib/api/client";
import { useSound } from "@/lib/sound";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { asLiveSeed, errorText, isNotFound, isTerminal } from "./adapt";
import { CriteriaEditor } from "./criteria-editor";
import { EmptyState, ErrorNotice } from "./notice";
import { BudgetNotice, FailedRun, LiveRun, RunSummary } from "./run-panel";
import { Shortlist } from "./shortlist";
import { DiscoverHeader, DiscoverPage } from "./step-header";

type Load =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "error"; message: string }
  | { status: "ready"; thesis: ThesisOut };

/** Skeletons hold still after two seconds; from then on the wait is said in words. */
function LoadingThesis() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 2000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div role="status" aria-label="Loading the thesis" className="flex flex-col gap-4">
      <Skeleton className="h-6 w-2/3 max-w-xl" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-28 w-full" />
      {slow ? <p className="text-dense text-ink-secondary">Still working</p> : null}
    </div>
  );
}

/** The saved criteria, read-only, beside the shortlist they produced. */
function CriteriaSummary({
  criteria,
  onEdit,
}: {
  criteria: CriterionOut[];
  onEdit: () => void;
}) {
  return (
    <section aria-label="Criteria" className="rounded-lg border border-line bg-surface">
      <div className="flex items-center justify-between gap-3 px-4 pt-3 pb-2">
        <h3 className="text-sm font-medium text-ink">
          Criteria
          <span className="pl-2 font-mono text-xs font-normal text-ink-muted">{criteria.length}</span>
        </h3>
        <Button variant="quiet" size="sm" onClick={onEdit} className="-mr-2">
          Edit criteria
        </Button>
      </div>
      <ul className="divide-y divide-line border-t border-line">
        {criteria.map((criterion) => (
          <li key={criterion.id} className="flex gap-2 px-4 py-2 text-dense">
            <span
              aria-hidden
              className={cn(
                "mt-1.5 size-2 shrink-0 border border-ink",
                criterion.kind === "must" ? "bg-ink" : "bg-surface",
              )}
            />
            <span className="flex min-w-0 flex-col">
              <span className="text-ink">{criterion.label}</span>
              <span className="text-xs text-ink-muted">
                {criterion.kind === "must" ? "Must have" : "Preference"} ·{" "}
                {criterion.assessed_from_evidence ? "assessed from evidence" : "company record"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * One thesis: its criteria while it is a draft, the live run while it is searching, and
 * the shortlist once the run has finished.
 */
export function ThesisView({ thesisId, live }: { thesisId: string; live: boolean }) {
  const router = useRouter();
  const { playCue } = useSound();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  // Only the first render decides whether a just-started run is replayed.
  const [startLive] = useState(live);
  const [liveSeed, setLiveSeed] = useState<RunOut | null>(null);
  const [editing, setEditing] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const fetchThesis = useCallback(
    () =>
      getThesis(thesisId).then(
        (thesis): Load => ({ status: "ready", thesis }),
        (caught): Load =>
          isNotFound(caught)
            ? { status: "missing" }
            : { status: "error", message: errorText(caught) },
      ),
    [thesisId],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchThesis().then((next) => {
      if (cancelled) return;
      setLoad(next);
      const run = next.status === "ready" ? next.thesis.run : null;
      if (run && (!isTerminal(run) || startLive)) setLiveSeed(asLiveSeed(run));
    });
    return () => {
      cancelled = true;
    };
  }, [fetchThesis, startLive]);

  /** The run reported done or failed: play the cue, then read the thesis it produced. */
  async function settled(run: RunOut) {
    playCue(run.state === "failed" ? "error" : "run_finished");
    setLoad(await fetchThesis());
    setLiveSeed(null);
    if (startLive) router.replace(`/app/discover/${encodeURIComponent(thesisId)}`, { scroll: false });
  }

  function started(run: RunOut, thesis: ThesisOut) {
    setLoad({ status: "ready", thesis });
    setEditing(false);
    setLiveSeed(asLiveSeed(run));
  }

  async function resume(run: RunOut) {
    setResuming(true);
    setResumeError(null);
    try {
      setLiveSeed(asLiveSeed(await resumeRun(run.id)));
    } catch (caught) {
      setResumeError(errorText(caught));
    } finally {
      setResuming(false);
    }
  }

  if (load.status === "loading") {
    return (
      <DiscoverPage>
        <DiscoverHeader />
        <LoadingThesis />
      </DiscoverPage>
    );
  }

  if (load.status === "missing") {
    return (
      <DiscoverPage>
        <DiscoverHeader />
        <EmptyState
          title="This thesis was not found"
          actions={
            <Button asChild variant="primary">
              <Link href="/app/discover/new">New screening</Link>
            </Button>
          }
        >
          It may have been deleted, or the link may belong to another workspace.
        </EmptyState>
      </DiscoverPage>
    );
  }

  if (load.status === "error") {
    return (
      <DiscoverPage>
        <DiscoverHeader />
        <ErrorNotice
          title="The thesis could not be loaded"
          className="max-w-2xl"
          actions={
            <Button
              size="sm"
              onClick={() => {
                setLoad({ status: "loading" });
                void fetchThesis().then(setLoad);
              }}
            >
              Try again
            </Button>
          }
        >
          {load.message}
        </ErrorNotice>
      </DiscoverPage>
    );
  }

  const { thesis } = load;
  const run = thesis.run;
  const phase = liveSeed
    ? "searching"
    : editing || !run
      ? "criteria"
      : run.state === "failed"
        ? "failed"
        : isTerminal(run)
          ? "shortlist"
          : "searching";

  const header = (
    <DiscoverHeader
      step={phase === "criteria" ? 2 : 3}
      actions={
        <Button asChild>
          <Link href="/app/discover/new">New screening</Link>
        </Button>
      }
    >
      <p className="max-w-3xl text-sm text-ink-secondary">{thesis.text}</p>
    </DiscoverHeader>
  );

  if (phase === "criteria") {
    return (
      <DiscoverPage>
        {header}
        <CriteriaEditor
          thesis={thesis}
          onStarted={started}
          onCancel={run && isTerminal(run) ? () => setEditing(false) : undefined}
        />
      </DiscoverPage>
    );
  }

  if (phase === "searching") {
    const seed = liveSeed ?? run;
    return (
      <DiscoverPage>
        {header}
        {seed ? <LiveRun key={seed.id} seed={seed} onSettled={settled} /> : null}
      </DiscoverPage>
    );
  }

  if (phase === "failed" && run) {
    return (
      <DiscoverPage>
        {header}
        <div className="flex max-w-4xl flex-col gap-4">
          <FailedRun
            run={run}
            onResume={() => resume(run)}
            resuming={resuming}
            resumeError={resumeError}
          />
          <div>
            <Button variant="quiet" onClick={() => setEditing(true)}>
              Edit criteria
            </Button>
          </div>
        </div>
      </DiscoverPage>
    );
  }

  return (
    <DiscoverPage>
      {header}
      <div className="grid grid-cols-1 items-start gap-8 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-6">
          {run ? <BudgetNotice run={run} /> : null}
          <Shortlist
            items={thesis.shortlist}
            thesisId={thesis.id}
            run={run}
            onEditCriteria={() => setEditing(true)}
          />
        </div>
        <aside className="flex flex-col gap-4 xl:sticky xl:top-20">
          {run ? <RunSummary run={run} /> : null}
          <CriteriaSummary criteria={thesis.criteria} onEdit={() => setEditing(true)} />
        </aside>
      </div>
    </DiscoverPage>
  );
}
