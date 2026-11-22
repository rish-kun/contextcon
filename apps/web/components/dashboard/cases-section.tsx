"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { caseHref, useShell } from "@/components/app-shell";
import {
  Button,
  Icon,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";
import type { CaseDetail, CaseSummary } from "@/lib/api/client";
import { formatDateTime, formatShortDateTime } from "@/lib/format";
import { DISPOSITION_LABEL } from "@/lib/labels";
import { DISPOSITIONS } from "@/lib/types";
import {
  ClaimsCell,
  CostCell,
  DispositionCell,
  FitCell,
  IdentityCue,
  waitingCue,
} from "./case-cells";
import { useCaseDetails, type Load } from "./use-load";

const ALL = "all";
const NONE = "none";

export function CasesSection({ cases, onRetry }: { cases: Load<CaseSummary[]>; onRetry: () => void }) {
  if (cases.status === "loading") return <CasesSkeleton />;
  if (cases.status === "error") {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line bg-surface p-5">
        <h2 className="text-sm font-medium text-ink">Cases could not be loaded</h2>
        <p className="text-dense text-ink-secondary">{cases.message}</p>
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }
  if (cases.data.length === 0) return <NoCases />;
  return <CasesList cases={cases.data} />;
}

function CasesSkeleton() {
  return (
    <div role="status" aria-label="Loading cases" className="rounded-lg border border-line bg-surface">
      <div className="h-8 rounded-t-lg bg-surface-sunken" />
      {Array.from({ length: 4 }, (_, row) => (
        <div key={row} className="flex h-14 items-center gap-6 border-t border-line px-3">
          <div className="flex w-56 flex-col gap-2">
            <Skeleton className="w-40" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="hidden h-6 w-36 sm:block" />
          <Skeleton className="hidden w-48 lg:block" />
          <Skeleton className="ml-auto w-20" />
        </div>
      ))}
    </div>
  );
}

const ENTRY_ROW =
  "group flex w-full items-center justify-between gap-4 border-t border-line px-5 py-4 text-left transition-colors hover:bg-surface-raised";

/** No cases yet: what a case is, and the three ways in. */
function NoCases() {
  const { openVerify } = useShell();
  const entry = (title: string, line: string) => (
    <>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-medium text-ink">{title}</span>
        <span className="text-dense text-ink-secondary">{line}</span>
      </span>
      <Icon icon={ArrowRight} className="shrink-0 text-ink-muted transition-colors group-hover:text-ink" />
    </>
  );
  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className="flex max-w-2xl flex-col gap-2 p-5">
        <h2 className="text-xl font-medium text-ink">No cases yet</h2>
        <p className="text-sm text-ink-secondary">
          A case holds a company&rsquo;s confirmed identity, checked claims, sources, and screening
          memo. Start with an investment thesis or open a case for a company you already have in
          mind.
        </p>
      </div>
      <Link href="/app/discover" className={ENTRY_ROW}>
        {entry("Start with a thesis", "Describe what you are looking for and review the criteria before anything is searched")}
      </Link>
      <button type="button" onClick={openVerify} className={ENTRY_ROW}>
        {entry("Verify a company you already have in mind", "Give its name and website; identity is confirmed before any claim is checked")}
      </button>
      <Link href="/app/investors" className={`${ENTRY_ROW} rounded-b-lg`}>
        {entry("Find investors", "Rank investors by their past rounds in comparable companies")}
      </Link>
    </div>
  );
}

function CasesList({ cases }: { cases: CaseSummary[] }) {
  const details = useCaseDetails(cases);
  const [query, setQuery] = useState("");
  const [disposition, setDisposition] = useState(ALL);

  const needle = query.trim().toLowerCase();
  const visible = cases.filter((item) => {
    if (needle && !item.name.toLowerCase().includes(needle)) return false;
    if (disposition === ALL) return true;
    if (disposition === NONE) return item.disposition === null;
    return item.disposition === disposition;
  });
  const filtered = needle !== "" || disposition !== ALL;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="search"
          aria-label="Search by company"
          placeholder="Search by company"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-8 w-full bg-surface sm:w-64"
        />
        <Select value={disposition} onValueChange={setDisposition}>
          <SelectTrigger aria-label="Disposition" className="h-8 w-full bg-surface sm:w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All dispositions</SelectItem>
            {DISPOSITIONS.map((value) => (
              <SelectItem key={value} value={value}>
                {DISPOSITION_LABEL[value]}
              </SelectItem>
            ))}
            <SelectItem value={NONE}>No disposition yet</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {visible.length === 0 ? (
        <div className="flex flex-col items-start gap-2 rounded-lg border border-line bg-surface p-5">
          <h2 className="text-sm font-medium text-ink">No cases match these filters</h2>
          <p className="text-dense text-ink-secondary">
            Try clearing one or more filters or changing your search term.
          </p>
          <Button
            size="sm"
            className="mt-1"
            onClick={() => {
              setQuery("");
              setDisposition(ALL);
            }}
          >
            Reset filters
          </Button>
        </div>
      ) : (
        <>
          <CasesTable cases={visible} details={details} />
          <CasesStack cases={visible} details={details} />
        </>
      )}
      {filtered && visible.length > 0 ? (
        <p className="font-mono text-xs text-ink-muted">
          Showing {visible.length} of {cases.length}
        </p>
      ) : null}
    </div>
  );
}

interface RowsProps {
  cases: CaseSummary[];
  details: Record<string, CaseDetail>;
}

function Updated({ item }: { item: CaseSummary }) {
  return (
    <time
      dateTime={item.updated_at}
      title={formatDateTime(item.updated_at) ?? undefined}
      className="font-mono text-xs whitespace-nowrap text-ink-secondary"
    >
      {formatShortDateTime(item.updated_at) ?? "unknown"}
    </time>
  );
}

function SecondLine({ item, detail }: { item: CaseSummary; detail?: CaseDetail }) {
  const waiting = waitingCue(item, detail);
  return (
    <span className="flex flex-wrap items-center gap-x-2 text-xs">
      <IdentityCue item={item} detail={detail} />
      {waiting ? (
        <>
          <span aria-hidden className="text-ink-muted">
            ·
          </span>
          <span className="text-ink">{waiting}</span>
        </>
      ) : null}
    </span>
  );
}

/** md and up: a table, because cases are compared row by row. Two-line rows, 56px. */
function CasesTable({ cases, details }: RowsProps) {
  return (
    <div className="hidden md:block">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Company</TableHead>
            <TableHead>Disposition</TableHead>
            <TableHead>Fit · assessable</TableHead>
            <TableHead>Claims</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead numeric>Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {cases.map((item) => {
            const detail = details[item.id];
            return (
              <TableRow key={item.id}>
                <TableCell className="h-14 min-w-56">
                  <div className="flex flex-col gap-0.5">
                    <Link
                      href={caseHref(item.id)}
                      className="self-start rounded-xs text-sm font-medium text-ink underline-offset-4 hover:text-accent hover:underline"
                    >
                      {item.name}
                    </Link>
                    <SecondLine item={item} detail={detail} />
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <DispositionCell item={item} />
                </TableCell>
                <TableCell className="min-w-72">
                  <FitCell item={item} detail={detail} />
                </TableCell>
                <TableCell className="min-w-32">
                  <ClaimsCell item={item} detail={detail} />
                </TableCell>
                <TableCell>
                  <Updated item={item} />
                </TableCell>
                <TableCell numeric>
                  <CostCell item={item} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

/** Below md: the same facts, stacked in reading order. */
function CasesStack({ cases, details }: RowsProps) {
  return (
    <ul className="flex flex-col rounded-lg border border-line bg-surface md:hidden">
      {cases.map((item) => {
        const detail = details[item.id];
        return (
          <li key={item.id} className="flex flex-col gap-3 border-b border-line p-4 last:border-b-0">
            <div className="flex flex-col gap-1">
              <Link href={caseHref(item.id)} className="self-start rounded-xs text-sm font-medium text-ink">
                {item.name}
              </Link>
              <SecondLine item={item} detail={detail} />
            </div>
            {item.disposition ? (
              <div>
                <DispositionCell item={item} />
              </div>
            ) : null}
            <div className="text-dense">
              <FitCell item={item} detail={detail} />
            </div>
            <div className="text-dense">
              <ClaimsCell item={item} detail={detail} />
            </div>
            <div className="flex items-center justify-between gap-3">
              <Updated item={item} />
              <CostCell item={item} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
