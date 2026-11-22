"use client";

import Link from "next/link";
import { StatRow, StatTile } from "@/components/insight";
import {
  Button,
  EmptyState,
  ErrorState,
  Loadable,
  LoadingState,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  PanelFooter,
  PanelGrid,
  PanelGridItem,
  PanelHeader,
  RowLink,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextLink,
} from "@/components/ui";
import { useShell, caseHref } from "@/components/app-shell";
import { listInvestorSearches, listTheses } from "@/lib/api/client";
import { formatCredits, formatDate, formatDateTime, plural } from "@/lib/format";
import { DISPOSITION_LABEL } from "@/lib/labels";
import { DISPOSITIONS } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { attention, claimCounts, coverageNote, useWorkspace, type Workspace } from "@/lib/workspace";
import { ResearchHome } from "@/components/home/research-home";
import { ClaimsCell, DispositionCell, FitCompact, waitingCue } from "./case-cells";

const THESIS_STATUS = {
  draft: "Criteria ready, not searched",
  searching: "Searching",
  ready: "Shortlist ready",
  failed: "Search stopped",
} as const;

const RECENT_LIMIT = 8;
const RAIL_LIMIT = 4;

function modelUsd(value: number): string {
  return value > 0 && value < 0.005 ? "under $0.01" : `$${value.toFixed(2)}`;
}

/** Cases at each disposition as ranked rows with one neutral bar each. Not a chart of anything else. */
function ByDisposition({ workspace }: { workspace: Workspace }) {
  const rows = DISPOSITIONS.map((disposition) => ({
    label: DISPOSITION_LABEL[disposition],
    count: workspace.cases.filter((item) => item.disposition === disposition).length,
  }));
  const none = workspace.cases.filter((item) => !item.disposition).length;
  const largest = Math.max(1, none, ...rows.map((row) => row.count));
  const row = (label: string, count: number, apart = false) => (
    <li
      key={label}
      className={`grid grid-cols-[minmax(0,1fr)_5rem_1.5rem] items-center gap-3 px-4 py-2 text-dense ${apart ? "border-t border-line text-ink-secondary" : "text-ink"}`}
    >
      <span className="truncate">{label}</span>
      <span aria-hidden className="h-2">
        <span
          className="block h-full min-w-0.5 rounded-r-xs bg-ink-muted"
          style={{ width: `${(count / largest) * 100}%`, opacity: count === 0 ? 0 : 1 }}
        />
      </span>
      <span className="text-right font-mono text-xs font-medium">{count}</span>
    </li>
  );
  return (
    <ul className="py-1">
      {rows.map((item) => row(item.label, item.count))}
      {row("No disposition yet", none, true)}
    </ul>
  );
}

function NeedsYou({ workspace }: { workspace: Workspace }) {
  const waiting = workspace.cases.flatMap((item) =>
    attention(item, workspace.details[item.id]).map((entry) => ({ item, entry })),
  );
  return (
    <Panel aria-labelledby="needs-you">
      <PanelHeader id="needs-you" title="Needs you" meta={waiting.length} />
      <PanelBody flush>
        {waiting.length === 0 ? (
          <EmptyState title="Nothing is waiting on you">
            Unresolved identities, requests to approve, failed runs and checks that were not run
            appear here.
          </EmptyState>
        ) : (
          <Table density="default" flush>
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>What is waiting</TableHead>
                <TableHead numeric>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {waiting.map(({ item, entry }) => (
                <TableRow key={`${item.id}-${entry.what}`} className="relative">
                  <TableCell>
                    <RowLink stretch href={`${caseHref(item.id)}/${entry.segment}`}>
                      {item.name}
                    </RowLink>
                  </TableCell>
                  <TableCell>{entry.what}</TableCell>
                  <TableCell numeric>{formatDate(item.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </PanelBody>
    </Panel>
  );
}

function RecentCases({ workspace }: { workspace: Workspace }) {
  const shown = workspace.cases.slice(0, RECENT_LIMIT);
  return (
    <Panel aria-labelledby="recent-cases">
      <PanelHeader id="recent-cases" title="Recently updated cases" meta={shown.length} />
      <PanelBody flush>
        <Table density="two-line" flush>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Disposition</TableHead>
              <TableHead>Fit · assessable</TableHead>
              <TableHead>Claims</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((item) => {
              const detail = workspace.details[item.id];
              return (
                <TableRow key={item.id} className="relative">
                  <TableCell className="min-w-48">
                    <RowLink stretch href={caseHref(item.id)}>
                      {item.name}
                    </RowLink>
                    <span className="block text-xs text-ink-muted">
                      {waitingCue(item, detail) ??
                        (item.identity_state === "confirmed" ? "Identity confirmed" : "Identity unresolved")}
                      {" · "}
                      <span className="font-mono">{formatDate(item.updated_at)}</span>
                    </span>
                  </TableCell>
                  <TableCell>
                    <DispositionCell item={item} />
                  </TableCell>
                  <TableCell>
                    <FitCompact item={item} />
                  </TableCell>
                  <TableCell className="min-w-44">
                    <ClaimsCell item={item} detail={detail} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </PanelBody>
      <PanelFooter>
        <TextLink href="/app/companies">
          View all {plural(workspace.cases.length, "company", "companies")}
        </TextLink>
      </PanelFooter>
    </Panel>
  );
}

function Screenings() {
  const [state, retry] = useLoad("theses", () => listTheses(), "The screenings were not returned");
  return (
    <Panel aria-labelledby="overview-screenings">
      <PanelHeader
        id="overview-screenings"
        title="Screenings"
        meta={state.status === "ready" ? state.data.length : undefined}
      />
      <PanelBody flush>
        <Loadable
          state={state}
          what="Screenings"
          onRetry={retry}
          loading={{ label: "Loading screenings", shape: "lines", count: 3 }}
          isEmpty={(data) => data.length === 0}
          empty={
            <EmptyState
              title="No screenings yet"
              actions={
                <Button asChild size="sm">
                  <Link href="/app/discover/new">New screening</Link>
                </Button>
              }
            >
              A screening turns a thesis into criteria and a shortlist of real companies.
            </EmptyState>
          }
        >
          {(theses) => (
            <ul className="divide-y divide-line">
              {[...theses]
                .sort((a, b) => b.created_at.localeCompare(a.created_at))
                .slice(0, RAIL_LIMIT)
                .map((thesis) => (
                  <li key={thesis.id} className="relative flex flex-col gap-1 px-4 py-3 transition-colors hover:bg-surface-raised">
                    <RowLink
                      stretch
                      href={`/app/discover/${encodeURIComponent(thesis.id)}`}
                      className="line-clamp-2 text-dense font-normal"
                    >
                      {thesis.text}
                    </RowLink>
                    <span className="text-xs text-ink-muted">
                      {THESIS_STATUS[thesis.status]} ·{" "}
                      <span className="font-mono">{thesis.shortlist_count}</span> shortlisted ·{" "}
                      <span className="font-mono">{formatDate(thesis.created_at)}</span>
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Loadable>
      </PanelBody>
      <PanelFooter>
        <TextLink href="/app/discover">All screenings</TextLink>
      </PanelFooter>
    </Panel>
  );
}

function InvestorSearches() {
  const [state, retry] = useLoad("investor-searches", () => listInvestorSearches(), "The searches were not returned");
  return (
    <Panel aria-labelledby="overview-investors">
      <PanelHeader
        id="overview-investors"
        title="Investor searches"
        meta={state.status === "ready" ? state.data.length : undefined}
      />
      <PanelBody flush>
        <Loadable
          state={state}
          what="Investor searches"
          onRetry={retry}
          loading={{ label: "Loading investor searches", shape: "lines", count: 2 }}
          isEmpty={(data) => data.length === 0}
          empty={
            <EmptyState
              title="No investor searches yet"
              actions={
                <Button asChild size="sm">
                  <Link href="/app/investors/new">Find investors</Link>
                </Button>
              }
            >
              For a business raising money: investors with dated rounds in comparable companies.
            </EmptyState>
          }
        >
          {(searches) => (
            <ul className="divide-y divide-line">
              {[...searches]
                .sort((a, b) => b.created_at.localeCompare(a.created_at))
                .slice(0, RAIL_LIMIT)
                .map((search) => (
                  <li key={search.id} className="relative flex flex-col gap-1 px-4 py-3 transition-colors hover:bg-surface-raised">
                    <RowLink
                      stretch
                      href={`/app/investors/${encodeURIComponent(search.id)}`}
                      className="text-dense font-normal"
                    >
                      {search.sector}
                    </RowLink>
                    <span className="text-xs text-ink-muted">
                      {search.location} · <span className="font-mono">{search.entries_count}</span>{" "}
                      {search.entries_count === 1 ? "investor" : "investors"} ·{" "}
                      <span className="font-mono">{formatDate(search.created_at)}</span>
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Loadable>
      </PanelBody>
    </Panel>
  );
}

function Book({ workspace }: { workspace: Workspace }) {
  const { cases, details } = workspace;
  const running = cases.filter((item) => item.status === "verifying").length;
  const needing = cases.filter((item) => attention(item, details[item.id]).length > 0).length;
  const assessed = cases.filter((item) => item.disposition).length;
  const prioritise = cases.filter((item) => item.disposition === "prioritise").length;
  const perCase = cases.map((item) => claimCounts(details[item.id])?.not_checked ?? 0);
  const notChecked = perCase.reduce((sum, count) => sum + count, 0);
  const credits = cases.reduce((sum, item) => sum + item.cost.crustdata_credits, 0);
  const usd = cases.reduce((sum, item) => sum + item.cost.llm_usd, 0);
  const coverage = coverageNote(workspace);

  return (
    <>
      <StatRow label="Book of work">
        <StatTile
          label="Cases"
          href="/app/companies"
          value={cases.length}
          note={running > 0 ? `${running} verifying now` : "None running"}
        />
        <StatTile
          label="Need you"
          href="/app/pipeline"
          value={needing}
          note="Identity, approvals, failed runs"
        />
        <StatTile
          label="Prioritise"
          href="/app/pipeline"
          value={prioritise}
          note={`of ${assessed} with a disposition`}
        />
        <StatTile
          label="Checks not run"
          value={notChecked}
          note={
            notChecked > 0
              ? `across ${plural(perCase.filter((count) => count > 0).length, "case")}`
              : "Every claim on file was checked"
          }
        />
        <StatTile
          label="Spent on cases"
          value={formatCredits(credits)}
          unit="credits"
          note={`${modelUsd(usd)} model usage, counted apart`}
        />
      </StatRow>
      {coverage ? <p className="-mt-3 font-mono text-2xs text-ink-muted">Claim and request figures {coverage}</p> : null}

      <PanelGrid>
        <PanelGridItem span={8}>
          <NeedsYou workspace={workspace} />
          <RecentCases workspace={workspace} />
        </PanelGridItem>
        <PanelGridItem span={4}>
          <Panel aria-labelledby="by-disposition">
            <PanelHeader id="by-disposition" title="By disposition" meta={cases.length} />
            <PanelBody flush>
              <ByDisposition workspace={workspace} />
            </PanelBody>
            <PanelFooter>
              <TextLink href="/app/pipeline">Open the pipeline</TextLink>
            </PanelFooter>
          </Panel>
          <Screenings />
          <InvestorSearches />
        </PanelGridItem>
      </PanelGrid>
    </>
  );
}

/**
 * `/app`. The state of the book of work on one screen: how many cases there are and
 * where they stand, what is waiting on a person, and what was touched last. Every figure
 * is counted from records DealProof holds; there is no time series of cases, so no trend
 * is drawn.
 */
export function Overview() {
  const { openVerify } = useShell();
  const [state, retry] = useWorkspace();
  const ready = state.status === "ready" ? state.data : null;

  return (
    <Page>
      <PageHeader
        title="Overview"
        meta={
          ready ? (
            <>
              <span className="font-mono">{ready.cases.length}</span> {ready.cases.length === 1 ? "case" : "cases"}
              , read <span className="font-mono">{formatDateTime(ready.loadedAt)}</span>
            </>
          ) : undefined
        }
        actions={
          <>
            <Button onClick={openVerify}>Verify a company</Button>
            <Button asChild variant="primary">
              <Link href="/app/discover/new">New screening</Link>
            </Button>
          </>
        }
      />

      <ResearchHome />

      {state.status === "loading" ? (
        <Panel>
          <LoadingState label="Loading the overview" shape="tiles" count={4} />
        </Panel>
      ) : state.status === "error" ? (
        <ErrorState size="page" what="Cases" reason={state.message} status={state.code} onRetry={retry} />
      ) : state.data.cases.length === 0 ? (
        <>
          <EmptyState size="page" title="No cases yet">
            A case is one company under review: its identity, each claim checked against dated
            evidence, and a screening assessment. Start from a thesis with New screening, or go
            straight to a company you already have in mind.
          </EmptyState>
          <PanelGrid>
            <PanelGridItem span={6}>
              <Screenings />
            </PanelGridItem>
            <PanelGridItem span={6}>
              <InvestorSearches />
            </PanelGridItem>
          </PanelGrid>
        </>
      ) : (
        <Book workspace={state.data} />
      )}
    </Page>
  );
}
