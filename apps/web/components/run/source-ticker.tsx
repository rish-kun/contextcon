"use client";

import { motion } from "motion/react";
import { Fragment, useState } from "react";
import { formatDate, plural } from "@/lib/format";
import type { SourceRow } from "@/lib/run/activity-store";
import { rise, transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { SourceClassGlyph } from "@/components/dealproof/glyphs";
import { Panel, PanelHeader } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Favicon } from "./favicon";
import { clockTime, failedReadText, readAgo, reliabilityOf, sourceClassLabel, sourceName, sourceTitle } from "./wording";

/** Rows shown while a run is going; older ones fold under "n earlier". */
const VISIBLE = 6;

function RowBody({ row, nowMs, absolute }: { row: SourceRow; nowMs: number; absolute: boolean }) {
  const { source } = row;
  const failed = source.state !== "read";
  const title = sourceTitle(source);
  return (
    <>
      <span className="flex items-center gap-2">
        <Favicon domain={source.domain} sourceClass={source.source_class} muted={failed} />
        <span className={cn("min-w-0 flex-1 truncate", failed ? "text-ink-muted" : "text-ink")}>
          {sourceName(source)}
        </span>
        <span className="shrink-0 font-mono text-2xs text-ink-muted">
          {failed
            ? failedReadText(source)
            : absolute
              ? clockTime(row.at)
              : `read ${readAgo(row.at, nowMs)}`}
        </span>
      </span>
      {failed ? null : (
        <span className="flex items-baseline gap-2 pl-6 text-xs text-ink-secondary">
          <span className="min-w-0 flex-1 truncate">{title ?? row.detail ?? "No title"}</span>
          <span className="inline-flex shrink-0 items-center gap-1 text-ink-muted">
            <SourceClassGlyph reliability={reliabilityOf(source.source_class)} size={12} />
            {sourceClassLabel(source.source_class)} · {formatDate(source.as_of) ?? "no date"}
          </span>
        </span>
      )}
    </>
  );
}

const rowClass =
  "focus-inset flex w-full flex-col gap-0.5 px-4 py-2 text-left text-dense transition-colors hover:bg-surface-raised";

function TickerRow({
  row,
  nowMs,
  absolute,
  enter,
}: {
  row: SourceRow;
  nowMs: number;
  absolute: boolean;
  enter: boolean;
}) {
  const { source } = row;
  const body = <RowBody row={row} nowMs={nowMs} absolute={absolute} />;
  return (
    <motion.li
      layout="position"
      initial={enter ? { opacity: 0, y: rise } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={transition.slow}
      className="border-b border-line last:border-b-0"
    >
      {source.url ? (
        <a href={source.url} target="_blank" rel="noreferrer noopener" className={rowClass}>
          {body}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : source.type === "crustdata_record" ? (
        <Popover>
          <PopoverTrigger className={rowClass}>{body}</PopoverTrigger>
          <PopoverContent align="start" className="flex w-72 flex-col gap-1 text-dense">
            <p className="font-medium text-ink">{source.title ?? "Crustdata record"}</p>
            <p className="text-ink-secondary">
              {sourceClassLabel(source.source_class)} · as of {formatDate(source.as_of) ?? "unknown date"}
            </p>
            {row.detail ? <p className="text-ink-secondary">{row.detail}</p> : null}
            <p className="font-mono text-2xs text-ink-muted">Read {clockTime(row.at)} IST</p>
          </PopoverContent>
        </Popover>
      ) : (
        <div className={cn(rowClass, "hover:bg-transparent")}>{body}</div>
      )}
    </motion.li>
  );
}

export interface SourceTickerProps {
  /** Oldest first, as the store keeps them. */
  sources: SourceRow[];
  counts: { read: number; failed: number };
  nowMs: number;
  /** Rows at or below this `seq` are drawn settled. */
  settledSeq: number;
  /** The last burst shown at once, and how many rows it held. */
  skipped?: { count: number; seq: number } | null;
  /** True while the run is going: six rows, the rest folded. */
  live?: boolean;
  /** Clock times in place of "2 s ago", for the run log. */
  absolute?: boolean;
  /** Names the step the list is filtered to. */
  filterLabel?: string | null;
  onClearFilter?: () => void;
  /** `strip` is the horizontally scrolling row of chips for narrow screens. */
  form?: "panel" | "strip";
  className?: string;
}

/**
 * Every public page or Crustdata record the run read, newest on top, as it was read.
 * Pages that could not be read are listed too, with the reason: hiding them would
 * overstate what was read. Uploaded seller documents never appear here.
 */
export function SourceTicker({
  sources,
  counts,
  nowMs,
  settledSeq,
  skipped = null,
  live = false,
  absolute = false,
  filterLabel = null,
  onClearFilter,
  form = "panel",
  className,
}: SourceTickerProps) {
  const [showAll, setShowAll] = useState(false);
  const newestFirst = [...sources].reverse();
  const folded = live && !showAll ? Math.max(0, newestFirst.length - VISIBLE) : 0;
  const shown = folded > 0 ? newestFirst.slice(0, VISIBLE) : newestFirst;
  const meta =
    sources.length === 0
      ? undefined
      : `${counts.read} read${counts.failed > 0 ? ` · ${counts.failed} could not be read` : ""}`;

  if (form === "strip") {
    return (
      <section aria-label="Sources read" className={cn("flex flex-col gap-2", className)}>
        <p className="flex items-baseline gap-2 text-sm font-medium text-ink">
          Sources
          {meta ? <span className="font-mono text-xs font-normal text-ink-muted">{meta}</span> : null}
        </p>
        {sources.length === 0 ? (
          <p className="text-dense text-ink-muted">No pages read yet</p>
        ) : (
          <ul aria-label="Sources read, newest first" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
            {newestFirst.map((row) => (
              <li
                key={row.seq}
                className={cn(
                  "inline-flex shrink-0 items-center gap-2 rounded-md border border-line bg-surface px-2 py-1 text-xs",
                  row.source.state === "read" ? "text-ink" : "text-ink-muted",
                )}
              >
                <Favicon domain={row.source.domain} sourceClass={row.source.source_class} />
                {sourceName(row.source)}
                {row.source.state === "read" ? null : <span>· {failedReadText(row.source)}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  return (
    <Panel aria-label="Sources read" className={className}>
      <PanelHeader title="Sources" meta={meta} />
      {filterLabel ? (
        <p className="flex flex-wrap items-center gap-x-2 border-b border-line bg-accent-tint px-4 py-1 text-xs text-ink">
          Read by {filterLabel}
          {onClearFilter ? (
            <button
              type="button"
              onClick={onClearFilter}
              className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
            >
              Show all
            </button>
          ) : null}
        </p>
      ) : null}
      {sources.length === 0 ? (
        <p className="px-4 py-3 text-dense text-ink-muted">No pages read yet</p>
      ) : (
        <ul aria-label="Sources read, newest first" className="flex flex-col">
          {shown.map((row, index) => {
            // Where a burst was cut short, the rows below this one appeared together.
            const next = shown[index + 1];
            const burst =
              skipped && row.seq > skipped.seq && next !== undefined && next.seq <= skipped.seq
                ? skipped
                : null;
            return (
              <Fragment key={row.seq}>
                <TickerRow row={row} nowMs={nowMs} absolute={absolute} enter={row.seq > settledSeq} />
                {burst ? (
                  <motion.li
                    layout="position"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={transition.slow}
                    className="border-b border-line px-4 py-1 font-mono text-2xs text-ink-muted"
                  >
                    + {burst.count} more, shown at once
                  </motion.li>
                ) : null}
              </Fragment>
            );
          })}
        </ul>
      )}
      {folded > 0 || (showAll && live && newestFirst.length > VISIBLE) ? (
        <button
          type="button"
          aria-expanded={showAll}
          onClick={() => setShowAll((value) => !value)}
          className="focus-inset flex h-9 w-full items-center justify-between gap-2 rounded-b-lg border-t border-line px-4 text-xs text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink"
        >
          <span className="font-mono">{showAll ? plural(newestFirst.length, "source") : `${folded} earlier`}</span>
          {showAll ? "Show fewer" : "Show all"}
        </button>
      ) : null}
    </Panel>
  );
}
