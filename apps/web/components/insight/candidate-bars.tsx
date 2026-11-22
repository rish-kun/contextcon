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

const head = "px-3 py-2 text-xs font-medium whitespace-nowrap text-ink-secondary";

/**
 * Candidates as ranked bars: one row each, fit and assessable share as two aligned bars
 * on their own 0 to 100 scales, and the size estimate as a figure. Bars on one baseline
 * compare more exactly than areas, which is why this is not a treemap.
 *
 * Fit and assessable are never merged. The assessable bar ends in a hatched remainder,
 * the part of the thesis that could not be assessed, so a high fit on thin coverage does
 * not read like a high fit on full coverage. A candidate with no fit says so in words.
 */
export function CandidateBars({
  rows,
  caption,
  className,
}: {
  rows: CandidateBar[];
  caption: string;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}>
      <table className="w-full table-fixed border-collapse text-left text-dense text-ink">
        <caption className="sr-only">{caption}</caption>
        <colgroup>
          <col />
          <col className="w-28 sm:w-32" />
          <col className="w-16 sm:w-32" />
          <col className="w-16 max-sm:hidden" />
        </colgroup>
        <thead className="bg-surface-sunken">
          <tr>
            <th scope="col" className={head}>
              Company
            </th>
            <th scope="col" className={head}>
              Fit
            </th>
            <th scope="col" className={head}>
              Assessable
            </th>
            <th scope="col" className={cn(head, "text-right max-sm:hidden")}>
              People
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className="border-b border-line transition-colors last:border-b-0 hover:bg-surface-raised"
            >
              <th scope="row" className="px-3 py-2 font-normal">
                <span className="flex min-w-0 items-baseline gap-2">
                  {row.rank !== null ? (
                    <span className="w-5 shrink-0 font-mono text-xs text-ink-muted">
                      {String(row.rank).padStart(2, "0")}
                    </span>
                  ) : null}
                  {row.href ? (
                    <a
                      href={row.href}
                      className="min-w-0 rounded-xs break-words text-ink underline decoration-line-strong underline-offset-2 transition-colors hover:text-accent"
                    >
                      {row.name}
                    </a>
                  ) : (
                    <span className="min-w-0 break-words">{row.name}</span>
                  )}
                </span>
              </th>
              <td className="px-3 py-2">
                {row.fit === null ? (
                  <span className="hatch-dense rounded-xs border border-dashed border-not-checked-line px-1 text-xs text-not-checked">
                    Not scored
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <span className="w-7 shrink-0 text-right font-mono text-xs font-medium">{row.fit}</span>
                    <span aria-hidden className="h-2 flex-1 bg-surface-sunken">
                      <span
                        className="block h-full min-w-0.5 rounded-r-xs bg-ink"
                        style={{ width: `${row.fit}%` }}
                      />
                    </span>
                  </span>
                )}
              </td>
              <td className="px-3 py-2">
                <span className="flex items-center gap-2">
                  <span className="w-9 shrink-0 text-right font-mono text-xs font-medium">
                    {row.assessablePct}%
                  </span>
                  <span aria-hidden className="flex h-2 flex-1 gap-0.5 max-sm:hidden">
                    {row.assessablePct > 0 ? (
                      <span className="h-full bg-ink-muted" style={{ width: `${row.assessablePct}%` }} />
                    ) : null}
                    {row.assessablePct < 100 ? (
                      <span className="hatch-dense h-full flex-1 border border-dashed border-not-checked-line" />
                    ) : null}
                  </span>
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs max-sm:hidden">
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
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
 * a missing location is seen and never folded into a place.
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
                  <span aria-hidden className="h-2 flex-1">
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
