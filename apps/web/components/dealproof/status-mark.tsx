"use client";

import { AnimatePresence, motion } from "motion/react";
import { CLAIM_STATUS_LABEL, NOT_CHECKED_REASON_LABEL } from "@/lib/labels";
import { transition } from "@/lib/transitions";
import {
  CLAIM_STATUSES,
  type ClaimStatus,
  type ClaimStatusCounts,
  type NotCheckedReason,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { StatusGlyph } from "./glyphs";

/** Ink for the glyph and label. */
export const STATUS_INK: Record<ClaimStatus, string> = {
  supported: "text-supported",
  partially_corroborated: "text-partial",
  conflicting_evidence: "text-conflicting",
  contradicted: "text-contradicted",
  cannot_verify: "text-cannot-verify",
  not_checked: "text-not-checked",
};

/** Fill and border. Not checked is the only status that is dashed and hatched. */
export const STATUS_SURFACE: Record<ClaimStatus, string> = {
  supported: "border-supported-line bg-supported-tint",
  partially_corroborated: "border-partial-line bg-partial-tint",
  conflicting_evidence: "border-conflicting-line bg-conflicting-tint",
  contradicted: "border-contradicted-line bg-contradicted-tint",
  cannot_verify: "border-cannot-verify-line bg-cannot-verify-tint",
  not_checked: "hatch border-dashed border-not-checked-line",
};

function notCheckedText(reason?: NotCheckedReason | null): string {
  return `${CLAIM_STATUS_LABEL.not_checked} · ${
    reason ? NOT_CHECKED_REASON_LABEL[reason] : "reason not recorded"
  }`;
}

export interface StatusMarkProps {
  status: ClaimStatus;
  /**
   * tag: glyph + label, the default. mark: glyph only, for the ledger spine and dense
   * tables, always next to a legend. count: glyph + mono number, for summaries.
   */
  form?: "tag" | "mark" | "count";
  /** For form="count". */
  count?: number;
  /** Shown with Not checked, always: "Not checked · budget reached". */
  reason?: NotCheckedReason | null;
  /** Strike the label through: the previous value in a diff. */
  struck?: boolean;
  className?: string;
}

/**
 * A claim status. Shape and words carry the meaning; colour only reinforces it.
 * When the status changes, the mark fades in and scales from 0.9 over 200ms.
 */
export function StatusMark({
  status,
  form = "tag",
  count,
  reason,
  struck = false,
  className,
}: StatusMarkProps) {
  const label = status === "not_checked" ? notCheckedText(reason) : CLAIM_STATUS_LABEL[status];

  if (form === "mark") {
    return (
      <span
        role="img"
        aria-label={`Status: ${label}`}
        title={label}
        className={cn("inline-flex shrink-0", STATUS_INK[status], className)}
      >
        <StatusGlyph status={status} />
      </span>
    );
  }

  if (form === "count") {
    return (
      <span
        aria-label={`${count ?? 0} ${CLAIM_STATUS_LABEL[status]}`}
        title={CLAIM_STATUS_LABEL[status]}
        className={cn(
          "inline-flex h-6 shrink-0 items-center gap-1 rounded-sm border px-1.5",
          STATUS_INK[status],
          status === "not_checked" ? STATUS_SURFACE.not_checked : "border-transparent",
          className,
        )}
      >
        <StatusGlyph status={status} />
        <span aria-hidden className="font-mono text-xs font-medium">
          {count ?? 0}
        </span>
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex h-6 max-w-full shrink-0 items-center rounded-sm border px-2 text-xs font-medium",
        STATUS_INK[status],
        STATUS_SURFACE[status],
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={status}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={transition.base}
          className="inline-flex min-w-0 items-center gap-1"
        >
          <StatusGlyph status={status} className="shrink-0" />
          <span className={cn("truncate", struck && "line-through")}>{label}</span>
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

/** The six glyphs with their names, in the fixed order. Sits above any ledger or table of marks. */
export function StatusLegend({ className }: { className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1", className)} aria-label="Status legend">
      {CLAIM_STATUSES.map((status) => (
        <li key={status} className={cn("inline-flex items-center gap-1 text-xs", STATUS_INK[status])}>
          <StatusGlyph status={status} />
          <span className="text-ink-secondary">{CLAIM_STATUS_LABEL[status]}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Counts in the fixed order. A non-zero Not checked count is always shown, hatched and
 * set apart; zero counts of the other statuses are left out.
 */
export function StatusCounts({
  counts,
  className,
}: {
  counts: ClaimStatusCounts;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {CLAIM_STATUSES.filter((status) => status !== "not_checked" && counts[status] > 0).map(
        (status) => (
          <StatusMark key={status} status={status} form="count" count={counts[status]} />
        ),
      )}
      {counts.not_checked > 0 ? (
        <StatusMark status="not_checked" form="count" count={counts.not_checked} className="ml-2" />
      ) : null}
    </span>
  );
}

/**
 * A distribution bar of statuses in the fixed order. Each segment is as wide as its
 * count. The Not checked segment is hatched and sits after a visible gap, so the bar
 * reads as unfinished. It is a picture of the counts; put the counts in words next to it.
 */
export function StatusDistribution({
  counts,
  className,
}: {
  counts: ClaimStatusCounts;
  className?: string;
}) {
  const settled = CLAIM_STATUSES.filter((s) => s !== "not_checked" && counts[s] > 0);
  const summary = CLAIM_STATUSES.filter((s) => counts[s] > 0)
    .map((s) => `${counts[s]} ${CLAIM_STATUS_LABEL[s]}`)
    .join(", ");

  return (
    <div
      role="img"
      aria-label={summary || "No checks yet"}
      className={cn("flex h-7 w-full items-stretch gap-3", className)}
    >
      {settled.length > 0 ? (
        <div
          className="flex min-w-0 items-stretch gap-0.5"
          style={{ flexGrow: settled.reduce((sum, s) => sum + counts[s], 0) }}
        >
          {settled.map((status) => (
            <span
              key={status}
              title={`${counts[status]} ${CLAIM_STATUS_LABEL[status]}`}
              style={{ flexGrow: counts[status] }}
              className={cn(
                "inline-flex min-w-10 basis-0 items-center justify-center gap-1 rounded-xs border",
                STATUS_INK[status],
                STATUS_SURFACE[status],
              )}
            >
              <StatusGlyph status={status} />
              <span className="font-mono text-xs font-medium">{counts[status]}</span>
            </span>
          ))}
        </div>
      ) : null}
      {counts.not_checked > 0 ? (
        <span
          title={`${counts.not_checked} ${CLAIM_STATUS_LABEL.not_checked}`}
          style={{ flexGrow: counts.not_checked }}
          className={cn(
            "inline-flex min-w-10 basis-0 items-center justify-center gap-1 rounded-xs border",
            STATUS_INK.not_checked,
            STATUS_SURFACE.not_checked,
          )}
        >
          <StatusGlyph status="not_checked" />
          <span className="font-mono text-xs font-medium">{counts.not_checked}</span>
        </span>
      ) : null}
    </div>
  );
}
