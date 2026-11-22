"use client";

import Link from "next/link";
import { getInvestorSearch } from "@/lib/api/client";
import { RunLogScreen } from "@/components/run/run-log-screen";
import { Skeleton } from "@/components/ui/skeleton";
import { profileLine } from "./format";
import { InvestorStream } from "./investor-stream";
import { useLoad } from "./use-load";

/** The run log of one investor search: what it did, read and cost, and a replay of it. */
export function InvestorRunLog({ id }: { id: string }) {
  const { data, loading } = useLoad(id, getInvestorSearch);
  const back = `/app/investors/${encodeURIComponent(id)}`;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-medium text-ink">Run log</h1>
        <p className="text-sm text-ink-secondary">
          {data ? `${data.profile.sector} · ${profileLine(data.profile)} · ` : null}
          <Link
            href={back}
            className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Back to the investors
          </Link>
        </p>
      </header>
      {loading ? (
        <div role="status" aria-label="Loading the run log" className="flex flex-col gap-3">
          <Skeleton className="h-5 w-2/3 max-w-xl" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : data ? (
        <RunLogScreen
          runs={data.run ? [data.run] : []}
          empty="No search has been run yet"
          findings={(context) => <InvestorStream context={context} />}
        />
      ) : (
        <p className="text-dense text-ink">The investor search did not load. Nothing was changed</p>
      )}
    </div>
  );
}
