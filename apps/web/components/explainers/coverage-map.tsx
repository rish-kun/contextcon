"use client";

import { Fragment } from "react";
import { formatAsOf, plural } from "@/lib/format";
import { NOT_CHECKED_REASON_LABEL, RELIABILITY_LABEL } from "@/lib/labels";
import type { ReliabilityClass } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StatusCounts } from "@/components/dealproof/status-mark";
import { Tooltip } from "@/components/ui/tooltip";
import {
  CLASS_SHORT_LABEL,
  coverageThinSpots,
  SELLER_CLASSES,
  type CoverageCell,
  type CoverageModel,
  type CoverageRow,
} from "./derive";

/** What the reader picked: a whole source class (a column head) or one cell. */
export interface CoverageSelection {
  reliability: ReliabilityClass;
  /** Null when a column head was picked. */
  category: string | null;
}

const isSeller = (reliability: ReliabilityClass) =>
  (SELLER_CLASSES as readonly ReliabilityClass[]).includes(reliability);

/**
 * The four cell shapes, plus the open square for the seller's own material. Shape carries
 * the state, so the map reads without colour and in print. There is no shading by
 * strength: a cell is filled by a dated fact or it is not.
 */
function CellMark({ state, size = 12 }: { state: CoverageCell["state"]; size?: number }) {
  const box = { width: size, height: size };
  switch (state) {
    case "found":
      return <span style={box} className="inline-block shrink-0 rounded-[2px] bg-ink" />;
    case "seller":
      return <span style={box} className="inline-block shrink-0 rounded-[2px] border-[1.5px] border-ink-secondary" />;
    case "searched_empty":
      return <span style={box} className="inline-block shrink-0 rounded-[2px] border border-dashed border-not-checked" />;
    case "not_searched":
      return (
        <span
          style={{ width: size + 8, height: size }}
          className="hatch-dense inline-block shrink-0 rounded-[2px] border border-dashed border-not-checked-line"
        />
      );
    case "none":
      return (
        <span style={box} className="inline-flex shrink-0 items-center justify-center">
          <span className="size-1 rounded-full bg-ink-muted/60" />
        </span>
      );
  }
}

function cellWords(row: CoverageRow, cell: CoverageCell): string {
  const klass = RELIABILITY_LABEL[cell.reliability];
  switch (cell.state) {
    case "found":
      return `${row.category} · ${klass}: ${plural(cell.count, "dated fact")}, most recent ${formatAsOf(cell.latest_as_of)}. Claim ${cell.claim_numbers.join(", ")}`;
    case "seller":
      return `${row.category} · ${klass}: where ${plural(cell.count, "statement")} came from. The seller's own material is not independent evidence`;
    case "searched_empty":
      return `${row.category} · ${klass}: searched, nothing found`;
    case "not_searched":
      return `${row.category} · ${klass}: not searched${
        row.not_searched_reason && row.not_searched_reason !== "mixed"
          ? ` · ${NOT_CHECKED_REASON_LABEL[row.not_searched_reason]}`
          : ""
      }`;
    case "none":
      return `${row.category} · ${klass}: no fact from this class`;
  }
}

const LEGEND: { state: CoverageCell["state"]; label: string }[] = [
  { state: "found", label: "dated fact found, with count" },
  { state: "searched_empty", label: "searched, nothing found" },
  { state: "not_searched", label: "not searched" },
  { state: "none", label: "no fact from this class" },
  { state: "seller", label: "seller's own material, not independent" },
];

/**
 * What the evidence for each kind of claim rests on: claim category by source class,
 * strongest independent source first, the seller's own material set apart at the right.
 * It shows "the right source for the right question" as a picture, and where the case is
 * thin. A cell is never inferred: "searched, nothing found" is drawn only from a recorded
 * empty search.
 *
 * Selecting a cell or a column head hands the selection to `onSelect`, so the map can
 * filter the table beneath it.
 */
export function CoverageMap({
  model,
  variant = "full",
  selection = null,
  onSelect,
  className,
}: {
  model: CoverageModel;
  /** compact: one row per category, small cells, no column heads, for the judgment panel. */
  variant?: "full" | "compact";
  selection?: CoverageSelection | null;
  onSelect?: (selection: CoverageSelection | null) => void;
  className?: string;
}) {
  if (model.rows.length === 0) {
    return (
      <p className={cn("rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-secondary", className)}>
        No claims to cover yet. Add seller claims or upload a document
      </p>
    );
  }

  const independent = model.columns.filter((c) => !isSeller(c));
  const seller = model.columns.filter(isSeller);
  const waiting = model.rows.every((row) => row.not_searched_reason === "identity_unresolved");

  if (variant === "compact") {
    const spots = coverageThinSpots(model);
    return (
      <div className={cn("flex flex-col gap-2", className)}>
        <table className="border-separate border-spacing-x-1 border-spacing-y-1 self-start">
          <caption className="sr-only">Evidence coverage by claim category and source class</caption>
          <tbody>
            {model.rows.map((row) => (
              <tr key={row.category}>
                <th scope="row" className="pr-2 text-left text-xs font-normal text-ink-secondary">
                  {row.category}
                </th>
                {model.columns.map((reliability, index) => {
                  const cell = row.cells[index];
                  return (
                    <td
                      key={reliability}
                      title={cellWords(row, cell)}
                      className={cn("leading-none", reliability === seller[0] && "pl-2")}
                    >
                      <span className="sr-only">{cellWords(row, cell)}</span>
                      <span aria-hidden className="inline-flex">
                        <CellMark state={cell.state} size={8} />
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {spots.length > 0 ? <p className="text-xs text-ink-secondary">{spots.join(" · ")}</p> : null}
      </div>
    );
  }

  const legend = LEGEND.filter(
    (item) =>
      (item.state !== "searched_empty" || model.has_empty_searches) &&
      (item.state !== "not_searched" || model.rows.some((row) => row.not_searched_reason)),
  );
  const isSelected = (reliability: ReliabilityClass, category: string | null) =>
    selection?.reliability === reliability && selection.category === category;
  const toggle = (next: CoverageSelection) =>
    onSelect?.(isSelected(next.reliability, next.category) ? null : next);

  return (
    <figure className={cn("flex flex-col gap-3", className)}>
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-176 border-collapse text-dense">
          <caption className="sr-only">
            What the evidence for each kind of claim rests on: claim category by source class
          </caption>
          <thead>
            <tr className="text-xs text-ink-muted">
              <th className="px-4 pt-3 text-left font-normal" />
              <th colSpan={independent.length} className="px-1 pt-3 text-left font-normal">
                Independent sources, strongest first
              </th>
              <th colSpan={seller.length} className="border-l border-line-strong px-3 pt-3 text-left font-normal">
                Seller&apos;s own
              </th>
            </tr>
            <tr className="border-b border-line-strong align-bottom">
              <th scope="col" className="px-4 py-2 text-left text-xs font-medium text-ink-secondary">
                Kind of claim
              </th>
              {model.columns.map((reliability) => {
                const head = (
                  <span className="block w-18 text-xs leading-4 font-medium text-ink-secondary">
                    {CLASS_SHORT_LABEL[reliability]}
                  </span>
                );
                return (
                  <th
                    key={reliability}
                    scope="col"
                    className={cn("px-1 py-2 text-left", reliability === seller[0] && "border-l border-line-strong pl-3")}
                  >
                    {onSelect ? (
                      <button
                        type="button"
                        aria-pressed={isSelected(reliability, null)}
                        onClick={() => toggle({ reliability, category: null })}
                        className={cn(
                          "rounded-xs text-left transition-colors hover:[&>span]:text-ink",
                          isSelected(reliability, null) && "[&>span]:text-accent [&>span]:underline",
                        )}
                      >
                        {head}
                      </button>
                    ) : (
                      head
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {model.rows.map((row) => (
              <tr key={row.category} className="border-b border-line last:border-b-0">
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  <Tooltip
                    content={
                      <span className="flex flex-col gap-1">
                        <span>Claim {row.claim_numbers.join(", ")}</span>
                        <StatusCounts counts={row.counts} className="rounded-xs bg-surface p-0.5" />
                      </span>
                    }
                  >
                    <span tabIndex={0} className="inline-flex items-baseline gap-2 rounded-xs">
                      <span className="text-ink">{row.category}</span>
                      <span className="font-mono text-xs text-ink-muted">{row.claim_numbers.length}</span>
                    </span>
                  </Tooltip>
                </th>
                {row.cells.map((cell) => {
                  const words = cellWords(row, cell);
                  const pickable = onSelect && (cell.state === "found" || cell.state === "seller");
                  const inner = (
                    <Fragment>
                      <CellMark state={cell.state} />
                      {cell.count > 0 ? (
                        <span className="font-mono text-xs text-ink">{cell.count}</span>
                      ) : null}
                    </Fragment>
                  );
                  return (
                    <td
                      key={cell.reliability}
                      className={cn("px-1 py-1", cell.reliability === seller[0] && "border-l border-line-strong pl-3")}
                    >
                      <Tooltip content={words}>
                        {pickable ? (
                          <button
                            type="button"
                            aria-label={words}
                            aria-pressed={isSelected(cell.reliability, row.category)}
                            onClick={() => toggle({ reliability: cell.reliability, category: row.category })}
                            className={cn(
                              "inline-flex h-7 min-w-10 items-center gap-1.5 rounded-xs px-1.5 transition-colors hover:bg-surface-raised",
                              isSelected(cell.reliability, row.category) && "bg-accent-tint ring-1 ring-accent-line",
                            )}
                          >
                            {inner}
                          </button>
                        ) : (
                          <span
                            tabIndex={0}
                            role="img"
                            aria-label={words}
                            className="inline-flex h-7 min-w-10 items-center gap-1.5 rounded-xs px-1.5"
                          >
                            {inner}
                          </span>
                        )}
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption className="flex flex-col gap-2">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-secondary" aria-label="Legend">
          {legend.map((item) => (
            <li key={item.state} className="inline-flex items-center gap-1.5">
              <CellMark state={item.state} />
              {item.label}
            </li>
          ))}
        </ul>
        {waiting ? (
          <p className="text-xs text-not-checked">
            Waiting on identity. No source is read for a claim until the legal entity is confirmed
          </p>
        ) : !model.has_empty_searches ? (
          <p className="text-xs text-ink-muted">
            A search that ran and found nothing is not recorded yet, so an empty cell means only
            that no fact came from that class
          </p>
        ) : null}
      </figcaption>
    </figure>
  );
}
