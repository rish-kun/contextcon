"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getThesis, type ThesisOut } from "@/lib/api/client";
import { RunLogScreen } from "@/components/run/run-log-screen";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "./adapt";
import { CandidateStream } from "./candidate-stream";
import { DiscoverHeader, DiscoverPage } from "./step-header";

/** The run log of one thesis: what its search did, read and cost, and a replay of it. */
export function ThesisRunLog({ thesisId }: { thesisId: string }) {
  const [state, setState] = useState<{ thesis: ThesisOut | null; error: string | null; loading: boolean }>({
    thesis: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    getThesis(thesisId).then(
      (thesis) => {
        if (!cancelled) setState({ thesis, error: null, loading: false });
      },
      (caught) => {
        if (!cancelled) setState({ thesis: null, error: errorText(caught), loading: false });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [thesisId]);

  const run = state.thesis?.run ?? null;
  return (
    <DiscoverPage>
      <DiscoverHeader step={3}>
        <p className="max-w-3xl text-sm text-ink-secondary">
          Run log
          {state.thesis ? <span> · {state.thesis.text}</span> : null}
          {" · "}
          <Link
            href={`/app/discover/${encodeURIComponent(thesisId)}`}
            className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Back to the shortlist
          </Link>
        </p>
      </DiscoverHeader>
      {state.loading ? (
        <div role="status" aria-label="Loading the run log" className="flex flex-col gap-3">
          <Skeleton className="h-5 w-2/3 max-w-xl" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : state.error ? (
        <p className="text-dense text-ink">The thesis did not load: {state.error}</p>
      ) : (
        <RunLogScreen
          runs={run ? [run] : []}
          empty="No search has been run for this thesis yet"
          findings={(context) => <CandidateStream context={context} thesisId={thesisId} />}
        />
      )}
    </DiscoverPage>
  );
}
