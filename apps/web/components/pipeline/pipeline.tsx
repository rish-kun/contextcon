"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { caseHref, useShell } from "@/components/app-shell";
import { ClaimsCell, DispositionCell, FitCell, FitCompact, waitingCue } from "@/components/dashboard/case-cells";
import { DispositionStamp, StatusCounts } from "@/components/dealproof";
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
import { formatCredits, formatDate, plural } from "@/lib/format";
import { DISPOSITION_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import {
  attention,
  claimCounts,
  coverageNote,
  REQUEST_STATE_LABEL,
  requestState,
  type RequestState,
  useWorkspace,
  withAssessment,
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

const LANES = [
  "verifying",
  "identity",
  "failed",
  "unknown",
  "assessed",
  "approval",
  "approved",
  "sent",
  "suppressed",
  "sendFailed",
  "sendUnknown",
] as const;
type Lane = (typeof LANES)[number];

const LANE_LABEL: Record<Lane, string> = {
  verifying: "Verifying",
  identity: "Needs identity",
  failed: "Verification failed",
  unknown: "Unknown",
  assessed: "Assessed",
  approval: "Awaiting approval",
  approved: "Approved, not sent",
  sent: "Sent",
  suppressed: "Suppressed",
  sendFailed: "Send failed",
  sendUnknown: "Send unknown",
};

/** What puts a card in the lane, shown under its title so nobody has to guess why it is there. */
const LANE_RULE: Record<Lane, string> = {
  verifying: "Checks running now",
  identity: "Legal entity not confirmed",
  failed: "Checks stopped before an assessment",
  unknown: "Case record not read, so its state is not known",
  assessed: "By disposition, no request written",
  approval: "A drafted request waits on a person",
  approved: "Approved or sending, not confirmed sent",
  sent: "The provider accepted the request",
  suppressed: "Test mode held it back, nothing was sent",
  sendFailed: "The send failed, nothing was sent",
  sendUnknown: "No confirmation, it may or may not have left",
};

/** The lane each stored send state files a case under. One state, one lane: none stands in for another. */
const REQUEST_LANE: Record<RequestState, Lane> = {
  none: "assessed",
  draft: "approval",
  approved: "approved",
  sending: "approved",
  sent: "sent",
  suppressed: "suppressed",
  failed: "sendFailed",
  unknown: "sendUnknown",
};

/**
 * The lane a case sits in, read from its record. Work in flight comes first. A lane is a
 * claim about the case, so it is made only from a state the record holds: a case whose
 * record was not read is Unknown, never Assessed, and a request that was suppressed,
 * failed or went unconfirmed is never filed as sent or as waiting on approval.
 */
function laneOf(item: CaseSummary, detail: CaseDetail | undefined): Lane {
  if (item.status === "verifying") return "verifying";
  if (item.identity_state !== "confirmed") return "identity";
  if (item.status === "failed") return "failed";
  if (!detail) return "unknown";
  return REQUEST_LANE[requestState(detail)];
}

/** The request chip's tone: a send that did not happen, or cannot be confirmed, is not quiet. */
const REQUEST_CHIP: Partial<Record<RequestState, string>> = {
  suppressed: "border border-dashed border-not-checked-line bg-not-checked-tint text-not-checked",
  failed: "border border-contradicted-line bg-contradicted-tint text-contradicted",
  unknown: "border border-dashed border-cannot-verify-line bg-cannot-verify-tint text-cannot-verify",
};

const DISPOSITION_ORDER = ["prioritise", "investigate_further", "deprioritise", "cannot_assess"] as const;

/** "2 blockers to Prioritise": how many open items stand between the case and the next disposition. */
function blockersLine(item: CaseSummary): string | null {
  const flip = item.decision_flip;
  if (!flip || flip.state !== "has_blockers" || flip.blockers_to_next < 1) return null;
  const next = flip.next_disposition ? DISPOSITION_LABEL[flip.next_disposition] : "the next disposition";
  return `${plural(flip.blockers_to_next, "blocker")} to ${next}`;
}

function host(website: string | null): string | null {
  if (!website) return null;
  return website.replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "") || null;
}

/** Only what the record holds: a field with no value is left out, not printed as "not scored". */
function CaseCard({ item, detail, lane }: { item: CaseSummary; detail: CaseDetail | undefined; lane: Lane }) {
  const counts = claimCounts(detail);
  const request = requestState(detail);
  const blockers = blockersLine(item);
  const domain = host(item.website);
  const running = lane === "verifying" ? waitingCue(item, detail) : null;
  const identity = lane === "identity" ? attention(item, detail)[0]?.what : null;
  const scored = item.fit_state === "scored" && item.fit !== null;
  return (
    <li className="relative flex flex-col gap-2 rounded-md border border-line bg-surface p-3 transition-colors hover:border-line-strong">
      <div className="flex min-w-0 flex-col">
        <RowLink stretch href={caseHref(item.id)} className="truncate text-sm">
          {item.name}
        </RowLink>
        <span className="truncate font-mono text-2xs text-ink-muted">
          {domain ? `${domain} · ` : null}
          <time dateTime={item.updated_at}>{formatDate(item.updated_at)}</time>
        </span>
      </div>
      {running ? (
        <span className="text-xs font-medium text-accent">{running}</span>
      ) : identity ? (
        <span className="text-xs text-cannot-verify">{identity}</span>
      ) : item.disposition && lane !== "assessed" ? (
        <DispositionStamp disposition={item.disposition} size="sm" className="self-start" />
      ) : null}
      {scored ? <FitCompact item={item} /> : null}
      {counts && detail && detail.claims.length > 0 ? <StatusCounts counts={counts} /> : null}
      {blockers ? (
        <span className="self-start rounded-xs border border-dashed border-line-strong px-1.5 py-0.5 font-mono text-xs text-ink-secondary">
          {blockers}
        </span>
      ) : null}
      {lane === "unknown" ? (
        <span className="text-xs text-cannot-verify">Record not read · request and claims not known</span>
      ) : request !== "none" ? (
        <span
          className={cn(
            "self-start rounded-xs px-1.5 py-0.5 text-xs",
            REQUEST_CHIP[request] ?? "bg-surface-sunken text-ink-secondary",
          )}
        >
          {REQUEST_STATE_LABEL[request]}
        </span>
      ) : null}
    </li>
  );
}

type Grouped = Record<Lane, CaseSummary[]>;

function Cards({ items, workspace, lane }: { items: CaseSummary[]; workspace: Workspace; lane: Lane }) {
  return (
    <ul className={cn("grid gap-2", lane === "assessed" && "sm:grid-cols-2")}>
      {items.map((item) => (
        <CaseCard key={item.id} item={item} detail={workspace.details[item.id]} lane={lane} />
      ))}
    </ul>
  );
}

function Board({ workspace, grouped }: { workspace: Workspace; grouped: Grouped }) {
  const filled = LANES.filter((lane) => grouped[lane].length > 0);
  const empty = LANES.filter((lane) => grouped[lane].length === 0);
  return (
    <div className="flex flex-col gap-4">
      {empty.length > 0 ? (
        <p className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          Empty lanes
          {empty.map((lane) => (
            <span key={lane} className="inline-flex h-6 items-center gap-1 rounded-xs border border-line bg-surface px-2 text-ink-secondary">
              {LANE_LABEL[lane]}
              <span className="font-mono text-2xs text-ink-muted">0</span>
            </span>
          ))}
        </p>
      ) : null}
      <ol className="flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-4 lg:overflow-x-auto lg:pb-2">
        {filled.map((lane) => (
          <li key={lane} className={cn("flex min-w-0 flex-col gap-3", lane === "assessed" ? "lg:min-w-96 lg:flex-[2]" : "lg:min-w-52 lg:flex-1")}>
            <div className="flex flex-col border-b border-line-strong pb-2">
              <h2 className="flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
                {LANE_LABEL[lane]}
                <span className="font-mono text-xs font-normal text-ink-muted">{grouped[lane].length}</span>
              </h2>
              <p className="text-xs text-ink-muted">{LANE_RULE[lane]}</p>
            </div>
            {lane === "assessed" ? (
              <>
                {DISPOSITION_ORDER.filter((d) => grouped.assessed.some((item) => item.disposition === d)).map((d) => (
                  <div key={d} className="flex flex-col gap-2">
                    <DispositionStamp disposition={d} size="sm" className="self-start" />
                    <Cards items={grouped.assessed.filter((item) => item.disposition === d)} workspace={workspace} lane={lane} />
                  </div>
                ))}
                {grouped.assessed.some((item) => !item.disposition) ? (
                  <div className="flex flex-col gap-2">
                    <h3 className="text-xs font-medium text-ink-secondary">No disposition yet</h3>
                    <Cards items={grouped.assessed.filter((item) => !item.disposition)} workspace={workspace} lane={lane} />
                  </div>
                ) : null}
              </>
            ) : (
              <Cards items={grouped[lane]} workspace={workspace} lane={lane} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PipelineTable({ workspace, grouped }: { workspace: Workspace; grouped: Grouped }) {
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
              <TableHead>To next disposition</TableHead>
              <TableHead>Request</TableHead>
              <TableHead numeric>Updated</TableHead>
            </TableRow>
          </TableHeader>
          {LANES.filter((column) => grouped[column].length > 0).map((column) => (
            <TableBody key={column}>
              <tr className="border-b border-line bg-surface-sunken">
                <th colSpan={7} scope="colgroup" className="h-8 px-4 text-left text-xs font-medium text-ink-secondary">
                  {LANE_LABEL[column]}{" "}
                  <span className="pl-1 font-mono font-normal text-ink-muted">{grouped[column].length}</span>
                  <span className="pl-3 font-normal text-ink-muted">{LANE_RULE[column]}</span>
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
                        {attention(item, detail)[0]?.what ?? (detail ? "Nothing waiting" : "Record not read")}
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
                    <TableCell muted={!blockersLine(item)} className="font-mono text-xs whitespace-nowrap">
                      {blockersLine(item) ?? "–"}
                    </TableCell>
                    <TableCell muted={!detail || requestState(detail) === "none"}>
                      {detail ? REQUEST_STATE_LABEL[requestState(detail)] : "Unknown · record not read"}
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
 * `/app/pipeline`. Every case by where it stands: lanes for work in flight, then the
 * assessed cases by disposition, then one lane per stored send state. The lanes are read
 * from the record, not stages a person drags a card between, and a case whose record was
 * not read sits in Unknown. Empty lanes are named above the board with a zero.
 */
export function Pipeline() {
  const { openVerify } = useShell();
  const [state, retry] = useWorkspace();
  const [view, setView] = useView();
  const [query, setQuery] = useState("");

  if (state.status === "loading") {
    return (
      <Page>
        <PageHeader title="Pipeline" />
        <Panel>
          <LoadingState label="Loading pipeline" shape="rows" density="two-line" />
        </Panel>
      </Page>
    );
  }
  if (state.status === "error") {
    return (
      <Page>
        <PageHeader title="Pipeline" />
        <ErrorState size="page" what="Pipeline" reason={state.message} status={state.code} onRetry={retry} />
      </Page>
    );
  }

  const workspace = state.data;
  const needle = query.trim().toLowerCase();
  const cases = workspace.cases.map((item) => withAssessment(item, workspace.details[item.id]));
  const shown = cases.filter((item) => !needle || item.name.toLowerCase().includes(needle));
  const group = (cases: CaseSummary[]) => {
    const out = Object.fromEntries(LANES.map((lane) => [lane, [] as CaseSummary[]])) as Grouped;
    for (const item of cases) out[laneOf(item, workspace.details[item.id])].push(item);
    return out;
  };
  const all = group(cases);
  const credits = cases.reduce((sum, item) => sum + item.cost.crustdata_credits, 0);
  const grouped = group(shown);
  const coverage = coverageNote(workspace);

  return (
    <Page>
      <PageHeader
        title="Pipeline"
        meta={
          <>
            <span className="font-mono">{workspace.cases.length}</span>{" "}
            {workspace.cases.length === 1 ? "case" : "cases"}, each filed by its own record
            {coverage ? <span className="font-mono text-xs text-ink-muted"> · request state {coverage}</span> : null}
          </>
        }
        actions={<Button onClick={openVerify}>Verify a company</Button>}
      />

      {workspace.cases.length === 0 ? (
        <EmptyState
          size="page"
          title="No cases in the pipeline"
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
          A case lands in a lane once a company is opened for verification, and moves as DealProof
          verifies claims, writes an assessment and drafts a request.
        </EmptyState>
      ) : (
        <>
          <Panel>
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-line sm:grid-cols-3 lg:grid-cols-6">
              {LANES.map((lane) => (
                <div key={lane} className="flex flex-col gap-0.5 bg-surface px-4 py-3">
                  <dt className="text-xs text-ink-secondary">{LANE_LABEL[lane]}</dt>
                  <dd className={cn("font-mono text-xl font-medium", all[lane].length > 0 ? "text-ink" : "text-ink-muted")}>
                    {all[lane].length}
                  </dd>
                </div>
              ))}
              <div className="flex flex-col gap-0.5 bg-surface px-4 py-3">
                <dt className="text-xs text-ink-secondary">Credits spent</dt>
                <dd className="font-mono text-xl font-medium text-ink">{formatCredits(credits)}</dd>
              </div>
            </dl>
          </Panel>
          <Toolbar count={`${shown.length} of ${workspace.cases.length}`}>
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by company"
              aria-label="Search by company"
              className="h-8 w-56 text-dense"
            />
            <Segmented
              label="View"
              value={view}
              onChange={setView}
              options={[
                { value: "board", label: "Board" },
                { value: "table", label: "Table" },
              ]}
            />
          </Toolbar>
          {shown.length === 0 ? (
            <Panel>
              <EmptyState
                title="No cases match this search"
                actions={
                  <Button size="sm" onClick={() => setQuery("")}>
                    Reset search
                  </Button>
                }
              >
                Clear the search to see the full board.
              </EmptyState>
            </Panel>
          ) : view === "board" ? (
            <Board workspace={workspace} grouped={grouped} />
          ) : (
            <PipelineTable workspace={workspace} grouped={grouped} />
          )}
        </>
      )}
    </Page>
  );
}
