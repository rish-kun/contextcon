import type { EstimateMeta, Evidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EstimateLabel, SourceLine } from "@/components/dealproof";

/**
 * A row of figures at the head of a page or panel. Tiles share hairlines instead of each
 * sitting in its own card, so the row reads as one band.
 */
export function KpiRow({
  children,
  label,
  className,
}: {
  children: React.ReactNode;
  /** Names the group for assistive technology: "Shortlist summary". */
  label: string;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}>
      <dl
        aria-label={label}
        className="-mr-px -mb-px grid grid-cols-2 sm:grid-cols-[repeat(auto-fit,minmax(11.5rem,1fr))]"
      >
        {children}
      </dl>
    </div>
  );
}

/**
 * One figure: a label, the value, what it is (a recorded fact, an Estimate or a Signal),
 * and where it came from. A sourced fact passes `evidence` and ends in its source chip
 * and as-of date. A figure DealProof worked out from the page's own rows passes `note`
 * saying so. A tile with neither is a bug in the caller.
 *
 * `missing` draws the tile hatched with the reason in words, for a figure the record
 * does not hold. It keeps its place in the row so the gap is seen.
 */
export function StatTile({
  label,
  value,
  unit,
  estimate,
  evidence,
  note,
  trend,
  missing,
  className,
}: {
  label: string;
  /** The figure, without a tilde. */
  value?: React.ReactNode;
  /** A short word after the figure: "people", "open roles". */
  unit?: string;
  estimate?: EstimateMeta | null;
  evidence?: Evidence[];
  /** How a computed figure was worked out, or what it compares to. */
  note?: React.ReactNode;
  /** A sparkline, drawn to the right of the figure. Only for a real series. */
  trend?: React.ReactNode;
  /** Why there is no figure: "Not on public record". Replaces the value. */
  missing?: string;
  className?: string;
}) {
  const figure = (
    <>
      <span className="text-xl font-semibold text-ink">{value}</span>
      {unit ? <span className="text-dense font-normal text-ink-secondary"> {unit}</span> : null}
    </>
  );

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-1 border-r border-b border-line px-4 py-3",
        missing && "hatch",
        className,
      )}
    >
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="flex min-w-0 flex-col items-start gap-1">
        {missing ? (
          <span className="rounded-xs bg-not-checked-tint px-1 text-dense font-medium text-not-checked">
            {missing}
          </span>
        ) : (
          <span className="flex w-full items-end justify-between gap-3">
            <span className="min-w-0">
              {estimate ? (
                <EstimateLabel kind={estimate.kind} basis={estimate.basis}>
                  {figure}
                </EstimateLabel>
              ) : (
                figure
              )}
            </span>
            {trend}
          </span>
        )}
        {note ? <span className="text-xs text-ink-secondary">{note}</span> : null}
        {evidence ? <SourceLine evidence={evidence} max={1} /> : null}
      </dd>
    </div>
  );
}
