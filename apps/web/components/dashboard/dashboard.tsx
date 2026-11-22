"use client";

import Link from "next/link";
import { VerifyCompanyForm, useShell } from "@/components/app-shell";
import { Button } from "@/components/ui";
import { listCases, listInvestorSearches, listTheses } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { CasesSection } from "./cases-section";
import { DiscoveryRuns, InvestorSearches } from "./recent-lists";
import { useLoad } from "./use-load";

// Stable references for useLoad.
const loadCases = () => listCases();
const loadTheses = () => listTheses();
const loadInvestorSearches = () => listInvestorSearches();

/**
 * `/app`. The cases table is the page; beside it, the quick way to open a case and the
 * recent discovery and investor runs. One summary line in words, no stat cards.
 */
export function Dashboard() {
  const { openVerify } = useShell();
  const [cases, retryCases] = useLoad(loadCases, "The list of cases was not returned");
  const [theses, retryTheses] = useLoad(loadTheses, "The list was not returned");
  const [searches, retrySearches] = useLoad(loadInvestorSearches, "The list was not returned");

  let summary: string | null = null;
  if (cases.status === "ready" && cases.data.length > 0) {
    const active = cases.data.filter(
      (item) => item.status === "verifying" || item.status === "awaiting_identity",
    ).length;
    summary =
      active > 0
        ? `${plural(cases.data.length, "case")} · ${active} running or waiting on you`
        : plural(cases.data.length, "case");
  }

  return (
    <div className="flex animate-row-in flex-col gap-6 motion-reduce:animate-none lg:gap-8">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-medium text-ink">Cases</h1>
          <p className="min-h-5 font-mono text-xs text-ink-secondary">{summary}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={openVerify}>New case</Button>
          <Button asChild variant="primary">
            <Link href="/app/discover">New thesis</Link>
          </Button>
        </div>
      </header>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-label="Cases" className="min-w-0">
          <CasesSection cases={cases} onRetry={retryCases} />
        </section>

        <div className="grid content-start gap-8 md:grid-cols-2 xl:grid-cols-1">
          <section aria-labelledby="verify-heading" className="rounded-lg border border-line bg-surface p-5 md:col-span-2 xl:col-span-1">
            <h2 id="verify-heading" className="text-sm font-medium text-ink">
              Verify a company
            </h2>
            <p className="mt-1 mb-4 text-dense text-ink-secondary">
              Start verification for a company you already have in mind
            </p>
            <VerifyCompanyForm />
          </section>
          <DiscoveryRuns state={theses} onRetry={retryTheses} />
          <InvestorSearches state={searches} onRetry={retrySearches} />
        </div>
      </div>
    </div>
  );
}
