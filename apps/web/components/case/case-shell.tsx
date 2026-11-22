"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CaseDetail } from "@/lib/api/client";
import { transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { JudgmentPanel } from "@/components/dealproof";
import { Button, Skeleton } from "@/components/ui";
import { toAssessment } from "./adapt";
import { useCase } from "./case-context";
import { CaseHeader } from "./case-header";

interface TabDef {
  /** Path segment under the case; empty for Overview. */
  segment: string;
  label: string;
  count?: number;
  /** A request is drafted and no one has approved it. */
  waiting?: boolean;
}

function tabsFor(detail: CaseDetail): TabDef[] {
  const status = detail.message?.status;
  const waiting =
    (detail.request_list?.items.length ?? 0) > 0 && (status === undefined || status === "draft");
  return [
    { segment: "", label: "Overview" },
    { segment: "identity", label: "Identity" },
    { segment: "claims", label: "Claims", count: detail.claims.length },
    { segment: "events", label: "Events", count: detail.events.length },
    { segment: "comparables", label: "Comparables" },
    { segment: "assessment", label: "Assessment" },
    { segment: "request", label: "Request & approval", waiting },
    { segment: "sources", label: "Sources", count: detail.sources.length },
    { segment: "documents", label: "Documents", count: detail.documents.length },
    { segment: "cost", label: "Cost" },
  ];
}

function activeSegment(pathname: string, basePath: string): string {
  const rest = pathname.startsWith(basePath) ? pathname.slice(basePath.length) : "";
  return rest.split("/").filter(Boolean)[0] ?? "";
}

/** Route tabs: links, so each tab has its own URL and the browser's back button works. */
function CaseTabs({ detail, active }: { detail: CaseDetail; active: string }) {
  const { basePath } = useCase();
  return (
    <nav
      aria-label="Case sections"
      className="-mx-4 overflow-x-auto border-b border-line-strong px-4 md:mx-0 md:px-0 print:hidden"
    >
      <ul className="flex items-end gap-6">
        {tabsFor(detail).map((tab) => {
          const current = tab.segment === active;
          return (
            <li key={tab.segment} className="shrink-0">
              <Link
                href={tab.segment ? `${basePath}/${tab.segment}` : basePath}
                aria-current={current ? "page" : undefined}
                aria-label={tab.waiting ? `${tab.label}, awaiting approval` : undefined}
                className={cn(
                  "relative inline-flex h-11 items-center gap-2 rounded-xs text-sm transition-colors md:h-9",
                  current ? "font-medium text-ink" : "text-ink-muted hover:text-ink",
                )}
              >
                {tab.label}
                {tab.count !== undefined ? (
                  <span className="font-mono text-xs font-normal text-ink-muted">{tab.count}</span>
                ) : null}
                {tab.waiting ? (
                  <span aria-hidden className="size-1.5 rounded-full bg-accent" />
                ) : null}
                {current ? (
                  <motion.span
                    layoutId="case-tab-indicator"
                    transition={transition.base}
                    className="absolute inset-x-0 bottom-0 h-0.5 bg-ink"
                    aria-hidden
                  />
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function nextStep(detail: CaseDetail): string {
  if (detail.identity.state !== "confirmed") return "Next: resolve identity";
  const status = detail.message?.status;
  if ((detail.request_list?.items.length ?? 0) > 0 && (status === undefined || status === "draft")) {
    return "Next: approve request";
  }
  if (detail.claims.some((claim) => claim.status !== "supported")) {
    return "Next: review open claims";
  }
  return "Next: print memo";
}

function AssessmentRail({ detail }: { detail: CaseDetail }) {
  if (!detail.assessment) return null;
  return (
    <aside className="hidden w-(--layout-rail) shrink-0 xl:block print:hidden">
      <div className="sticky top-20 flex flex-col gap-3">
        <JudgmentPanel
          assessment={toAssessment(detail.assessment, detail.claims)}
          variant="rail"
        />
        <p className="px-5 text-dense font-medium text-ink">{nextStep(detail)}</p>
      </div>
    </aside>
  );
}

function CaseLoading() {
  return (
    <div role="status" aria-label="Loading the case" className="flex flex-col gap-4">
      <Skeleton className="h-8 w-80 max-w-full" />
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-28 w-full rounded-lg" />
      <Skeleton className="h-9 w-full" />
    </div>
  );
}

function CaseProblem({ notFound }: { notFound: boolean }) {
  const { error, reload } = useCase();
  return (
    <div className="flex max-w-(--layout-prose-max) flex-col items-start gap-3 py-12">
      <h1 className="text-2xl font-medium text-ink">
        {notFound ? "No case at this address" : "This case did not load"}
      </h1>
      <p className="text-ink-secondary">
        {notFound
          ? "The case may have been deleted, or the link belongs to another workspace."
          : error}
      </p>
      <div className="flex gap-2">
        {notFound ? null : (
          <Button variant="primary" onClick={() => void reload()}>
            Try again
          </Button>
        )}
        <Button asChild>
          <Link href="/app">All cases</Link>
        </Button>
      </div>
    </div>
  );
}

/**
 * The frame every case tab sits in: header, tab row, the tab, and from `xl` the sticky
 * assessment rail. Children render only once the case has loaded.
 */
export function CaseShell({ children }: { children: React.ReactNode }) {
  const { detail, state, basePath } = useCase();
  const pathname = usePathname();
  const active = activeSegment(pathname, basePath);

  return (
    <div
      data-case-shell=""
      className="flex w-full flex-col gap-6"
    >
      {state === "loading" ? <CaseLoading /> : null}
      {state === "error" || state === "not_found" ? (
        <CaseProblem notFound={state === "not_found"} />
      ) : null}
      {detail ? (
        <>
          <div data-case-chrome="" className="flex flex-col gap-6">
            <CaseHeader detail={detail} />
            <CaseTabs detail={detail} active={active} />
          </div>
          <div className="flex items-start gap-8">
            <div
              key={active}
              className="min-w-0 flex-1 animate-fade-in motion-reduce:animate-none"
            >
              {children}
            </div>
            {active === "assessment" ? null : <AssessmentRail detail={detail} />}
          </div>
        </>
      ) : null}
    </div>
  );
}
