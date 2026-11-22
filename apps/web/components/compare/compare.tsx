"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { caseHref, useShell } from "@/components/app-shell";
import { DispositionStamp, StatusCounts } from "@/components/dealproof";
import { formatAmountUsd } from "@/components/discover/adapt";
import {
  Button,
  EmptyState,
  ErrorState,
  Icon,
  Input,
  LoadingState,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  Popover,
  PopoverContent,
  PopoverTrigger,
  RowLink,
} from "@/components/ui";
import { FitBar } from "@/components/workspace/fit-bar";
import { getCase, type CaseDetail, type CaseSummary } from "@/lib/api/client";
import { hostOf } from "@/lib/directory";
import { formatCredits, formatDate, formatUsd, plural } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { useUrlState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { claimCounts, loadWorkspace, useWorkspace } from "@/lib/workspace";

const MIN = 2;
const MAX = 4;

const CRITERION_STATE = { pass: "Met", fail: "Not met", unknown: "Unknown · could not assess" } as const;
const FIT_NOTE: Record<string, string> = {
  identity_unresolved: "Waits on identity",
  awaiting_strategy_criteria: "No criteria set for this case",
  unavailable: "Fit unavailable",
};

/** An absent value: a dash to the eye, the reason on hover and to a screen reader. */
function Dash({ why }: { why: string }) {
  return (
    <span className="text-ink-muted" title={why}>
      <span aria-hidden>–</span>
      <span className="sr-only">{why}</span>
    </span>
  );
}

/** A value over a quieter second line. */
function Two({ top, bottom }: { top: React.ReactNode; bottom?: React.ReactNode }) {
  return (
    <span className="flex flex-col">
      <span>{top}</span>
      {bottom ? <span className="text-xs text-ink-muted">{bottom}</span> : null}
    </span>
  );
}

interface Row {
  label: string;
  cell: (detail: CaseDetail) => React.ReactNode;
}

interface Group {
  title: string;
  /** One line in place of the rows, when the cases cannot be read row by row. */
  note?: string;
  rows: Row[];
}

const SUMMARY: Row[] = [
  {
    label: "Disposition",
    cell: (detail) => {
      const disposition = detail.assessment?.judgments.screening_disposition.disposition;
      return disposition ? <DispositionStamp disposition={disposition} size="sm" /> : <Dash why="No assessment has been written yet" />;
    },
  },
  {
    label: "Identity",
    cell: ({ identity }) =>
      identity.state === "confirmed"
        ? `Confirmed · ${plural(identity.keys.length, "key")}`
        : `${identity.state === "ambiguous" ? "Ambiguous" : "Unresolved"} · ${plural(identity.candidates.length, "candidate")}`,
  },
  {
    label: "Fit · assessable",
    cell: (detail) => {
      const fit = detail.assessment?.judgments.opportunity_fit ?? detail.opportunity;
      const state = "state" in fit ? fit.state : fit.fit_state;
      if (state === "scored" && fit.fit !== null) return <FitBar fit={fit.fit} pct={fit.assessable_pct} />;
      return <span className="text-ink-secondary">{FIT_NOTE[state] ?? "Fit unavailable"}</span>;
    },
  },
];

const PROFILE: Row[] = [
  {
    label: "Headquarters",
    cell: ({ profile }) => profile?.headquarters?.value ?? profile?.country?.value ?? <Dash why="No headquarters on record" />,
  },
  {
    label: "Founded",
    cell: ({ profile }) =>
      profile?.year_founded ? <span className="font-mono text-xs">{profile.year_founded.value}</span> : <Dash why="No founding year on record" />,
  },
  {
    label: "People",
    cell: ({ profile }) =>
      profile?.headcount ? (
        <span title={`Estimate · ${profile.headcount.estimate_basis ?? "from professional profiles, not a payroll count"}`}>
          <span className="underline-estimate font-mono text-xs">~{profile.headcount.value.toLocaleString("en-US")}</span>
          <span className="pl-2 font-mono text-2xs text-ink-secondary">Estimate</span>
        </span>
      ) : (
        <Dash why="No profile-based headcount estimate on record" />
      ),
  },
  {
    label: "People, change in a year",
    cell: ({ profile }) => {
      const growth = profile?.headcount_growth_yoy_pct;
      if (!growth) return <Dash why="No year-on-year headcount estimate on record" />;
      return (
        <span className="font-mono text-xs">
          {growth.value > 0 ? "+" : ""}
          {Math.round(growth.value)}%<span className="pl-2 text-2xs text-ink-secondary">Signal</span>
        </span>
      );
    },
  },
  {
    label: "Total funding",
    cell: ({ profile }) =>
      profile?.total_funding_usd ? (
        <Two
          top={<span className="font-mono text-xs">{formatAmountUsd(profile.total_funding_usd.value)}</span>}
          bottom={profile.funding_rounds.length > 0 ? plural(profile.funding_rounds.length, "round") : undefined}
        />
      ) : (
        <Dash why="No funding total on record" />
      ),
  },
  {
    label: "Company type",
    cell: ({ profile }) =>
      profile?.company_type ? (
        <span title={profile.company_type_reason ?? undefined}>{profile.company_type === "startup" ? "Startup" : "Established"}</span>
      ) : (
        <Dash why="Company type not determined" />
      ),
  },
];

const CLAIMS: Row[] = [
  {
    label: "Settled",
    cell: ({ claims }) => {
      if (claims.length === 0) return <span className="text-ink-muted">No claims yet</span>;
      const settled = claims.filter((claim) => claim.status !== "cannot_verify" && claim.status !== "not_checked").length;
      return (
        <span className="font-mono text-xs">
          {settled} of {claims.length}
        </span>
      );
    },
  },
  {
    label: "By status",
    cell: (detail) => {
      const counts = claimCounts(detail);
      return counts && detail.claims.length > 0 ? <StatusCounts counts={counts} /> : <Dash why="No claims on record" />;
    },
  },
];

const notAssessed = <Dash why="No assessment has been written yet" />;

const JUDGMENTS: Row[] = [
  {
    label: "Opportunity fit",
    cell: ({ assessment }) => {
      const fit = assessment?.judgments.opportunity_fit;
      if (!fit) return notAssessed;
      if (fit.state !== "scored" || fit.fit === null) return <Two top={FIT_NOTE[fit.state] ?? "Fit unavailable"} bottom={fit.note} />;
      const met = fit.criterion_results.filter((result) => result.state === "pass").length;
      return (
        <Two
          top={<span className="font-mono text-xs">Fit {Math.round(fit.fit)} · {Math.round(fit.assessable_pct)}% assessable</span>}
          bottom={fit.criterion_results.length > 0 ? `${met} of ${plural(fit.criterion_results.length, "criterion", "criteria")} met` : undefined}
        />
      );
    },
  },
  {
    label: "Evidence sufficiency",
    cell: ({ assessment }) => {
      const sufficiency = assessment?.judgments.evidence_sufficiency;
      if (!sufficiency) return notAssessed;
      const required = sufficiency.required_categories.length;
      return (
        <Two
          top={
            <span className="font-mono text-xs">
              {sufficiency.settled.length} of {required} required checks settled
            </span>
          }
          bottom={sufficiency.gaps.length > 0 ? `${plural(sufficiency.gaps.length, "gap")} open` : "No gaps open"}
        />
      );
    },
  },
  {
    label: "Business assessment",
    cell: ({ assessment }) => {
      const business = assessment?.judgments.business_assessment;
      if (!business) return notAssessed;
      return business.assessed ? (
        <Two top={plural(business.signals.length, "operating signal")} bottom={business.signals.map((signal) => signal.label).join(", ") || undefined} />
      ) : (
        <Two top="Not assessed" bottom={business.reason} />
      );
    },
  },
  {
    label: "Financial assessment",
    cell: ({ assessment }) => {
      const financial = assessment?.judgments.financial_assessment;
      if (!financial) return notAssessed;
      return financial.assessed ? (
        <Two
          top={financial.conclusion ?? plural(financial.figures.length, "figure")}
          bottom={financial.period ? `Period ${financial.period}` : undefined}
        />
      ) : (
        <Two top="Not assessed" bottom={financial.reason ?? "No reliable financial inputs"} />
      );
    },
  },
  {
    label: "Screening disposition",
    cell: ({ assessment }) => {
      const result = assessment?.judgments.screening_disposition;
      if (!result) return notAssessed;
      return (
        <ul className="flex list-none flex-col gap-1 text-xs text-ink-secondary">
          {result.reasons.length === 0 ? <li>No reasons recorded</li> : null}
          {result.reasons.slice(0, 3).map((reason) => (
            <li key={reason.text}>{reason.text}</li>
          ))}
          {result.reasons.length > 3 ? <li className="text-ink-muted">and {result.reasons.length - 3} more in the case</li> : null}
        </ul>
      );
    },
  },
];

const RECORD: Row[] = [
  {
    label: "Latest dated event",
    cell: ({ events }) => {
      const latest = [...events].sort((a, b) => b.event_date.localeCompare(a.event_date))[0];
      return latest ? (
        <Two top={latest.title} bottom={<span className="font-mono">{formatDate(latest.event_date)}</span>} />
      ) : (
        <Dash why="No dated public event found for this entity" />
      );
    },
  },
  { label: "Sources", cell: ({ sources }) => <span className="font-mono text-xs">{sources.length}</span> },
  {
    label: "Assessment",
    cell: ({ assessment }) =>
      assessment ? (
        <span className="font-mono text-xs">
          v{assessment.version} · {formatDate(assessment.created_at)}
        </span>
      ) : (
        notAssessed
      ),
  },
  {
    label: "Cost",
    cell: ({ cost }) => (
      <span className="font-mono text-xs">
        {formatCredits(cost.crustdata_credits)} cr · {formatUsd(cost.llm_usd)}
      </span>
    ),
  },
];

/** Criteria rows exist only when every case was scored against the same criteria. */
function criteriaGroup(details: CaseDetail[]): Group {
  const sets = details.map((detail) => detail.opportunity.criterion_results);
  const ids = (results: typeof sets[number]) => results.map((result) => result.criterion_id).sort().join("|");
  const shared = sets.length > 0 && sets[0].length > 0 && sets.every((results) => ids(results) === ids(sets[0]));
  if (!shared) {
    return {
      title: "Criteria",
      note: sets.every((results) => results.length === 0)
        ? "None of these cases has criteria set, so there is no fit to compare"
        : "These cases were scored against different criteria, so fit is not comparable row by row",
      rows: [],
    };
  }
  return {
    title: "Criteria",
    rows: sets[0].map((criterion) => ({
      label: `${criterion.label}${criterion.kind === "must" ? " · must-have" : ""}`,
      cell: (detail) => {
        const result = detail.opportunity.criterion_results.find((entry) => entry.criterion_id === criterion.criterion_id);
        if (!result) return <Dash why="Not scored for this case" />;
        return (
          <span className={result.state === "unknown" ? "text-ink-secondary" : undefined} title={result.reason}>
            {CRITERION_STATE[result.state]}
          </span>
        );
      },
    })),
  };
}

const LABEL_CELL = "sticky left-0 z-10 w-52 min-w-52 border-r border-line bg-surface px-4 text-left align-top text-xs font-medium text-ink-secondary";

function Matrix({ details, onRemove }: { details: CaseDetail[]; onRemove: (id: string) => void }) {
  const groups: Group[] = [
    { title: "", rows: SUMMARY },
    { title: "Profile", rows: PROFILE },
    criteriaGroup(details),
    { title: "Claims", rows: CLAIMS },
    { title: "The five judgments", rows: JUDGMENTS },
    { title: "Record", rows: RECORD },
  ];
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-collapse text-left text-dense text-ink">
        <thead>
          <tr className="border-b border-line-strong">
            <th scope="col" className={cn(LABEL_CELL, "py-3 align-bottom")}>
              <span className="sr-only">Field</span>
            </th>
            {details.map((detail) => (
              <th key={detail.case.id} scope="col" className="min-w-56 px-4 py-3 text-left align-bottom font-normal">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 flex-col">
                    <RowLink href={caseHref(detail.case.id)} className="truncate text-sm">
                      {detail.case.name}
                    </RowLink>
                    <span className="truncate font-mono text-2xs text-ink-muted">
                      {hostOf(detail.case.website) ?? "No domain on record"}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRemove(detail.case.id)}
                    aria-label={`Remove ${detail.case.name} from comparison`}
                    className="-mr-1 inline-flex size-6 shrink-0 items-center justify-center rounded-xs text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink print:hidden"
                  >
                    <Icon icon={X} size={14} />
                  </button>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        {groups.map((group) => (
          <tbody key={group.title || "summary"}>
            {group.title ? (
              <tr className="border-b border-line bg-surface-sunken">
                <th
                  colSpan={details.length + 1}
                  scope="colgroup"
                  className="h-8 px-4 text-left text-xs font-medium text-ink-secondary"
                >
                  <span className="sticky left-4">{group.title}</span>
                </th>
              </tr>
            ) : null}
            {group.note ? (
              <tr className="border-b border-line">
                <td colSpan={details.length + 1} className="px-4 py-2 text-ink-secondary">
                  <span className="sticky left-4">{group.note}</span>
                </td>
              </tr>
            ) : null}
            {group.rows.map((row) => (
              <tr key={row.label} className="border-b border-line last:border-b-0">
                <th scope="row" className={cn(LABEL_CELL, "py-2")}>
                  {row.label}
                </th>
                {details.map((detail) => (
                  <td key={detail.case.id} className="min-w-56 px-4 py-2 align-top">
                    {row.cell(detail)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

/** The cases that can be added, searched by name. Choosing one adds it and closes the list. */
function CasePicker({
  cases,
  selected,
  onAdd,
  primary = false,
}: {
  cases: CaseSummary[];
  selected: string[];
  onAdd: (id: string) => void;
  primary?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const full = selected.length >= MAX;
  const needle = query.trim().toLowerCase();
  const shown = cases.filter((item) => !needle || item.name.toLowerCase().includes(needle));
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={primary ? "primary" : "secondary"}
          disabled={full}
          title={full ? "Remove a case before adding another. A comparison holds up to four cases" : undefined}
        >
          Add a case
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="flex w-80 flex-col gap-2 p-2">
        <Input
          type="search"
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search cases to add"
          aria-label="Search cases to add"
          className="h-8 text-dense"
        />
        <ul className="flex max-h-72 flex-col overflow-y-auto">
          {shown.length === 0 ? <li className="px-2 py-2 text-dense text-ink-muted">No cases match this search</li> : null}
          {shown.map((item) => {
            const taken = selected.includes(item.id);
            return (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={taken}
                  onClick={() => {
                    onAdd(item.id);
                    setOpen(false);
                    setQuery("");
                  }}
                  className="flex h-9 w-full items-center justify-between gap-3 rounded-sm px-2 text-left text-dense text-ink transition-colors hover:bg-surface-raised disabled:text-ink-muted disabled:hover:bg-transparent"
                >
                  <span className="truncate">{item.name}</span>
                  <span className="shrink-0 font-mono text-2xs text-ink-muted">
                    {taken ? "Selected" : formatDate(item.updated_at)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="px-2 pb-1 text-xs text-ink-muted">Choose two to four cases</p>
      </PopoverContent>
    </Popover>
  );
}

function CopyLink() {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          /* the address bar holds the same link */
        }
      }}
    >
      <span aria-live="polite">{copied ? "Link copied" : "Copy link"}</span>
    </Button>
  );
}

interface Selection {
  details: CaseDetail[];
  /** Ids in the link whose case could not be read. */
  missing: string[];
}

/**
 * `/app/compare?cases=a,b,c`. Two to four cases side by side on what decides a screening.
 * No column is marked as a winner and nothing is totalled: the five judgments stay
 * separate here as everywhere. The selection is the URL, so the view can be shared.
 */
export function Compare() {
  const { openVerify } = useShell();
  const [workspaceState, retryWorkspace] = useWorkspace();
  const [params, setParams] = useUrlState();

  const ids = [...new Set((params.get("cases") ?? "").split(",").map((id) => id.trim()).filter(Boolean))].slice(0, MAX);
  const key = ids.join(",");
  const [selection, retrySelection] = useLoad<Selection>(
    `compare:${key}`,
    async () => {
      if (ids.length === 0) return { details: [], missing: [] };
      const workspace = await loadWorkspace();
      const settled = await Promise.allSettled(
        ids.map((id) => (workspace.details[id] ? Promise.resolve(workspace.details[id]) : getCase(id))),
      );
      const details: CaseDetail[] = [];
      const missing: string[] = [];
      settled.forEach((result, index) => {
        if (result.status === "fulfilled") details.push(result.value);
        else missing.push(ids[index]);
      });
      if (details.length === 0 && settled[0]?.status === "rejected") throw settled[0].reason;
      return { details, missing };
    },
    "The cases were not returned",
  );

  const setIds = (next: string[]) => setParams({ cases: next.length > 0 ? next.join(",") : null });

  if (workspaceState.status === "loading" || selection.status === "loading") {
    return (
      <Page>
        <PageHeader title="Compare" />
        <Panel>
          <LoadingState label="Loading comparison" shape="rows" density="compact" count={8} />
        </Panel>
      </Page>
    );
  }
  if (workspaceState.status === "error" || selection.status === "error") {
    const failed = workspaceState.status === "error" ? workspaceState : selection.status === "error" ? selection : null;
    return (
      <Page>
        <PageHeader title="Compare" />
        <ErrorState
          size="page"
          what="Comparison"
          reason={failed?.message}
          status={failed?.code}
          onRetry={() => {
            retryWorkspace();
            retrySelection();
          }}
        />
      </Page>
    );
  }

  const cases = workspaceState.data.cases;
  const { details, missing } = selection.data;
  const present = details.map((detail) => detail.case.id);
  const add = (id: string) => setIds([...present, id].slice(0, MAX));
  const theses = new Set(details.map((detail) => detail.opportunity.thesis_id));
  const sharedThesis = details.length >= MIN && theses.size === 1 ? details[0].opportunity.thesis_text : null;

  if (cases.length < MIN) {
    return (
      <Page>
        <PageHeader title="Compare" meta="Select two to four cases" />
        <EmptyState
          size="page"
          title="At least two cases are needed to compare"
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
          You currently have {plural(cases.length, "case")} on file. Start another verification or open a
          case from a screening shortlist.
        </EmptyState>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader
        title="Compare"
        meta={
          details.length === 0 ? (
            "Select two to four cases"
          ) : (
            <>
              <span className="font-mono">{details.length}</span> {details.length === 1 ? "case" : "cases side by side"}
              {sharedThesis ? (
                <>
                  {" "}
                  · shared screening: <span title={sharedThesis}>{sharedThesis.length > 72 ? `${sharedThesis.slice(0, 71)}…` : sharedThesis}</span>
                </>
              ) : null}
            </>
          )
        }
        actions={
          <span className="flex flex-wrap items-center gap-2 print:hidden">
            {details.length > 0 ? (
              <>
                <CopyLink />
                <Button onClick={() => window.print()}>Print</Button>
              </>
            ) : null}
            {details.length > 0 ? <CasePicker cases={cases} selected={present} onAdd={add} /> : null}
          </span>
        }
      />

      {missing.length > 0 ? (
        <p role="status" className="flex flex-wrap items-center gap-2 text-dense text-ink-secondary">
          {missing.length === 1
            ? "One case in this link is no longer available and was omitted"
            : `${missing.length} cases in this link are no longer available and were omitted`}
          <Button size="sm" onClick={() => setIds(present)}>
            Update the link
          </Button>
        </p>
      ) : null}

      {details.length === 0 ? (
        <EmptyState
          size="page"
          title="Choose two to four cases to compare"
          actions={
            <>
              <CasePicker cases={cases} selected={present} onAdd={add} primary />
              <Button asChild>
                <Link href="/app/companies?case=with">Browse companies</Link>
              </Button>
            </>
          }
        >
          Compare puts each case&apos;s disposition, identity, criteria, claim counts, the five judgments and
          cost side by side, without collapsing them into one winner.
        </EmptyState>
      ) : (
        <>
          {details.length < MIN ? (
            <p className="text-dense text-ink-secondary">Add one more case to compare it with {details[0].case.name}</p>
          ) : null}
          <Panel>
            <PanelBody flush>
              <Matrix details={details} onRemove={(id) => setIds(present.filter((entry) => entry !== id))} />
            </PanelBody>
          </Panel>
          <p className="max-w-(--layout-prose-max) text-xs text-ink-muted">
            No column is marked as a winner. Each judgment stays separate so evidence gaps remain visible. A dash
            means the record holds no value; its reason is on hover.
          </p>
        </>
      )}
    </Page>
  );
}
