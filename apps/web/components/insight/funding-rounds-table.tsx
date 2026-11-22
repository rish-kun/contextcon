import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** One dated funding round as a table row. `source` is its source chip and is required. */
export interface FundingRow {
  id: string;
  /** ISO date of the round. Null when the record carries none. */
  date: string | null;
  /** "Series A". Null when the record carries no round type. */
  round: string | null;
  amountUsd: number | null;
  investors?: string[];
  /** The company that raised it, for a table that lists rounds across companies. */
  company?: string;
  /** The source chip for this row, with the round's own date as its as-of date. */
  source: React.ReactNode;
}

/** `$6.0M`, `$750K`. One precision per unit, so the column lines up. */
export function formatAmountUsd(amount: number): string {
  if (amount >= 1_000_000_000) return `$${(amount / 1_000_000_000).toFixed(1)}B`;
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${Math.round(amount / 1_000)}K`;
  return `$${Math.round(amount)}`;
}

const cell = "px-3 py-2 align-middle max-sm:block max-sm:p-0";
const head = "h-8 px-3 text-xs font-medium whitespace-nowrap text-ink-secondary";

/**
 * Funding rounds as a table, newest first, with the amount drawn as a bar beside its
 * figure so sizes compare down the column. Bars share one scale: the largest amount in
 * this table. A round with no recorded amount says so and draws no bar; it is never
 * shown as zero. Every row ends in its own source.
 *
 * Under 640px each round stacks into a small block; the column headings stay available
 * to assistive technology.
 */
export function FundingRoundsTable({
  rows,
  caption,
  showCompany = false,
  showInvestors = true,
  className,
}: {
  rows: FundingRow[];
  /** What the table lists, read out with it: "Funding rounds on record for Harbourline". */
  caption: string;
  showCompany?: boolean;
  showInvestors?: boolean;
  className?: string;
}) {
  const sorted = [...rows].sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));
  const largest = Math.max(0, ...sorted.map((row) => row.amountUsd ?? 0));

  return (
    <div className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}>
      <table className="w-full border-collapse text-left text-dense text-ink max-sm:block">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-surface-sunken max-sm:sr-only">
          <tr>
            {showCompany ? (
              <th scope="col" className={head}>
                Company
              </th>
            ) : null}
            <th scope="col" className={head}>
              Round
            </th>
            <th scope="col" className={head}>
              Date
            </th>
            <th scope="col" className={cn(head, "w-2/5")}>
              Amount
            </th>
            {showInvestors ? (
              <th scope="col" className={head}>
                Investors
              </th>
            ) : null}
            <th scope="col" className={head}>
              Source
            </th>
          </tr>
        </thead>
        <tbody className="max-sm:block">
          {sorted.map((row) => (
            <tr
              key={row.id}
              className="border-b border-line transition-colors last:border-b-0 hover:bg-surface-raised max-sm:flex max-sm:flex-col max-sm:gap-1 max-sm:px-3 max-sm:py-3"
            >
              {showCompany ? (
                <td className={cn(cell, "font-medium")}>{row.company ?? "Company not recorded"}</td>
              ) : null}
              <td className={cn(cell, row.round ? "text-ink" : "text-ink-muted")}>
                {row.round ?? "Round type not recorded"}
              </td>
              <td className={cn(cell, "font-mono text-xs whitespace-nowrap", !row.date && "text-ink-muted")}>
                {formatDate(row.date) ?? "date unknown"}
              </td>
              <td className={cell}>
                {row.amountUsd == null ? (
                  <span className="text-ink-muted">Amount not recorded</span>
                ) : (
                  <span className="flex items-center gap-3">
                    <span className="w-14 shrink-0 text-right font-mono text-xs">
                      {formatAmountUsd(row.amountUsd)}
                    </span>
                    <span aria-hidden className="h-2 min-w-16 flex-1 bg-surface-sunken">
                      <span
                        className="block h-full min-w-0.5 rounded-r-xs bg-ink"
                        style={{ width: `${largest > 0 ? (row.amountUsd / largest) * 100 : 0}%` }}
                      />
                    </span>
                  </span>
                )}
              </td>
              {showInvestors ? (
                <td className={cn(cell, "text-ink-secondary")}>
                  {row.investors && row.investors.length > 0 ? (
                    row.investors.join(", ")
                  ) : (
                    <span className="text-ink-muted">Not named in the record</span>
                  )}
                </td>
              ) : null}
              <td className={cn(cell, "max-sm:pt-1")}>{row.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
