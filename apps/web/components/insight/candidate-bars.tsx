import { cn } from "@/lib/utils";

/** One candidate on the overview: its fit, how much of the thesis could be assessed, its size. */
export interface CandidateBar {
  id: string;
  rank: number | null;
  name: string;
  /** In-page link to the candidate's card. */
  href?: string;
  /** 0 to 100. Null when nothing could be assessed, so no fit is scored. */
  fit: number | null;
  /** Share of criteria that could be assessed, 0 to 100. */
  assessablePct: number;
  /** Profile-based estimate of team size. Null when the source returned none. */
  headcount: number | null;
}

const GRID =
  "grid grid-cols-[minmax(0,1fr)_3rem_3.5rem] items-center gap-x-3 px-4 sm:grid-cols-[minmax(11rem,1fr)_9rem_9rem_4rem]";

/**
 * Candidates as ranked bars: one row each, fit and assessable share as two aligned bars
 * on their own 0 to 100 scales, and the size estimate as a figure. Bars on one baseline
 * compare more exactly than areas, which is why this is not a treemap.
 *
 * Fit and assessable are never merged. The assessable bar ends in a hatched remainder,
 * the part of the thesis that could not be assessed, so a high fit on thin coverage does
 * not read like a high fit on full coverage. A candidate with no fit says so in words.
 * When every fit is the same, pass `fitTied`: the fit bars are left out, because a column
 * of identical bars would look like a finding.
 *
 * A name keeps at least 11rem and ends in an ellipsis; it never wraps by letter. Under
 * 640px the bars and the size column drop away and the figures stay.
 */
export function CandidateBars({
  rows,
  caption,
  fitTied = false,
  className,
}: {
  rows: CandidateBar[];
  caption: string;
  /** Every scored candidate has the same fit, so the fit bars carry nothing. */
  fitTied?: boolean;
  className?: string;
}) {
  const head = "text-xs font-medium whitespace-nowrap text-ink-secondary";
  return (
    <div
      role="table"
      aria-label={caption}
      className={cn("overflow-hidden rounded-lg border border-line bg-surface text-dense text-ink", className)}
    >
      <div role="row" className={cn(GRID, "h-8 bg-surface-sunken")}>
        <span role="columnheader" className={head}>
          Company
        </span>
        <span role="columnheader" className={head}>
          Fit
        </span>
        <span role="columnheader" className={head}>
          Assessable
        </span>
        <span role="columnheader" className={cn(head, "text-right max-sm:hidden")}>
          People
        </span>
      </div>
      {rows.map((row) => (
        <div
          key={row.id}
          role="row"
          className={cn(GRID, "min-h-9 border-t border-line py-1.5 transition-colors hover:bg-surface-raised")}
        >
          <span role="rowheader" className="flex min-w-0 items-baseline gap-2">
            {row.rank !== null ? (
              <span className="w-5 shrink-0 font-mono text-xs text-ink-muted">
                {String(row.rank).padStart(2, "0")}
              </span>
            ) : null}
            {row.href ? (
              <a
                href={row.href}
                title={row.name}
                className="min-w-0 truncate rounded-xs text-ink underline decoration-line-strong underline-offset-2 transition-colors hover:text-accent"
              >
                {row.name}
              </a>
            ) : (
              <span title={row.name} className="min-w-0 truncate">
                {row.name}
              </span>
            )}
          </span>
          <span role="cell" className="flex min-w-0 items-center gap-2">
            {row.fit === null ? (
              <span className="truncate rounded-xs border border-dashed border-not-checked-line bg-not-checked-tint px-1 text-xs text-not-checked">
                <span className="sm:hidden">–</span>
                <span className="max-sm:sr-only">Not scored</span>
              </span>
            ) : (
              <>
                <span className="w-7 shrink-0 text-right font-mono text-xs font-medium">{row.fit}</span>
                {fitTied ? null : (
                  <span aria-hidden className="h-2 flex-1 bg-surface-sunken max-sm:hidden">
                    <span className="block h-full min-w-0.5 rounded-r-xs bg-ink" style={{ width: `${row.fit}%` }} />
                  </span>
                )}
              </>
            )}
          </span>
          <span role="cell" className="flex min-w-0 items-center gap-2">
            <span className="w-9 shrink-0 text-right font-mono text-xs font-medium">{row.assessablePct}%</span>
            <span aria-hidden className="flex h-2 flex-1 gap-0.5 max-sm:hidden">
              {row.assessablePct > 0 ? (
                <span className="h-full bg-ink-muted" style={{ width: `${row.assessablePct}%` }} />
              ) : null}
              {row.assessablePct < 100 ? (
                <span className="hatch-dense h-full flex-1 border border-dashed border-not-checked-line" />
              ) : null}
            </span>
          </span>
          <span role="cell" className="text-right font-mono text-xs max-sm:hidden">
            {row.headcount === null ? (
              <span className="text-ink-muted">
                <span aria-hidden>–</span>
                <span className="sr-only">No estimate returned</span>
              </span>
            ) : (
              <span className="underline-estimate" title="Estimate · from professional profiles, not a payroll count">
                ~{row.headcount.toLocaleString("en-US")}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

/** One group on a count chart: a place, how many candidates, and which. */
export interface CountBar {
  label: string;
  count: number;
  /** The names behind the count, shown under the label. */
  names?: string[];
  /** Draws the row hatched: these are the candidates the source returned nothing for. */
  missing?: boolean;
}

/**
 * Counts by group as ranked bars, largest first, on one scale. Used for where the
 * candidates are headquartered. A group for "not returned" is hatched and kept last, so
 * a missing location is seen and never folded into a place. When every group has the same
 * count the bars are not drawn, because equal bars say nothing.
 */
export function CountBars({
  rows,
  caption,
  unit,
  className,
}: {
  rows: CountBar[];
  caption: string;
  /** Singular noun for the count, for assistive technology: "company". */
  unit: string;
  className?: string;
}) {
  const sorted = [...rows].sort(
    (a, b) => Number(Boolean(a.missing)) - Number(Boolean(b.missing)) || b.count - a.count || a.label.localeCompare(b.label),
  );
  const largest = Math.max(1, ...sorted.map((row) => row.count));
  // A distribution is drawn only when it carries one: equal counts would be a wall of full bars.
  const flat = new Set(sorted.filter((row) => !row.missing).map((row) => row.count)).size <= 1;

  return (
    <div className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}>
      <table className="w-full table-fixed border-collapse text-left text-dense text-ink">
        <caption className="sr-only">{caption}</caption>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.label} className="border-b border-line last:border-b-0">
              <th scope="row" className="w-2/5 px-3 py-2 align-top font-normal">
                <span className={cn("block truncate", row.missing && "text-not-checked")}>{row.label}</span>
                {row.names && row.names.length > 0 ? (
                  <span className="block truncate text-xs text-ink-muted" title={row.names.join(", ")}>
                    {row.names.join(", ")}
                  </span>
                ) : null}
              </th>
              <td className="px-3 py-2 align-top">
                <span className="flex h-5 items-center gap-2">
                  <span aria-hidden className={cn("h-2 flex-1", flat && "invisible")}>
                    <span
                      className={cn(
                        "block h-full min-w-0.5",
                        row.missing
                          ? "hatch-dense border border-dashed border-not-checked-line"
                          : "rounded-r-xs bg-ink",
                      )}
                      style={{ width: `${(row.count / largest) * 100}%` }}
                    />
                  </span>
                  <span className="w-6 shrink-0 text-right font-mono text-xs font-medium">
                    {row.count}
                    <span className="sr-only"> {row.count === 1 ? unit : `${unit}s`}</span>
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
