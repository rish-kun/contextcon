"use client";

import Link from "next/link";
import { Button, Skeleton } from "@/components/ui";
import type { InvestorSearchSummary, ThesisSummary } from "@/lib/api/client";
import { formatShortDateTime, plural } from "@/lib/format";
import type { Load } from "./use-load";

const STATUS_LABEL: Record<ThesisSummary["status"], string> = {
  draft: "Draft · not searched",
  searching: "Searching",
  ready: "Finished",
  failed: "Did not finish",
};

/** `series_a` → `Series A`. The stage is the API's own value, only re-spaced. */
function readable(value: string): string {
  const words = value.split("_").filter(Boolean);
  return words
    .map((word, index) => (index === 0 || word.length === 1 ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function ListShell<T>({
  title,
  state,
  onRetry,
  failure,
  empty,
  children,
}: {
  title: string;
  state: Load<T[]>;
  onRetry: () => void;
  failure: string;
  empty: React.ReactNode;
  children: (items: T[]) => React.ReactNode;
}) {
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-ink">{title}</h2>
      {state.status === "loading" ? (
        <div role="status" aria-label={`Loading ${title.toLowerCase()}`} className="flex flex-col gap-2 border-t border-line pt-3">
          <Skeleton className="w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      ) : state.status === "error" ? (
        <div role="alert" className="flex flex-col items-start gap-2 border-t border-line pt-3">
          <p className="text-dense text-ink-secondary">
            {failure}. {state.message}
          </p>
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : state.data.length === 0 ? (
        <div className="flex flex-col items-start gap-2 border-t border-line pt-3">{empty}</div>
      ) : (
        <ul className="flex flex-col border-t border-line">{children(state.data)}</ul>
      )}
    </section>
  );
}

const ROW = "flex flex-col gap-1 border-b border-line py-3";
const TITLE = "line-clamp-2 rounded-xs text-dense text-ink underline-offset-4 hover:text-accent hover:underline";
const META = "font-mono text-2xs text-ink-muted";
const LIMIT = 4;

export function DiscoveryRuns({ state, onRetry }: { state: Load<ThesisSummary[]>; onRetry: () => void }) {
  return (
    <ListShell
      title="Recent discovery runs"
      state={state}
      onRetry={onRetry}
      failure="Discovery runs could not be loaded"
      empty={
        <>
          <p className="text-dense text-ink-secondary">No thesis has been searched yet</p>
          <Button asChild size="sm">
            <Link href="/app/discover">Start with a thesis</Link>
          </Button>
        </>
      }
    >
      {(theses) =>
        theses.slice(0, LIMIT).map((thesis) => (
          <li key={thesis.id} className={ROW}>
            <Link href={`/app/discover/${encodeURIComponent(thesis.id)}`} className={TITLE}>
              {thesis.text}
            </Link>
            <p className="text-xs text-ink-secondary">
              {STATUS_LABEL[thesis.status]} · {plural(thesis.criteria_count, "criterion", "criteria")} ·{" "}
              {plural(thesis.shortlist_count, "company", "companies")} shortlisted
            </p>
            <time dateTime={thesis.created_at} className={META}>
              {formatShortDateTime(thesis.created_at)}
            </time>
          </li>
        ))
      }
    </ListShell>
  );
}

export function InvestorSearches({
  state,
  onRetry,
}: {
  state: Load<InvestorSearchSummary[]>;
  onRetry: () => void;
}) {
  return (
    <ListShell
      title="Recent investor searches"
      state={state}
      onRetry={onRetry}
      failure="Investor searches could not be loaded"
      empty={
        <>
          <p className="text-dense text-ink-secondary">No investor search has been run yet</p>
          <Button asChild size="sm">
            <Link href="/app/investors">Find investors</Link>
          </Button>
        </>
      }
    >
      {(searches) =>
        searches.slice(0, LIMIT).map((search) => (
          <li key={search.id} className={ROW}>
            <Link href={`/app/investors/${encodeURIComponent(search.id)}`} className={TITLE}>
              {search.sector}
            </Link>
            <p className="text-xs text-ink-secondary">
              {search.location} · {readable(search.stage)} · {STATUS_LABEL[search.status]} ·{" "}
              {plural(search.entries_count, "investor")}
            </p>
            <time dateTime={search.created_at} className={META}>
              {formatShortDateTime(search.created_at)}
            </time>
          </li>
        ))
      }
    </ListShell>
  );
}
