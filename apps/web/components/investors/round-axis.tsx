import type { InvestorEntryOut } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * One time axis shared by every investor in a shortlist, from the first year a
 * comparable round was found to the day of the search. Each round is a mark at its date,
 * so the two things the ranking counts, how many rounds and how recent, can be read
 * across rows. The axis stops at the search date: nothing after it is known.
 */
export interface RoundAxis {
  start: number;
  end: number;
  /** ISO date of the search, the right edge. */
  searchedOn: string;
  years: number[];
}

export function buildAxis(entries: InvestorEntryOut[], searchedAt: string): RoundAxis | null {
  const dates = entries.flatMap((e) => e.comparable_rounds.map((r) => Date.parse(r.date)));
  const end = Date.parse(searchedAt);
  const first = Math.min(...dates.filter(Number.isFinite));
  if (!Number.isFinite(first) || !Number.isFinite(end) || first >= end) return null;

  const firstYear = new Date(first).getUTCFullYear();
  const lastYear = new Date(end).getUTCFullYear();
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, i) => firstYear + i);
  return { start: Date.UTC(firstYear, 0, 1), end, searchedOn: searchedAt.slice(0, 10), years };
}

function position(axis: RoundAxis, time: number): number {
  const share = (time - axis.start) / (axis.end - axis.start);
  return Math.min(1, Math.max(0, share)) * 100;
}

const yearStart = (year: number) => Date.UTC(year, 0, 1);

/** The year labels, drawn once above the list. */
export function RoundAxisHeader({ axis, className }: { axis: RoundAxis; className?: string }) {
  // Past seven years the labels would touch, so every other one is named.
  const step = axis.years.length > 7 ? 2 : 1;
  return (
    <div aria-hidden className={cn("flex flex-col gap-1", className)}>
      <p className="flex items-baseline justify-between gap-3 text-xs text-ink-muted">
        <span>Dated comparable rounds</span>
        <span className="font-mono text-2xs">searched {formatDate(axis.searchedOn)}</span>
      </p>
      <div className="relative h-4">
        {axis.years.map((year, index) =>
          index % step === 0 ? (
            <span
              key={year}
              className="absolute top-0 font-mono text-2xs text-ink-muted"
              style={{ left: `${position(axis, yearStart(year))}%` }}
            >
              {year}
            </span>
          ) : null,
        )}
      </div>
    </div>
  );
}

/**
 * One investor's rounds on the shared axis. Decorative for assistive technology: the
 * same rounds are listed with their dates and sources right below.
 */
export function RoundStrip({
  axis,
  entry,
  className,
}: {
  axis: RoundAxis;
  entry: InvestorEntryOut;
  className?: string;
}) {
  return (
    <div aria-hidden className={cn("relative h-7", className)}>
      <span className="absolute inset-x-0 bottom-0 h-px bg-line-strong" />
      {axis.years.map((year) => (
        <span
          key={year}
          className="absolute bottom-0 h-1.5 w-px bg-line-strong"
          style={{ left: `${position(axis, yearStart(year))}%` }}
        />
      ))}
      <span className="absolute right-0 bottom-0 h-7 border-l border-dashed border-ink-muted" />
      {entry.comparable_rounds.map((round, index) => (
        <span
          key={`${round.company_id}-${round.date}-${index}`}
          className="absolute bottom-0 h-5 w-0.5 -translate-x-px rounded-t-xs bg-ink"
          style={{ left: `${position(axis, Date.parse(round.date))}%` }}
        />
      ))}
    </div>
  );
}
