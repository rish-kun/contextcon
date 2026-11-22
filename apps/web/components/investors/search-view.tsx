"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  ApiError,
  getInvestorSearch,
  type InvestorSearchOut,
  resumeRun,
  type RunOut,
} from "@/lib/api/client";
import { formatCredits, plural } from "@/lib/format";
import { useRunActivity } from "@/lib/run/use-run-activity";
import { CostReadout, HatchedBlock, RunProgress } from "@/components/dealproof";
import { RunView } from "@/components/run/run-view";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  budgetReached,
  finishedSeconds,
  isTerminal,
  skippedForBudget,
  toCost,
  toRun,
} from "./adapt";
import { applyFixtureState, type FixtureState } from "./fixture-states";
import { editHref, profileLine } from "./format";
import { InvestorStream } from "./investor-stream";
import { RankingCaveat, scopeLine, Shortlist } from "./shortlist";
import { useLoad } from "./use-load";

function Notice({
  title,
  children,
  actions,
}: {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-line bg-surface p-5">
      <div className="flex max-w-2xl flex-col gap-1">
        <h2 className="text-xl font-medium text-ink">{title}</h2>
        <p className="text-sm text-ink-secondary">{children}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

function LoadingSearch() {
  return (
    <div role="status" aria-label="Loading the investor search" className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-8 w-80 max-w-full" />
        <Skeleton className="w-96 max-w-full" />
      </div>
      <Skeleton className="h-10 w-full rounded-lg" />
      <div className="flex flex-col gap-3">
        {[0, 1, 2].map((row) => (
          <Skeleton key={row} className="h-32 w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}

/**
 * One investor search: the business it was run for, the run while it works, then the
 * ranked shortlist with its cost. Loading, not found, failed, unfinished, budget-limited
 * and empty searches each say what happened in plain words.
 */
export function SearchView({
  id,
  fresh = false,
  fixtureState = null,
}: {
  id: string;
  /** Arrived straight from the form: follow the run even if it has already finished. */
  fresh?: boolean;
  fixtureState?: FixtureState | null;
}) {
  const router = useRouter();
  const { data, error, loading, reload } = useLoad(id, getInvestorSearch);
  const [demo, setDemo] = useState(fixtureState);
  const [refollow, setRefollow] = useState(false);
  const [followed, setFollowed] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);

  const search = useMemo<InvestorSearchOut | null>(
    () => (data ? applyFixtureState(data, demo) : null),
    [data, demo],
  );
  const run = search?.run ?? null;
  const wantsReplay = fresh || refollow || demo === "running";
  const following =
    run !== null && (!isTerminal(run) || (wantsReplay && followed !== run.id));

  // The run's stream, activity and pacing. It is followed while `following` holds, and
  // what it showed stays on screen after it ends so the result folds in, not swaps in.
  const { feed, setPaused } = useRunActivity(following ? run : null, {
    onSettled: (settled) => {
      setFollowed(settled.id);
      setRefollow(false);
      reload();
      if (fresh) router.replace(`/app/investors/${encodeURIComponent(id)}`, { scroll: false });
    },
  });

  if (loading) return <LoadingSearch />;

  if (!search) {
    const notFound = error instanceof ApiError && error.status === 404;
    return notFound ? (
      <Notice
        title="Search not found"
        actions={
          <Button asChild variant="primary">
            <Link href="/app/investors/new">Find investors</Link>
          </Button>
        }
      >
        No investor search has this address. It may have been removed when its retention
        period ended.
      </Notice>
    ) : (
      <Notice title="This search could not be loaded" actions={<Button onClick={reload}>Try again</Button>}>
        DealProof could not reach the search record. Nothing was changed and nothing was spent.
      </Notice>
    );
  }

  /** This session watched the run, live or just finished. */
  const watched = run !== null && feed.run?.id === run.id && demo !== "failed" ? feed.run : null;
  const shownRun: RunOut | null = !run
    ? null
    : watched
      ? watched
      : following
        ? { ...run, state: "running", steps: isTerminal(run) ? [] : run.steps }
        : run;
  const elapsed = following || !run ? 0 : (finishedSeconds(run) ?? 0);
  const running = shownRun !== null && !isTerminal(shownRun);
  const failed = !running && (shownRun?.state === "failed" || search.status === "failed");
  const failedStep = shownRun?.steps.find((step) => step.state === "failed");
  const skipped = shownRun ? skippedForBudget(shownRun).length : 0;
  const overBudget = !running && shownRun !== null && budgetReached(shownRun);
  const edit = editHref(search.profile);

  async function resume() {
    if (!run) return;
    setResuming(true);
    try {
      await resumeRun(run.id);
      setDemo(null);
      setFollowed(null);
      setRefollow(true);
      reload();
    } catch {
      /* the stopped run stays on screen with its reason; the button can be pressed again */
    } finally {
      setResuming(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-medium text-ink">{search.profile.sector}</h1>
          <p className="text-sm text-ink-secondary">
            <span className="text-ink-muted">Your business · </span>
            {profileLine(search.profile)}
          </p>
        </div>
        <Button asChild>
          <Link href={edit}>Edit search</Link>
        </Button>
      </header>

      {watched ? (
        <RunView
          run={watched}
          feed={feed}
          onPause={setPaused}
          logHref={`/app/investors/${encodeURIComponent(id)}/log`}
          onResume={resume}
          resuming={resuming}
          findings={(context) =>
            // The ranked shortlist takes the stream's place once the search has been read again.
            !running && search.entries.length > 0 ? (
              <div className="animate-fade-in motion-reduce:animate-none">
                <Shortlist search={search} />
              </div>
            ) : (
              <InvestorStream context={context} />
            )
          }
        />
      ) : shownRun ? (
        <RunProgress
          run={toRun(shownRun, elapsed)}
          onRetryStep={failed ? resume : undefined}
          logHref={`/app/investors/${encodeURIComponent(id)}/log`}
        />
      ) : null}

      {running && !watched ? (
        <p className="rounded-lg border border-dashed border-line-strong px-5 py-4 text-sm text-ink-secondary">
          Investors are listed when the run finishes. Each one needs a dated funding record
          behind it, so nothing is shown from a search that is still reading.
        </p>
      ) : null}

      {!running && !shownRun && search.entries.length === 0 ? (
        <Notice
          title="This search has not started"
          actions={
            <>
              <Button onClick={reload}>Check again</Button>
              <Button asChild variant="quiet">
                <Link href={edit}>Edit search</Link>
              </Button>
            </>
          }
        >
          No run is recorded for this search yet, so there is nothing to list and nothing has
          been spent.
        </Notice>
      ) : null}

      {failed ? (
        <Notice
          title="The search did not finish"
          actions={
            <>
              {run ? (
                <Button variant="primary" onClick={resume} disabled={resuming}>
                  {resuming ? "Resuming" : "Resume run"}
                </Button>
              ) : null}
              <Button asChild>
                <Link href={edit}>Edit search</Link>
              </Button>
            </>
          }
        >
          {failedStep
            ? `${failedStep.label} did not finish: ${failedStep.error ?? "no reason recorded"}. Previous steps are kept.`
            : "The run stopped before its last step. Previous steps are kept."}{" "}
          {search.entries.length > 0
            ? "The list below comes from an unfinished search and may be missing investors."
            : "No investors are listed from an unfinished search."}
        </Notice>
      ) : null}

      {overBudget && shownRun ? (
        <HatchedBlock>
          <p className="text-sm text-ink">
            <span className="font-medium">Credit budget reached.</span>{" "}
            {skipped > 0
              ? `${plural(skipped, "step")} did not run.`
              : `The search stopped reading at ${formatCredits(shownRun.budget_credits)} credits.`}{" "}
            This list covers only the comparable companies read before the limit. Investors
            behind the companies that were not read are missing from it, not ruled out.
          </p>
        </HatchedBlock>
      ) : null}

      {!running && !watched && search.entries.length > 0 ? <Shortlist search={search} /> : null}

      {!running && !failed && shownRun && search.entries.length === 0 ? (
        <Notice
          title="No investors found with dated comparable rounds"
          actions={
            <Button asChild variant="primary">
              <Link href={edit}>Edit search</Link>
            </Button>
          }
        >
          DealProof lists an investor only when a dated funding record connects them to a
          comparable company. Broaden the sector or stage and search again.{" "}
          <span className="text-ink-muted">{scopeLine(search)}.</span>
        </Notice>
      ) : null}

      {!running && shownRun ? (
        <section aria-label="Cost of this search">
          {shownRun.steps.some((step) => step.state === "done") ? (
            <CostReadout cost={toCost(shownRun)} title="This search cost" />
          ) : (
            <p className="text-sm text-ink-secondary">
              <span className="font-medium text-ink">No usage recorded yet.</span> Credits and
              model usage appear here once a search step runs.
            </p>
          )}
        </section>
      ) : null}

      <RankingCaveat />
    </div>
  );
}
