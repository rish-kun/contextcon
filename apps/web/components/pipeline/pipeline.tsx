"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { caseHref } from "@/components/app-shell";
import { ClaimsCell, DispositionCell, FitCell, FitCompact } from "@/components/dashboard/case-cells";
import { DispositionStamp, StatusCounts } from "@/components/dealproof";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  RowLink,
  Segmented,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Toolbar,
} from "@/components/ui";
import type { CaseDetail, CaseSummary } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  attention,
  claimCounts,
  coverageNote,
  PIPELINE_COLUMNS,
  PIPELINE_LABEL,
  type PipelineColumn,
  pipelineColumn,
  REQUEST_STATE_LABEL,
  requestState,
  useWorkspace,
  type Workspace,
} from "@/lib/workspace";

type View = "board" | "table";
const VIEW_KEY = "dealproof.pipeline.view";
const listeners = new Set<() => void>();

/** Board or table, remembered in this browser. A private window simply starts on the board. */
function useView(): [View, (view: View) => void] {
  const view = useSyncExternalStore<View>(
    (notify) => {
      listeners.add(notify);
      return () => listeners.delete(notify);
    },
    () => {
      try {
        return window.localStorage.getItem(VIEW_KEY) === "table" ? "table" : "board";
      } catch {
        return "board";
      }
    },
    () => "board",
  );
  return [
    view,
    (next) => {
      try {
        window.localStorage.setItem(VIEW_KEY, next);
      } catch {
        /* the choice lasts for this page only */
      }
      listeners.forEach((notify) => notify());
    },
  ];
}

/** What the column rule says, shown under its title so nobody has to guess why a card is there. */
const COLUMN_RULE: Record<PipelineColumn, string> = {
  identity: "Legal entity not confirmed",
  verifying: "Checks running now",
  failed: "Last run did not finish",
  assessed: "Assessed, no request drafted",
  drafted: "Request waiting on a person",
  sent: "Request left, or was suppressed",
};

function CaseCard({ item, detail }: { item: CaseSummary; detail: CaseDetail | undefined }) {
  const counts = claimCounts(detail);
  const request = requestState(detail);
  const waiting = attention(item, detail)[0];
  return (
    <li className="relative flex flex-col gap-2 rounded-md border border-line bg-surface p-3 transition-colors hover:border-line-strong">
      <RowLink stretch href={caseHref(item.id)} className="truncate text-sm">
        {item.name}
      </RowLink>
      {item.disposition ? (
        <DispositionStamp disposition={item.disposition} size="sm" className="self-start" />
      ) : (
        <span className="text-xs text-ink-muted">No disposition yet</span>
      )}
      <FitCompact item={item} />
      {counts && detail && detail.claims.length > 0 ? (
        <StatusCounts counts={counts} />
      ) : (
        <span className="text-xs text-ink-muted">
          {item.claim_count > 0 ? plural(item.claim_count, "claim") : "No claims yet"}
        </span>
      )}
      {request !== "none" ? (
        <span
          className={cn(
            "self-start rounded-xs px-1 text-xs",
            request === "suppressed"
              ? "border border-dashed border-not-checked-line bg-not-checked-tint text-not-checked"
              : "bg-surface-sunken text-ink-secondary",
          )}
        >
          {REQUEST_STATE_LABEL[request]}
        </span>
      ) : waiting ? (
        <span className="text-xs text-ink-secondary">{waiting.what}</span>
      ) : null}
      <time dateTime={item.updated_at} className="font-mono text-2xs text-ink-muted">
        Updated {formatDate(item.updated_at)}
      </time>
    </li>
  );
}

function Board({ workspace, grouped }: { workspace: Workspace; grouped: Record<PipelineColumn, CaseSummary[]> }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 md:-mx-6 md:px-6 lg:-mx-8 lg:px-8">
      <ol className="grid min-w-max grid-flow-col auto-cols-[15rem] gap-3 xl:min-w-0 xl:auto-cols-fr">
        {PIPELINE_COLUMNS.map((column) => (
          <li key={column} className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-col border-b border-line-strong pb-2">
              <h2 className="flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
                {PIPELINE_LABEL[column]}
                <span className="font-mono text-xs font-normal text-ink-muted">{grouped[column].length}</span>
              </h2>
              <p className="text-xs text-ink-muted">{COLUMN_RULE[column]}</p>
            </div>
            {grouped[column].length === 0 ? (
              <p className="text-xs text-ink-muted">None</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {grouped[column].map((item) => (
                  <CaseCard key={item.id} item={item} detail={workspace.details[item.id]} />
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PipelineTable({ workspace, grouped }: { workspace: Workspace; grouped: Record<PipelineColumn, CaseSummary[]> }) {
  return (
    <Panel>
      <PanelBody flush>
        <Table density="two-line" flush>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Disposition</TableHead>
              <TableHead>Fit · assessable</TableHead>
              <TableHead>Claims</TableHead>
              <TableHead>Request</TableHead>
              <TableHead numeric>Updated</TableHead>
            </TableRow>
          </TableHeader>
          {PIPELINE_COLUMNS.filter((column) => grouped[column].length > 0).map((column) => (
            <TableBody key={column}>
              <tr className="border-b border-line bg-surface-sunken">
                <th colSpan={6} scope="colgroup" className="h-8 px-4 text-left text-xs font-medium text-ink-secondary">
                  {PIPELINE_LABEL[column]}{" "}
                  <span className="pl-1 font-mono font-normal text-ink-muted">{grouped[column].length}</span>
                  <span className="pl-3 font-normal text-ink-muted">{COLUMN_RULE[column]}</span>
                </th>
              </tr>
              {grouped[column].map((item) => {
                const detail = workspace.details[item.id];
                return (
                  <TableRow key={item.id} className="relative">
                    <TableCell>
                      <RowLink stretch href={caseHref(item.id)}>
                        {item.name}
                      </RowLink>
                      <span className="block text-xs text-ink-muted">
                        {attention(item, detail)[0]?.what ?? "Nothing waiting"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <DispositionCell item={item} />
                    </TableCell>
                    <TableCell className="min-w-56">
                      <FitCell item={item} detail={detail} />
                    </TableCell>
                    <TableCell>
                      <ClaimsCell item={item} detail={detail} />
                    </TableCell>
                    <TableCell muted={requestState(detail) === "none"}>
                      {REQUEST_STATE_LABEL[requestState(detail)]}
                    </TableCell>
                    <TableCell numeric>{formatDate(item.updated_at)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          ))}
        </Table>
      </PanelBody>
    </Panel>
  );
}

/**
 * `/app/pipeline`. Every case by where it stands. The columns are states DealProof reads
 * from the record, not stages a person drags a card between: nobody can move a case to
 * "Assessed". Empty columns stay, so the board keeps its shape.
 */
export function Pipeline() {
  const [state, retry] = useWorkspace();
  const [view, setView] = useView();
  const [disposition, setDisposition] = useState<"all" | "with" | "without">("all");

  if (state.status === "loading") {
    return (
      <Page>
        <PageHeader title="Pipeline" />
        <Panel>
          <LoadingState label="Loading the pipeline" shape="rows" density="two-line" />
        </Panel>
      </Page>
    );
  }
  if (state.status === "error") {
    return (
      <Page>
        <PageHeader title="Pipeline" />
        <ErrorState size="page" what="The pipeline" reason={state.message} status={state.code} onRetry={retry} />
      </Page>
    );
  }

  const workspace = state.data;
  const shown = workspace.cases.filter((item) =>
    disposition === "all" ? true : disposition === "with" ? Boolean(item.disposition) : !item.disposition,
  );
  const grouped = Object.fromEntries(PIPELINE_COLUMNS.map((column) => [column, [] as CaseSummary[]])) as Record<
    PipelineColumn,
    CaseSummary[]
  >;
  for (const item of shown) grouped[pipelineColumn(item, workspace.details[item.id])].push(item);
  const coverage = coverageNote(workspace);

  return (
    <Page>
      <PageHeader
        title="Pipeline"
        meta={
          <>
            <span className="font-mono">{workspace.cases.length}</span>{" "}
            {workspace.cases.length === 1 ? "case" : "cases"} by where they stand
            {coverage ? <span className="font-mono text-xs text-ink-muted"> · request state {coverage}</span> : null}
          </>
        }
        figures={[
          { label: "Request drafted", value: grouped.drafted.length, href: "/app/approvals" },
          { label: "Waiting on identity", value: grouped.identity.length },
        ]}
      />

      {workspace.cases.length === 0 ? (
        <EmptyState
          size="page"
          title="No cases yet"
          actions={
            <Link href="/app/discover/new" className="text-dense text-accent underline underline-offset-2">
              New screening
            </Link>
          }
        >
          Cases appear here once a company is opened for verification, each in the column its
          record puts it in.
        </EmptyState>
      ) : (
        <>
          <Toolbar count={`${shown.length} shown`}>
            <Segmented
              label="View"
              value={view}
              onChange={setView}
              options={[
                { value: "board", label: "Board" },
                { value: "table", label: "Table" },
              ]}
            />
            <Segmented
              label="Filter by disposition"
              value={disposition}
              onChange={setDisposition}
              options={[
                { value: "all", label: "All", count: workspace.cases.length },
                { value: "with", label: "Has a disposition", count: workspace.cases.filter((c) => c.disposition).length },
                { value: "without", label: "None yet", count: workspace.cases.filter((c) => !c.disposition).length },
              ]}
            />
          </Toolbar>
          {view === "board" ? (
            <Board workspace={workspace} grouped={grouped} />
          ) : (
            <PipelineTable workspace={workspace} grouped={grouped} />
          )}
        </>
      )}
    </Page>
  );
}
