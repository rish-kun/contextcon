"use client";

import type { CaseDetail } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { staggerDelay } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { Fact } from "@/components/dealproof";
import { factEstimate, factEvidence } from "./adapt";
import { useCaseDetail } from "./case-context";
import { BlockedByIdentity, EmptyState, TabHeading } from "./parts";

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
 * Peers chosen on one shared basis, with one sourced observation each. Comparables
 * inform the reader and feed no score. When no fair comparison exists the tab says so
 * and shows nothing weaker in its place.
 */
export function ComparablesTab() {
  const detail = useCaseDetail();
  const { comparables } = detail;
  const blocked = detail.identity.state !== "confirmed";

  return (
    <div className="flex flex-col gap-6">
      <TabHeading
        title="Comparables"
        summary={
          !blocked && comparables.companies.length > 0
            ? `${plural(comparables.companies.length, "peer")} on the same basis · informational only, not scored`
            : undefined
        }
      />

      {blocked ? (
        <BlockedByIdentity what="A fair comparison starts from the confirmed company's activity, region and size." />
      ) : comparables.companies.length === 0 ? (
        <EmptyState title="No fair comparison found">
          {comparables.no_fair_comparison_reason
            ? `${comparables.no_fair_comparison_reason.replace(/\.$/, "")}. `
            : "Available records did not return peers matching the same activity, region and size band. "}
          DealProof does not substitute a weaker list.
        </EmptyState>
      ) : (
        <>
          <section aria-label="Basis of comparison" className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-ink">Basis of comparison</h3>
            <ComparisonBasis basis={comparables.basis} />
            <p className="text-xs text-ink-secondary">
              Every peer below shares all three. The size band is an estimate from
              professional profiles, not a payroll count
            </p>
          </section>

          <section aria-label="Peers" className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-ink">Peers</h3>
            <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
              {comparables.companies.map((peer, index) => (
                <li
                  key={peer.crustdata_company_id}
                  style={{ animationDelay: `${staggerDelay(index)}s` }}
                  className="grid gap-x-6 gap-y-1 px-4 py-3 text-dense md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
                >
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-ink">{peer.name}</span>
                    <span className="font-mono text-2xs text-ink-secondary">
                      company id {peer.crustdata_company_id}
                    </span>
                  </div>
                  <Fact
                    evidence={factEvidence(peer.observation)}
                    estimate={factEstimate(peer.observation)}
                    layout="stacked"
                  >
                    {peer.observation.value}
                  </Fact>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
