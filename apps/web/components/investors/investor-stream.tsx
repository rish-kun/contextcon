"use client";

import { motion } from "motion/react";
import { formatDate, plural } from "@/lib/format";
import type { InvestorRow, RoundRow } from "@/lib/run/activity-store";
import { duration, ease, rise, transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { NumberTween } from "@/components/dealproof/number-tween";
import type { FindingsContext } from "@/components/run/run-view";
import { Panel, PanelHeader } from "@/components/ui/card";

/** How many comparable companies are named before "+N". */
const NAMES_SHOWN = 8;

interface Axis {
  start: number;
  end: number;
  years: number[];
}

/** One time axis for every investor, from the first dated round read to the clock of the run. */
function buildAxis(rounds: RoundRow[], nowMs: number): Axis | null {
  const times = rounds.map((round) => Date.parse(round.date ?? "")).filter(Number.isFinite);
  if (times.length === 0) return null;
  const firstYear = new Date(Math.min(...times)).getUTCFullYear();
  const lastYear = new Date(nowMs).getUTCFullYear();
  if (lastYear < firstYear) return null;
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, index) => firstYear + index);
  return { start: Date.UTC(firstYear, 0, 1), end: Math.max(nowMs, Date.UTC(firstYear, 0, 2)), years };
}

const share = (axis: Axis, time: number) =>
  `${Math.min(1, Math.max(0, (time - axis.start) / (axis.end - axis.start))) * 100}%`;

/** `series_a` or "Series A" → "Series A". */
function roundName(value: string | null | undefined): string {
  if (!value) return "Round";
  const words = value.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function roundLine(round: RoundRow): string {
  return [round.company ?? "A company", roundName(round.round), formatDate(round.date) ?? "no date"].join(" · ");
}

function StreamRow({
  investor,
  axis,
  ranked,
  isNew,
}: {
  investor: InvestorRow;
  axis: Axis | null;
  ranked: boolean;
  isNew: (seq: number) => boolean;
}) {
  const dated = investor.rounds.filter((round) => round.date);
  // The newest round by date; an undated round is only shown when nothing else is.
  const newest = [...dated].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? "")).at(-1) ?? investor.rounds.at(-1);
  const more = investor.rounds.length - 1;
  return (
    <div className="flex flex-col gap-2 px-4 py-3 text-dense">
      <p className="flex items-baseline justify-between gap-3">
        <span className="flex min-w-0 items-baseline gap-2">
          {ranked && investor.rank != null ? (
            <span className="font-mono text-xs text-ink-muted">{investor.rank}</span>
          ) : null}
          <span className="truncate font-medium text-ink">{investor.name}</span>
        </span>
        <span className="shrink-0 font-mono text-xs text-ink-secondary">
          <NumberTween value={investor.rounds.length} /> {investor.rounds.length === 1 ? "round" : "rounds"}
        </span>
      </p>
      {axis && dated.length > 0 ? (
        <div aria-hidden className="relative h-5">
          <span className="absolute inset-x-0 bottom-0 h-px bg-line-strong" />
          {axis.years.map((year) => (
            <span
              key={year}
              className="absolute bottom-0 h-1.5 w-px bg-line-strong"
              style={{ left: share(axis, Date.UTC(year, 0, 1)) }}
            />
          ))}
          {dated.map((round) => (
            <motion.span
              key={round.id}
              initial={isNew(round.seq) ? { opacity: 0, scaleY: 0.4 } : false}
              animate={{ opacity: 1, scaleY: 1 }}
              transition={{ duration: duration.base, ease }}
              className="absolute bottom-0 h-4 w-0.5 origin-bottom -translate-x-px rounded-t-xs bg-ink"
              style={{ left: share(axis, Date.parse(round.date ?? "")) }}
            />
          ))}
        </div>
      ) : null}
      {newest ? (
        <p className="text-xs text-ink-secondary">
          {roundLine(newest)}
          {more > 0 ? <span className="font-mono text-ink-muted"> +{more}</span> : null}
        </p>
      ) : (
        <p className="text-xs text-ink-muted">No round read yet</p>
      )}
    </div>
  );
}

/**
 * The Investor search findings. First the comparable companies that raised money, as a
 * wrapping line of names. Then the investors behind them, grouped from each dated round
 * as it is read.
 *
 * While rounds are still arriving the list is "Investors so far", in the order investors
 * were first seen, so it does not reshuffle under the reader. When the rank step finishes
 * the rows move to rank order once and the header becomes "Investor shortlist". A round
 * with no date is counted and draws no mark; an investor backed only by undated rounds is
 * listed apart, not ranked. Only organisation names and round facts are shown.
 */
export function InvestorStream({ context }: { context: FindingsContext }) {
  const { view, isNew, nowMs } = context;
  const companies = view.companies.rows;
  const found = view.companies.counts.found ?? companies.length;
  const counts = view.rounds.counts;
  const rounds = view.rounds.rows;
  const roundsTotal = counts.rounds ?? rounds.length;
  const dated = counts.rounds_dated ?? rounds.filter((round) => round.date).length;
  const ranked = view.investorsRankedSeq !== null && context.stepSettled(view.investorsRankedStep);
  const axis = buildAxis(rounds, nowMs);

  const bySeen = [...view.investors].sort((a, b) => a.firstSeq - b.firstSeq);
  const listed = ranked
    ? bySeen.filter((investor) => investor.ranked).sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity))
    : bySeen;
  const unranked = ranked ? bySeen.filter((investor) => !investor.ranked) : [];
  const named = counts.investors ?? view.investors.length;

  return (
    <div className="flex flex-col gap-4">
      <Panel aria-label="Comparable companies that raised money">
        <PanelHeader title="Comparable companies that raised" meta={found > 0 ? found : undefined} />
        <p className="px-4 py-3 text-dense text-ink">
          {companies.length === 0 ? (
            <span className="text-ink-muted">No comparable company has been returned yet</span>
          ) : (
            <>
              {companies.slice(0, NAMES_SHOWN).map((company, index) => (
                <motion.span
                  key={company.id}
                  initial={isNew(company.firstSeq) ? { opacity: 0 } : false}
                  animate={{ opacity: 1 }}
                  transition={{ duration: duration.slow, ease, delay: isNew(company.firstSeq) ? company.slot * 0.06 : 0 }}
                >
                  {index > 0 ? <span className="text-ink-muted"> · </span> : null}
                  {company.name ?? "Unnamed company"}
                </motion.span>
              ))}
              {found > Math.min(companies.length, NAMES_SHOWN) ? (
                <span className="font-mono text-xs text-ink-muted">
                  {" "}
                  +{found - Math.min(companies.length, NAMES_SHOWN)}
                </span>
              ) : null}
            </>
          )}
        </p>
      </Panel>

      <Panel aria-label={ranked ? "Investor shortlist" : "Investors so far"}>
        <PanelHeader
          title={ranked ? "Investor shortlist" : "Investors so far"}
          meta={
            named > 0 || roundsTotal > 0
              ? `${named} named · ${dated === roundsTotal ? plural(dated, "dated round") : `${dated} of ${roundsTotal} rounds with a date`}`
              : undefined
          }
        />
        {listed.length === 0 ? (
          <p className="px-4 py-3 text-dense text-ink-muted">No funding round has been read yet</p>
        ) : (
          <ol className="flex flex-col">
            {listed.map((investor) => (
              <motion.li
                key={investor.key}
                layout="position"
                initial={isNew(investor.firstSeq) ? { opacity: 0, y: rise } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={transition.slow}
                className="border-b border-line last:border-b-0"
              >
                <StreamRow investor={investor} axis={axis} ranked={ranked} isNew={isNew} />
              </motion.li>
            ))}
          </ol>
        )}
        {axis ? (
          <p className="flex justify-between border-t border-line px-4 py-2 font-mono text-2xs text-ink-muted">
            <span>{axis.years[0]}</span>
            <span>{formatDate(new Date(axis.end).toISOString().slice(0, 10))}</span>
          </p>
        ) : null}
      </Panel>

      {unranked.length > 0 ? (
        <Panel aria-label="Not ranked">
          <PanelHeader title="Not ranked · no dated round" meta={unranked.length} />
          <ul className={cn("flex flex-col")}>
            {unranked.map((investor) => (
              <li key={investor.key} className="border-b border-line last:border-b-0">
                <StreamRow investor={investor} axis={null} ranked={false} isNew={isNew} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
