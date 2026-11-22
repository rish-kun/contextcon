"use client";

import type { CaseDetail } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Fact } from "@/components/dealproof";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui";
import { factEstimate, factEvidence } from "./adapt";
import { useCaseDetail } from "./case-context";
import { BlockedByIdentity, TabEmpty, TabSection, TabStack } from "./parts";

type Basis = CaseDetail["comparables"]["basis"];

/** The three things every peer shares with the company. An unset one is said to be unset. */
export function ComparisonBasis({ basis, className }: { basis: Basis; className?: string }) {
  const cells: [string, string | null][] = [
    ["Activity", basis.industry],
    ["Region", basis.country],
    ["Size band", basis.headcount_band ? `${basis.headcount_band} people` : null],
  ];
  return (
    <dl
      className={cn(
        "grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3",
        className,
      )}
    >
      {cells.map(([label, value]) => (
        <div key={label} className="flex flex-col gap-1 bg-surface px-4 py-3">
          <dt className="text-xs text-ink-muted">{label}</dt>
          <dd className={value ? "font-mono text-sm font-medium text-ink" : "text-dense text-ink-muted"}>
            {value ?? "Not set"}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Peers chosen on one shared basis, with one sourced observation each, as a plain table.
 * Comparables inform the reader and feed no score. When no fair comparison exists the tab
 * says so and shows nothing weaker in its place.
 */
export function ComparablesTab() {
  const detail = useCaseDetail();
  const { comparables } = detail;

  if (detail.identity.state !== "confirmed") {
    return <BlockedByIdentity what="Peers are chosen from the confirmed company's activity, region and size" />;
  }
  if (comparables.companies.length === 0) {
    return (
      <TabEmpty title="No fair comparison found">
        {comparables.no_fair_comparison_reason
          ? comparables.no_fair_comparison_reason.replace(/\.$/, "")
          : "No peer matched the same activity, region and size band"}
        . A weaker list is not shown in its place
      </TabEmpty>
    );
  }

  return (
    <TabStack>
      <TabSection
        title="Basis"
        why={<p>Every peer shares all three. The size band is an estimate from professional profiles, not a payroll count. Comparables are informational and feed no score.</p>}
        flush
      >
        <ComparisonBasis basis={comparables.basis} className="rounded-none border-0" />
      </TabSection>

      <TabSection title="Peers" meta={`${comparables.companies.length} · not scored`} flush>
        <Table density="two-line" flush>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Company</TableHead>
              <TableHead>Observation</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {comparables.companies.map((peer) => (
              <TableRow key={peer.crustdata_company_id}>
                <TableCell className="align-top">
                  <span className="flex flex-col">
                    <span className="font-medium text-ink">{peer.name}</span>
                    <span className="font-mono text-2xs text-ink-muted">id {peer.crustdata_company_id}</span>
                  </span>
                </TableCell>
                <TableCell className="align-top">
                  <Fact evidence={factEvidence(peer.observation)} estimate={factEstimate(peer.observation)} layout="stacked">
                    {peer.observation.value}
                  </Fact>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TabSection>
    </TabStack>
  );
}
