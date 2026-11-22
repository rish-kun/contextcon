"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { listTheses, type Schemas, type ThesisSummary } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "./adapt";
import { EmptyState, ErrorNotice } from "./notice";
import { DiscoverHeader, DiscoverPage } from "./step-header";

const STATUS: Record<Schemas["ThesisStatus"], string> = {
  draft: "Criteria ready, not searched",
  searching: "Searching",
  ready: "Shortlist ready",
  failed: "Search stopped",
};

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; theses: ThesisSummary[] };

/** Every thesis in the workspace, newest first, each a link to its shortlist. */
export function ThesisList() {
  const [load, setLoad] = useState<Load>({ status: "loading" });

  const fetchTheses = useCallback(
    () =>
      listTheses().then(
        (theses): Load => ({
          status: "ready",
          theses: theses.sort((a, b) => b.created_at.localeCompare(a.created_at)),
        }),
        (caught): Load => ({ status: "error", message: errorText(caught) }),
      ),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchTheses().then((next) => {
      if (!cancelled) setLoad(next);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchTheses]);

  const newThesis = (
    <Button asChild variant="primary">
      <Link href="/app/discover/new">New thesis</Link>
    </Button>
  );

  return (
    <DiscoverPage>
      <DiscoverHeader actions={newThesis}>
        <p className="max-w-3xl text-sm text-ink-secondary">
          Each thesis keeps its criteria, its search run and the shortlist it produced.
        </p>
      </DiscoverHeader>

      {load.status === "loading" ? (
        <div role="status" aria-label="Loading theses" className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : null}

      {load.status === "error" ? (
        <ErrorNotice
          title="The theses could not be loaded"
          className="max-w-2xl"
          actions={
            <Button
              size="sm"
              onClick={() => {
                setLoad({ status: "loading" });
                void fetchTheses().then(setLoad);
              }}
            >
              Try again
            </Button>
          }
        >
          {load.message}
        </ErrorNotice>
      ) : null}

      {load.status === "ready" && load.theses.length === 0 ? (
        <EmptyState title="No theses yet" actions={newThesis}>
          A thesis says what you are looking for in plain words. DealProof turns it into
          criteria you can edit, then searches live company data for companies that match.
        </EmptyState>
      ) : null}

      {load.status === "ready" && load.theses.length > 0 ? (
        <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
          {load.theses.map((thesis) => (
            <li key={thesis.id}>
              <Link
                href={`/app/discover/${encodeURIComponent(thesis.id)}`}
                className="focus-inset flex flex-col gap-1 px-4 py-3 transition-colors hover:bg-surface-raised sm:px-5"
              >
                <span className="text-sm text-ink">{thesis.text}</span>
                <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-secondary">
                  <span>{STATUS[thesis.status]}</span>
                  <span className="font-mono text-ink-muted">
                    {plural(thesis.criteria_count, "criterion", "criteria")} ·{" "}
                    {plural(thesis.shortlist_count, "company", "companies")} ·{" "}
                    {formatDate(thesis.created_at)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </DiscoverPage>
  );
}
