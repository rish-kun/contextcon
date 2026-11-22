"use client";

import { useEffect, useState } from "react";
import { getCase, getRun, isFixtureMode, type CaseDetail, type RunOut } from "@/lib/api/client";
import { useRunActivity } from "@/lib/run/use-run-activity";
import { ClaimStream } from "@/components/case/claim-stream";
import { RecheckStream } from "@/components/case/recheck-stream";
import { CandidateStream } from "@/components/discover/candidate-stream";
import { InvestorStream } from "@/components/investors/investor-stream";
import { RunLogScreen } from "@/components/run/run-log-screen";
import { RunView, type FindingsContext } from "@/components/run/run-view";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/toolbar";

const RUNS = [
  { value: "fx-run-discover", label: "Discover" },
  { value: "fx-run-investors", label: "Investor search" },
  { value: "fx-run-verify", label: "Verify" },
  { value: "fx-run-recheck", label: "Recheck" },
  { value: "fx-run-verify-shree", label: "Verify, stops at identity" },
];
const CASE_BASE = "/app/cases";

function findingsFor(detail: CaseDetail | null) {
  return function Findings(context: FindingsContext) {
    const { run } = context;
    if (run.kind === "discover") return <CandidateStream context={context} thesisId={run.thesis_id ?? ""} />;
    if (run.kind === "investor_discover") return <InvestorStream context={context} />;
    if (!detail) return null;
    const basePath = `${CASE_BASE}/${detail.case.id}`;
    return run.kind === "verify" ? (
      <ClaimStream context={context} detail={detail} basePath={basePath} />
    ) : (
      <RecheckStream context={context} detail={detail} basePath={basePath} />
    );
  };
}

function Live({ run, detail }: { run: RunOut; detail: CaseDetail | null }) {
  const { feed, setPaused } = useRunActivity(run);
  if (!feed.run) return null;
  return (
    <RunView
      run={feed.run}
      feed={feed}
      onPause={setPaused}
      form={run.kind === "recheck" || run.kind === "evaluate" ? "compact" : "full"}
      findings={findingsFor(detail)}
    />
  );
}

/** Every fixture run through the live view: followed live, then as a log with replay. */
export function RunGallery() {
  const [runId, setRunId] = useState(RUNS[0].value);
  const [take, setTake] = useState(0);
  const [loaded, setLoaded] = useState<{ run: RunOut; detail: CaseDetail | null } | null>(null);

  useEffect(() => {
    if (!isFixtureMode) return;
    let cancelled = false;
    void getRun(runId).then(async (run) => {
      const detail = run.case_id ? await getCase(run.case_id).catch(() => null) : null;
      if (!cancelled) setLoaded({ run, detail });
    });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!isFixtureMode) {
    return (
      <main className="mx-auto flex max-w-(--layout-content-max) flex-col gap-2 p-8">
        <h1 className="text-2xl font-medium text-ink">Live run view</h1>
        <p className="text-dense text-ink-secondary">
          This page replays recorded fixture runs. Start the app with NEXT_PUBLIC_API_MODE=fixtures to see it
        </p>
      </main>
    );
  }
  const current = loaded && loaded.run.id === runId ? loaded : null;

  return (
    <main className="mx-auto flex max-w-(--layout-content-max) flex-col gap-8 p-8">
      <header className="flex flex-col gap-3">
        <h1 className="text-2xl font-medium text-ink">Live run view</h1>
        <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">
          Each fixture run, followed from its recorded activity, then opened as a log. Every row is a
          stored event. Turn on reduced motion in the system settings to see that form.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Fixture run" value={runId} onChange={setRunId} options={RUNS} />
          <Button size="sm" onClick={() => setTake((value) => value + 1)}>
            Run again
          </Button>
        </div>
      </header>
      {current ? (
        <>
          <section aria-label="Live" className="flex flex-col gap-3">
            <h2 className="text-xl font-medium text-ink">Live</h2>
            <Live key={`${runId}:${take}`} run={current.run} detail={current.detail} />
          </section>
          <section aria-label="Run log" className="flex flex-col gap-3">
            <h2 className="text-xl font-medium text-ink">Run log</h2>
            <RunLogScreen key={runId} runs={[current.run]} findings={findingsFor(current.detail)} />
          </section>
        </>
      ) : (
        <p className="text-dense text-ink-muted">Loading the fixture run</p>
      )}
    </main>
  );
}
