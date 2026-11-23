"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { caseHref, describeError, useShell } from "@/components/app-shell";
import { IdentityCue } from "@/components/dashboard/case-cells";
import { DispositionStamp } from "@/components/dealproof";
import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  PanelFooter,
  RowLink,
  Segmented,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextLink,
  Toolbar,
  Tooltip,
} from "@/components/ui";
import { FilterSelect } from "@/components/workspace/filter-select";
import { FitBar } from "@/components/workspace/fit-bar";
import { createCase } from "@/lib/api/client";
import { companyRows, SCREENING_DETAIL_LIMIT, useScreenings, type CompanyRow } from "@/lib/directory";
import { formatDate } from "@/lib/format";
import { DISPOSITION_LABEL } from "@/lib/labels";
import { useUrlState } from "@/lib/url-state";
import { useWorkspace } from "@/lib/workspace";

const COMPARE_MAX = 4;

type CaseFilter = "all" | "with" | "without";
const SORTS = ["updated", "name", "fit", "headcount"] as const;
type Sort = (typeof SORTS)[number];
const SORT_LABEL: Record<Sort, string> = {
  updated: "Recently updated",
  name: "Name, A to Z",
  fit: "Fit, highest first",
  headcount: "Headcount, largest first",
};

const DISPOSITIONS = ["prioritise", "investigate_further", "deprioritise", "cannot_assess"] as const;

/** Largest first, with rows that hold no value always after the ones that do. */
function byNumber(a: number | null, b: number | null): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  return b - a;
}

function sortRows(rows: CompanyRow[], sort: Sort): CompanyRow[] {
  const byName = (a: CompanyRow, b: CompanyRow) => a.name.localeCompare(b.name);
  return [...rows].sort((a, b) => {
    if (sort === "name") return byName(a, b);
    if (sort === "fit") return byNumber(a.fit, b.fit) || byName(a, b);
    if (sort === "headcount") return byNumber(a.headcount, b.headcount) || byName(a, b);
    return (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "") || byName(a, b);
  });
}

const Dash = ({ why }: { why: string }) => (
  <span className="text-ink-muted">
    <span aria-hidden>–</span>
    <span className="sr-only">{why}</span>
  </span>
);

/** Fit and the share it rests on, never apart: the words, then a bar whose hatched end is the unassessed share. */
function FitCell({ row }: { row: CompanyRow }) {
  if (row.fit === null || row.assessablePct === null) {
    return (
      <span className="block max-w-56 truncate text-xs text-ink-muted" title={row.fitNote ?? undefined}>
        {row.fitNote ?? "Not assessed yet"}
      </span>
    );
  }
  return <FitBar fit={row.fit} pct={row.assessablePct} />;
}

function CaseCell({ row }: { row: CompanyRow }) {
  if (!row.item) return <span className="text-ink-muted">No case</span>;
  return (
    <div className="flex flex-col items-start gap-0.5">
      {row.item.disposition ? (
        <DispositionStamp disposition={row.item.disposition} size="sm" />
      ) : (
        <span className="text-ink-secondary">{row.item.status === "verifying" ? "Verifying" : "No disposition yet"}</span>
      )}
      <span className="text-xs">
        <IdentityCue item={row.item} record={row.record} />
      </span>
    </div>
  );
}

/** Open the case, or start one from the shortlist entry. A removed company cannot be verified from here. */
function RowAction({ row }: { row: CompanyRow }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (row.item) {
    return (
      <Button asChild size="sm" className="relative z-10">
        <Link href={caseHref(row.item.id)} aria-label={`Open the case for ${row.name}`}>
          Open
        </Link>
      </Button>
    );
  }
  const entry = row.shortlist;
  if (!entry || !row.screening) return null;
  const screeningId = row.screening.id;

  async function verify() {
    if (!entry) return;
    setPending(true);
    setError(null);
    try {
      const created = await createCase({ shortlist_item_id: entry.id, thesis_id: screeningId });
      router.push(caseHref(created.id));
    } catch (caught) {
      setError(describeError(caught, "The case could not be opened"));
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" variant="primary" onClick={verify} disabled={pending} aria-label={`Verify ${row.name}`}>
        {pending ? "Opening" : "Verify"}
      </Button>
      {error ? (
        <p role="alert" className="max-w-48 text-right text-xs whitespace-normal text-contradicted">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function CompaniesTable({
  rows,
  selected,
  toggle,
}: {
  rows: CompanyRow[];
  selected: string[];
  toggle: (caseId: string) => void;
}) {
  const full = selected.length >= COMPARE_MAX;
  return (
    <Table density="two-line" flush>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10">
            <span className="sr-only">Select to compare</span>
          </TableHead>
          <TableHead>Company</TableHead>
          <TableHead>HQ</TableHead>
          <TableHead numeric>
            <Tooltip content="Headcount estimate from professional profiles, not a payroll count">
              <button type="button" className="underline-estimate rounded-xs">
                Headcount
              </button>
            </Tooltip>
          </TableHead>
          <TableHead>Fit · assessable</TableHead>
          <TableHead>Found by screening</TableHead>
          <TableHead>Case</TableHead>
          <TableHead numeric>Updated</TableHead>
          <TableHead>
            <span className="sr-only">Action</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const caseId = row.item?.id ?? null;
          const checked = caseId !== null && selected.includes(caseId);
          return (
            <TableRow
              key={row.key}
              className="relative"
              data-state={checked ? "selected" : undefined}
              aria-selected={checked || undefined}
            >
              <TableCell>
                <input
                  type="checkbox"
                  className="relative z-10 block size-4 accent-ink disabled:opacity-40"
                  checked={checked}
                  disabled={caseId === null || (full && !checked)}
                  onChange={() => caseId && toggle(caseId)}
                  aria-label={`Select ${row.name} to compare`}
                  title={
                    caseId === null
                      ? "Open a case for this company before comparing it"
                      : full && !checked
                        ? "Maximum 4 cases per comparison"
                        : undefined
                  }
                />
              </TableCell>
              <TableCell>
                {caseId ? (
                  <RowLink stretch href={caseHref(caseId)}>
                    {row.name}
                  </RowLink>
                ) : (
                  <span className="font-medium text-ink">{row.name}</span>
                )}
                <span className="block max-w-64 truncate font-mono text-2xs text-ink-muted">
                  {row.domain ?? "No domain on record"}
                </span>
              </TableCell>
              <TableCell muted={!row.hq} className="max-w-48 truncate" title={row.hq ?? undefined}>
                {row.hq ?? <Dash why="No headquarters on record" />}
              </TableCell>
              <TableCell numeric title={row.headcountBasis ? `Estimate · ${row.headcountBasis}` : undefined}>
                {row.headcount === null ? (
                  <Dash why="No headcount estimate on record" />
                ) : (
                  <span className="underline-estimate">~{row.headcount.toLocaleString("en-US")}</span>
                )}
              </TableCell>
              <TableCell className="min-w-44">
                <FitCell row={row} />
              </TableCell>
              <TableCell className="max-w-64">
                {row.screening ? (
                  <TextLink
                    href={`/app/discover/${encodeURIComponent(row.screening.id)}`}
                    className="relative z-10 block truncate text-ink-secondary no-underline hover:underline"
                  >
                    {row.screening.text}
                  </TextLink>
                ) : (
                  <span className="text-ink-muted">Verified directly</span>
                )}
              </TableCell>
              <TableCell>
                <CaseCell row={row} />
              </TableCell>
              <TableCell numeric muted={!row.updatedAt}>
                {formatDate(row.updatedAt) ?? "–"}
              </TableCell>
              <TableCell className="text-right">
                <RowAction row={row} />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/**
 * `/app/companies`. Every company on file: each case, and each company a screening found
 * that has no case yet. Filters and the sort live in the URL, so a view can be shared.
 */
export function Companies() {
  const { openVerify } = useShell();
  const [workspaceState, retryWorkspace] = useWorkspace();
  const [screeningState, retryScreenings] = useScreenings();
  const [params, setParams, resetParams] = useUrlState();
  const [selected, setSelected] = useState<string[]>([]);
  // Typed text is held here and mirrored to the URL, so a keystroke never waits on navigation.
  const [query, setQuery] = useState(() => params.get("q") ?? "");

  const verify = <Button onClick={openVerify}>Verify a company</Button>;

  if (workspaceState.status === "loading" || screeningState.status === "loading") {
    return (
      <Page>
        <PageHeader title="Companies" actions={verify} />
        <Panel>
          <LoadingState label="Loading companies" shape="rows" density="two-line" count={6} />
        </Panel>
      </Page>
    );
  }
  if (workspaceState.status === "error") {
    return (
      <Page>
        <PageHeader title="Companies" actions={verify} />
        <ErrorState
          size="page"
          what="Companies"
          reason={workspaceState.message}
          status={workspaceState.code}
          onRetry={retryWorkspace}
        />
      </Page>
    );
  }

  const workspace = workspaceState.data;
  const screenings = screeningState.status === "ready" ? screeningState.data : null;
  const all = companyRows(workspace, screenings);

  const caseFilter: CaseFilter = params.get("case") === "with" ? "with" : params.get("case") === "without" ? "without" : "all";
  const screening = params.get("screening");
  const disposition = params.get("disposition");
  const sort: Sort = SORTS.find((option) => option === params.get("sort")) ?? "updated";
  const filtered = Boolean(query || screening || disposition || caseFilter !== "all");

  const needle = query.trim().toLowerCase();
  const shown = sortRows(
    all.filter((row) => {
      if (needle && !`${row.name} ${row.domain ?? ""} ${row.hq ?? ""}`.toLowerCase().includes(needle)) return false;
      if (caseFilter === "with" && !row.item) return false;
      if (caseFilter === "without" && row.item) return false;
      if (screening === "none" ? row.screening !== null : screening && row.screening?.id !== screening) return false;
      if (disposition === "none" ? !row.item || row.item.disposition !== null : disposition && row.item?.disposition !== disposition) {
        return false;
      }
      return true;
    }),
    sort,
  );

  const withCase = all.filter((row) => row.item).length;
  const confirmed = all.filter((row) => row.item?.identity_state === "confirmed").length;
  const screeningOptions = [...new Map(all.flatMap((row) => (row.screening ? [[row.screening.id, row.screening.text]] : []))).entries()];
  const toggle = (caseId: string) =>
    setSelected((current) =>
      current.includes(caseId) ? current.filter((id) => id !== caseId) : current.length < COMPARE_MAX ? [...current, caseId] : current,
    );

  return (
    <Page>
      <PageHeader
        title="Companies"
        meta={
          <>
            <span className="font-mono">{all.length}</span> {all.length === 1 ? "company" : "companies"} ·{" "}
            <span className="font-mono">{withCase}</span> with a case ·{" "}
            <span className="font-mono">{all.length - withCase}</span> found by a screening only
          </>
        }
        figures={
          all.length > 0
            ? [
                { label: "Companies", value: all.length },
                { label: "With a case", value: withCase },
                { label: "Identity confirmed", value: confirmed },
              ]
            : undefined
        }
        actions={verify}
      />

      {screeningState.status === "error" ? (
        <ErrorState size="inline" what="Screening shortlists" status={screeningState.code} onRetry={retryScreenings} />
      ) : null}

      {all.length === 0 ? (
        <EmptyState
          size="page"
          title="No companies on file yet"
          actions={
            <>
              <Button asChild variant="primary" size="sm">
                <Link href="/app/discover/new">New screening</Link>
              </Button>
              <Button size="sm" onClick={openVerify}>
                Verify a company
              </Button>
            </>
          }
        >
          Companies appear here when a screening returns a shortlist or when you start verification
          for a company directly.
        </EmptyState>
      ) : (
        <>
          <Toolbar count={`${shown.length} of ${all.length}`}>
            <Input
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setParams({ q: event.target.value.trim() });
              }}
              placeholder="Search by company"
              aria-label="Search by company, domain or headquarters"
              className="h-8 w-56 text-dense"
            />
            <Segmented
              label="Filter by case"
              value={caseFilter}
              onChange={(next) => setParams({ case: next === "all" ? null : next })}
              options={[
                { value: "all", label: "All", count: all.length },
                { value: "with", label: "With a case", count: withCase },
                { value: "without", label: "No case", count: all.length - withCase },
              ]}
            />
            <FilterSelect
              label="Filter by screening"
              all="All screenings"
              value={screening}
              onChange={(next) => setParams({ screening: next })}
              options={[
                ...screeningOptions.map(([id, text]) => ({ value: id, label: text.length > 48 ? `${text.slice(0, 47)}…` : text })),
                { value: "none", label: "Verified directly" },
              ]}
            />
            <FilterSelect
              label="Filter by disposition"
              all="Any disposition"
              value={disposition}
              onChange={(next) => setParams({ disposition: next })}
              options={[
                ...DISPOSITIONS.map((value) => ({ value, label: DISPOSITION_LABEL[value] })),
                { value: "none", label: "No disposition yet" },
              ]}
            />
            <FilterSelect
              label="Sort companies"
              all={SORT_LABEL.updated}
              value={sort === "updated" ? null : sort}
              onChange={(next) => setParams({ sort: next })}
              options={SORTS.filter((option) => option !== "updated").map((value) => ({ value, label: SORT_LABEL[value] }))}
            />
            {selected.length > 0 ? (
              <>
                {selected.length >= 2 ? (
                  <Button asChild size="sm" variant="primary">
                    <Link href={`/app/compare?cases=${selected.map(encodeURIComponent).join(",")}`}>
                      Compare ({selected.length})
                    </Link>
                  </Button>
                ) : (
                  <span className="text-xs text-ink-secondary">Select 1 to 3 more cases to compare</span>
                )}
                <Button size="sm" variant="quiet" onClick={() => setSelected([])}>
                  Clear selection
                </Button>
              </>
            ) : null}
          </Toolbar>

          <Panel>
            <PanelBody flush>
              {shown.length === 0 ? (
                <EmptyState
                  title="No companies match these filters"
                  actions={
                    filtered ? (
                      <Button
                        size="sm"
                        onClick={() => {
                          setQuery("");
                          resetParams();
                        }}
                      >
                        Reset filters
                      </Button>
                    ) : undefined
                  }
                >
                  Try clearing one or more filters or changing your search term.
                </EmptyState>
              ) : (
                <CompaniesTable rows={shown} selected={selected} toggle={toggle} />
              )}
            </PanelBody>
            {screenings && screenings.unread > 0 ? (
              <PanelFooter>
                Shortlists are read from the {SCREENING_DETAIL_LIMIT} most recent screenings; {screenings.unread} more{" "}
                {screenings.unread === 1 ? "was" : "were"} not read
              </PanelFooter>
            ) : null}
          </Panel>
        </>
      )}
    </Page>
  );
}
