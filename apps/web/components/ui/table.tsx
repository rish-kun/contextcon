"use client";

import { createContext, useContext } from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "./skeleton";

export type TableDensity = "compact" | "default" | "two-line";
const DensityContext = createContext<TableDensity | null>(null);
/** Row heights: 32 for records, 40 for directories, 52 for a name over its meta line. */
const CELL: Record<TableDensity, string> = { compact: "h-8 py-1", default: "h-10 py-2", "two-line": "h-13 py-2" };

/**
 * A plain semantic table at 13px. Numbers go in `numeric` cells: right-aligned, mono,
 * tabular. Row states read apart: hover is a surface step, selected is accent tint with a
 * left bar (set data-state="selected" and aria-selected), the header is a sunken band.
 */
export function Table({
  className,
  density,
  flush = false,
  ...props
}: React.ComponentProps<"table"> & {
  /** Set a density to get its row height and 16px edge cells. Unset keeps the 36px legacy row. */
  density?: TableDensity;
  /** No border of its own, for a table inside a flush panel body. */
  flush?: boolean;
}) {
  return (
    <DensityContext.Provider value={density ?? null}>
      <div className={cn("w-full overflow-x-auto", !flush && "rounded-lg border border-line bg-surface")}>
        <table
          className={cn(
            "w-full border-collapse text-left text-dense text-ink",
            density && "[&_td:first-child]:pl-4 [&_td:last-child]:pr-4 [&_th:first-child]:pl-4 [&_th:last-child]:pr-4",
            className,
          )}
          {...props}
        />
      </div>
    </DensityContext.Provider>
  );
}

export function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("bg-surface-sunken", className)} {...props} />;
}

export function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("[&>tr:last-child]:border-b-0", className)} {...props} />;
}

export function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      className={cn("border-t border-line-strong font-medium [&>tr]:border-b-0", className)}
      {...props}
    />
  );
}

export function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn(
        "border-b border-line transition-colors hover:bg-surface-raised data-[state=selected]:selected-bar data-[state=selected]:bg-accent-tint",
        className,
      )}
      {...props}
    />
  );
}

export function TableHead({
  className,
  numeric = false,
  ...props
}: React.ComponentProps<"th"> & { numeric?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        "h-8 px-3 text-xs font-medium whitespace-nowrap text-ink-secondary",
        numeric && "text-right",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({
  className,
  numeric = false,
  muted = false,
  ...props
}: React.ComponentProps<"td"> & { numeric?: boolean; muted?: boolean }) {
  const density = useContext(DensityContext);
  return (
    <td
      className={cn(
        "px-3 align-middle",
        density ? CELL[density] : "h-9 py-2",
        numeric && "text-right font-mono text-xs whitespace-nowrap",
        muted && "text-ink-muted",
        className,
      )}
      {...props}
    />
  );
}

/** Rows standing in for a table that is loading, at the table's own density. */
export function TableSkeleton({
  columns,
  rows = 4,
  density = "default",
}: {
  columns: number;
  rows?: number;
  density?: TableDensity;
}) {
  return (
    <Table density={density} flush aria-hidden>
      <TableBody>
        {Array.from({ length: rows }, (_, row) => (
          <TableRow key={row}>
            {Array.from({ length: columns }, (_, column) => (
              <TableCell key={column}>
                <Skeleton className={column === 0 ? "w-32" : "w-16"} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function TableCaption({ className, ...props }: React.ComponentProps<"caption">) {
  return (
    <caption
      className={cn("caption-bottom px-3 py-2 text-left text-xs text-ink-muted", className)}
      {...props}
    />
  );
}
