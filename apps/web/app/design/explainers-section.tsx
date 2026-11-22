"use client";

/**
 * The five explainers in every state, for the component gallery. Sample data only: see
 * sample-data.ts. Each "event" button changes the record the way a run would, so the
 * motion can be reviewed without a live run. Nothing here moves until one is pressed.
 */
import { useState } from "react";
import {
  ChangeTimeline,
  CostMeter,
  CoverageMap,
  EvidenceTrail,
  PipelineRail,
  coverageFromClaims,
  meterFromCaseCost,
  meterFromRun,
  pipelineStations,
  timelineCause,
  versionState,
  type CoverageSelection,
  type EmptySearch,
  type PipelineInput,
  type TimelineEntry,
} from "@/components/explainers";
import { Button } from "@/components/ui";
import type { Claim, ClaimStatusCounts } from "@/lib/types";
import { cn } from "@/lib/utils";
import * as sample from "./sample-data";

function Specimen({
  label,
  note,
  children,
  className,
}: {
  label: string;
  note?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-xs text-ink-muted">
        <span className="font-medium text-ink-secondary">{label}</span>
        {note ? <span> · {note}</span> : null}
      </p>
      <div className={cn("min-w-0", className)}>{children}</div>
    </div>
  );
}

const framed = "rounded-lg border border-line";
const claim = (number: number): Claim => sample.claims.find((c) => c.number === number)!;

/* ───────────────────────── Sample records ───────────────────────── */

/** Searches that came back empty. The API does not record these yet; the gallery shows the drawing. */
const emptySearches: EmptySearch[] = [
  { claim_id: "c5", reliability: "registry_mirror", label: "Registry mirror" },
  { claim_id: "c2", reliability: "audited_statement" },
];

const nothingFound: Claim = {
  ...claim(2),
  id: "c2-empty",
  record: [],
  note: "No independent source carries a headcount for this company.",
};

const counts: ClaimStatusCounts = {
  supported: 1,
  partially_corroborated: 1,
  conflicting_evidence: 1,
  contradicted: 1,
  cannot_verify: 1,
  not_checked: 2,
};

const pipelineBase: PipelineInput = {
  basePath: "#explainers",
  created_at: "2026-11-21T04:30:00Z",
  owner_name: sample.sampleUser.name,
  thesis_id: "sample-thesis",
  identity_confirmed: true,
  runs: [{ kind: "verify", state: "done", finished_at: "2026-11-22T11:12:00Z" }],
  live_run_kind: null,
  claim_counts: counts,
  assessment: {
    version: 1,
    created_at: "2026-11-22T11:12:00Z",
    disposition: "investigate_further",
    assessable_share: 0.7,
  },
  request: { status: "draft", documents: 3, at: null },
};

const noCounts: ClaimStatusCounts = { ...counts, supported: 0, partially_corroborated: 0, conflicting_evidence: 0, contradicted: 0, cannot_verify: 0, not_checked: 0 };

const sampleDocuments = [
  {
    id: "doc-lease",
    filename: "Lease agreement.pdf",
    uploaded_at: "2026-11-22T11:01:00Z",
    uploaded_by_name: sample.sampleUser.name,
  },
];

const statusesV1 = sample.claims.map((c) => c.status);
const statusesV2 = statusesV1.map((status, index) => (index === 4 ? ("supported" as const) : status));

const timelineV1: TimelineEntry = {
  meta: sample.versions[0],
  state: versionState(statusesV1, "investigate_further"),
  cause: null,
  diff: null,
};
const timelineV2: TimelineEntry = {
  meta: sample.versions[1],
  state: versionState(statusesV2, "prioritise"),
  cause: timelineCause(sample.versions[1].trigger, ["doc-lease"], sample.diff, sampleDocuments),
  diff: sample.diff,
};
const timelineV3: TimelineEntry = {
  meta: { version: 3, created_at: "2026-11-23T05:10:00Z", trigger: "recheck after a new filing" },
  state: versionState(statusesV2.map((s, i) => (i === 0 ? ("conflicting_evidence" as const) : s)), "investigate_further"),
  cause: timelineCause("recheck after a new filing", [], sample.diffDowngrade, sampleDocuments),
  diff: sample.diffDowngrade,
};

/* ───────────────────────── Section ───────────────────────── */

export function ExplainersSection() {
  const [verifyDone, setVerifyDone] = useState(false);
  const [selection, setSelection] = useState<CoverageSelection | null>(null);
  const [arrived, setArrived] = useState(false);
  const [spent, setSpent] = useState(38);

  const coverage = coverageFromClaims(sample.claims, { emptySearches });
  const liveRun = { ...sample.runRunning, credits_used: spent };

  return (
    <section id="explainers" aria-labelledby="explainers-title" className="flex scroll-mt-6 flex-col gap-6">
      <div className="flex flex-col gap-1 border-b border-line-strong pb-3">
        <h2 id="explainers-title" className="text-2xl font-medium text-ink">
          Explainers
        </h2>
        <p className="max-w-(--layout-prose-max) text-sm text-ink-secondary">
          Five views that draw how a conclusion was reached, from the case&apos;s own records.
          Each is static on a page visit and moves only when the record changes while the
          reader is watching. With no data, each says what would fill it.
        </p>
      </div>

      {/* Evidence trail */}
      <Specimen
        label="Evidence trail"
        note="claim, sources, dated facts, rule, status. The dashed row is a search that found nothing"
        className={framed}
      >
        <EvidenceTrail claim={claim(5)} emptySearches={emptySearches} className="rounded-lg" />
      </Specimen>
      <Specimen
        label="Conflicting evidence"
        note="the disagreeing sources are stacked with a marker between them, and both lead into the rule"
        className={framed}
      >
        <EvidenceTrail claim={claim(4)} className="rounded-lg" />
      </Specimen>
      <div className="grid gap-6 xl:grid-cols-2">
        <Specimen label="Checked, nothing found" note="without recorded searches, it says that the sources searched are not known" className={framed}>
          <EvidenceTrail claim={nothingFound} className="rounded-lg" />
        </Specimen>
        <Specimen label="Not checked" note="the other four columns are one hatched block" className={framed}>
          <EvidenceTrail claim={claim(6)} onRunCheck={() => {}} className="rounded-lg" />
        </Specimen>
      </div>
      <Specimen label="With the claim's own rule" note="shown when the API sends the rule that fired; until then the status definition stands in" className={framed}>
        <EvidenceTrail
          claim={claim(2)}
          rule="A count of professional profiles is a signal of team size. It cannot settle a payroll figure"
          className="rounded-lg"
        />
      </Specimen>

      {/* Pipeline rail */}
      <Specimen
        label="Pipeline rail"
        note="the hatched end of a connector is the share of that stage's work that was not done"
        className={cn(framed, "bg-surface p-4")}
      >
        <PipelineRail stations={pipelineStations(pipelineBase)} />
      </Specimen>
      <Specimen
        label="A stage finishing while the page is open"
        note="the station fills and its connector draws. Opened cold, the same rail is simply drawn"
      >
        <div className="flex flex-col items-start gap-2">
          <div className={cn(framed, "w-full bg-surface p-4")}>
            <PipelineRail
              stations={pipelineStations(
                verifyDone
                  ? { ...pipelineBase, request: null }
                  : { ...pipelineBase, runs: [], live_run_kind: "verify", assessment: null, request: null },
              )}
            />
          </div>
          <Button size="sm" onClick={() => setVerifyDone((value) => !value)}>
            {verifyDone ? "Reset to verify running" : "Finish the verify run"}
          </Button>
        </div>
      </Specimen>
      <div className="grid gap-6 xl:grid-cols-2">
        <Specimen label="New case, added directly" className={cn(framed, "bg-surface p-4")}>
          <PipelineRail
            stations={pipelineStations({
              ...pipelineBase,
              thesis_id: null,
              runs: [],
              claim_counts: noCounts,
              assessment: null,
              request: null,
            })}
          />
        </Specimen>
        <Specimen label="Identity unresolved, read-only copy" note="nothing after Verify is filled" className={cn(framed, "bg-surface p-4")}>
          <PipelineRail
            readOnly
            stations={pipelineStations({
              ...pipelineBase,
              identity_confirmed: false,
              runs: [],
              claim_counts: noCounts,
              assessment: null,
              request: null,
            })}
          />
        </Specimen>
      </div>

      {/* Coverage map */}
      <Specimen
        label="Coverage map"
        note="four cell shapes and no heat scale. Pick a cell or a column head; in the product it filters the sources table"
      >
        <div className="flex flex-col gap-2">
          <CoverageMap model={coverage} selection={selection} onSelect={setSelection} />
          <p className="font-mono text-xs text-ink-secondary" aria-live="polite">
            {selection
              ? `Selected: ${selection.category ?? "every kind of claim"} · ${selection.reliability}`
              : "Nothing selected"}
          </p>
        </div>
      </Specimen>
      <div className="grid gap-6 xl:grid-cols-3">
        <Specimen label="Compact" note="for the Evidence sufficiency judgment" className={cn(framed, "bg-surface p-4")}>
          <CoverageMap model={coverage} variant="compact" />
        </Specimen>
        <Specimen label="Identity unresolved" note="every independent cell is hatched" className="xl:col-span-2">
          <CoverageMap model={coverageFromClaims(sample.claims.slice(0, 3), { identityOpen: true })} />
        </Specimen>
      </div>
      <Specimen label="No claims yet">
        <CoverageMap model={coverageFromClaims([])} />
      </Specimen>

      {/* Change timeline */}
      <Specimen
        label="Change timeline"
        note="the cause sits on the rail between two versions; what moved because of a claim hangs under it"
      >
        <div className="flex flex-col items-start gap-2">
          <ChangeTimeline
            className="w-full"
            entries={arrived ? [timelineV1, timelineV2, timelineV3] : [timelineV1, timelineV2]}
            current={arrived ? 3 : 2}
            highlightVersion={arrived ? 3 : null}
            onOpen={() => {}}
            unchangedFor={(version) =>
              sample.claims
                .filter((c) => (version === 2 ? c.number !== 5 : c.number !== 1))
                .map((c) => ({
                  number: c.number,
                  text: c.text,
                  status: c.status,
                  not_checked_reason: c.not_checked_reason,
                }))
            }
          />
          <Button size="sm" onClick={() => setArrived((value) => !value)}>
            {arrived ? "Remove version 3" : "Version 3 arrives"}
          </Button>
        </div>
      </Specimen>
      <Specimen label="One version only">
        <ChangeTimeline entries={[timelineV1]} current={1} />
      </Specimen>

      {/* Cost meter */}
      <Specimen label="Cost meter" note="one bar segmented by step, in run order" className={cn(framed, "bg-surface p-4")}>
        <CostMeter model={meterFromCaseCost(sample.cost)} />
      </Specimen>
      <Specimen
        label="Budget reached"
        note="the checks the budget left undone are hatched past the end of the track. Nothing turns red"
        className={cn(framed, "bg-surface p-4")}
      >
        <CostMeter
          model={meterFromCaseCost({
            ...sample.costReached,
            lines: [
              ...sample.cost.lines,
              { id: "l7", run_label: "Recheck", step_label: "Check customer claims", credits: 64, model_usd: null, at: "2026-11-22T11:44:00Z" },
            ],
          })}
          notCheckedHref="#ledger"
        />
      </Specimen>
      <Specimen
        label="During a run"
        note="the running step's segment is lighter and grows when the credit figure changes"
      >
        <div className="flex flex-col items-start gap-2">
          <div className={cn(framed, "w-full bg-surface p-4")}>
            <CostMeter model={meterFromRun(liveRun, 4)} />
          </div>
          <Button size="sm" onClick={() => setSpent((value) => (value >= 110 ? 38 : value + 12))}>
            {spent >= 110 ? "Reset" : "Spend 12 more credits"}
          </Button>
        </div>
      </Specimen>
      <div className="grid gap-6 xl:grid-cols-2">
        <Specimen label="Nothing spent" className={cn(framed, "bg-surface p-4")}>
          <CostMeter model={meterFromCaseCost({ credits_used: 0, credit_budget: 150, model_usd: 0, lines: [] })} />
        </Specimen>
        <Specimen label="Compact" note="case header and dashboard rows">
          <div className="flex flex-col items-start gap-2">
            <CostMeter model={meterFromCaseCost(sample.cost)} variant="compact" />
            <CostMeter model={meterFromCaseCost(sample.costReached)} variant="compact" />
          </div>
        </Specimen>
      </div>
    </section>
  );
}
