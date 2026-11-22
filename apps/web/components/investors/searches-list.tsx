"use client";

import Link from "next/link";
import { type InvestorSearchSummary, listInvestorSearches } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { stageLabel } from "./format";
import { useLoad } from "./use-load";

const STATUS_LABEL: Record<InvestorSearchSummary["status"], string> = {
  draft: "Not started",
  searching: "Searching",
  ready: "Finished",
  failed: "Did not finish",
};

const loadSearches = () => listInvestorSearches();

/** Past investor searches, newest first, each opening its shortlist. */
export function SearchesList() {
  const { data, error, loading, reload } = useLoad("investor-searches", loadSearches);

  if (loading) {
    return (
      <div role="status" aria-label="Loading investor searches" className="flex flex-col gap-2">
        {[0, 1, 2].map((row) => (
          <Skeleton key={row} className="h-10 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-line bg-surface p-5">
        <p className="text-sm text-ink-secondary">
          <span className="font-medium text-ink">The searches could not be loaded.</span>{" "}
          {error ? "Nothing was changed." : null}
        </p>
        <Button onClick={reload}>Try again</Button>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-line bg-surface p-5">
        <div className="flex max-w-2xl flex-col gap-1">
          <h2 className="text-xl font-medium text-ink">No investor searches yet</h2>
          <p className="text-sm text-ink-secondary">
            Describe a business and the funding it wants. DealProof lists the investors that
            dated funding records connect to comparable companies, with the rounds behind
            each one.
          </p>
        </div>
        <Button asChild variant="primary">
          <Link href="/app/investors/new">Find investors</Link>
        </Button>
      </div>
    );
  }

  const searches = [...data].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <div className="flex flex-col gap-2">
      <p className="text-dense text-ink-secondary">{plural(searches.length, "search", "searches")}</p>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Business</TableHead>
            <TableHead>Location</TableHead>
            <TableHead>Stage</TableHead>
            <TableHead>Status</TableHead>
            <TableHead numeric>Investors</TableHead>
            <TableHead numeric>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {searches.map((search) => (
            <TableRow key={search.id}>
              <TableCell>
                <Link
                  href={`/app/investors/${encodeURIComponent(search.id)}`}
                  className="rounded-xs font-medium text-ink underline decoration-line-strong underline-offset-4 transition-colors hover:text-accent"
                >
                  {search.sector}
                </Link>
              </TableCell>
              <TableCell>{search.location}</TableCell>
              <TableCell>{stageLabel(search.stage)}</TableCell>
              <TableCell className="text-ink-secondary">{STATUS_LABEL[search.status]}</TableCell>
              <TableCell numeric>{search.status === "ready" ? search.entries_count : "–"}</TableCell>
              <TableCell numeric className="text-ink-secondary">
                {formatDate(search.created_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
