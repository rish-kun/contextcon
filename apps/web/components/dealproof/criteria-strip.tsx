"use client";

import { formatShare, plural } from "@/lib/format";
import { VERDICT_LABEL } from "@/lib/labels";
import { STAGGER_LIMIT } from "@/lib/transitions";
import type { CriterionResult, FitResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/tooltip";
import { NumberTween } from "./number-tween";

const CELL_STYLE: Record<CriterionResult["verdict"], string> = {
  met: "border-ink bg-ink",
  not_met: "border-ink bg-surface",
  unknown: "border-dashed border-not-checked-line",
};

function isUnavailable(fit: FitResult): boolean {
  return fit.fit === null || fit.assessable_share <= 0;
}

/** Assessed criteria keep their order; unknown ones are grouped at the right end. */
function ordered(criteria: CriterionResult[]): CriterionResult[] {
  return [
    ...criteria.filter((c) => c.verdict !== "unknown"),
    ...criteria.filter((c) => c.verdict === "unknown"),
  ];
}

/**
 * The words, always in this order and never apart:
 * "Fit 82 · 70% of criteria assessable". Both numbers are the same size and ink.
 * When nothing could be assessed it reads "Fit unavailable · 0% of criteria assessable".
 */
export function FitText({ fit, className }: { fit: FitResult; className?: string }) {
  const unavailable = isUnavailable(fit);
  return (
    <span className={cn("font-mono text-sm font-medium text-ink", className)}>
      {unavailable ? (
        "Fit unavailable"
      ) : (
        <>
          Fit <NumberTween value={fit.fit ?? 0} />
        </>
      )}
      <span aria-hidden> · </span>
      <span className="sr-only">, </span>
      {formatShare(unavailable ? 0 : fit.assessable_share)} of criteria assessable
    </span>
  );
}

/**
 * The fit readout: one track whose full width is all criteria, weighted. Met is an ink
 * cell, not met is an empty cell with a solid border, unknown is hatched with a dashed
 * border at the right end. The track is visibly shortened by what could not be assessed.
 *
 * size="compact" is the 6px strip for shortlist and dashboard rows.
 */
export function CriteriaStrip({
  fit,
  size = "default",
  caption = false,
  className,
}: {
  fit: FitResult;
  size?: "default" | "compact";
  /** Adds "Fit measures match to your criteria. It says nothing about returns". */
  caption?: boolean;
  className?: string;
}) {
  const unavailable = isUnavailable(fit);
  const criteria = ordered(fit.criteria);
  const unknown = criteria.filter((c) => c.verdict === "unknown");
  const assessed = criteria.length - unknown.length;
  const firstUnknown = criteria.findIndex((c) => c.verdict === "unknown");
  const compact = size === "compact";

  const stripLabel = criteria
    .map((c) => `${c.label}: ${VERDICT_LABEL[c.verdict]}`)
    .join(". ");

  const cells = criteria.map((criterion, index) => {
    const verdict = unavailable ? "unknown" : criterion.verdict;
    const cellClass = cn(
      "relative min-w-1 basis-0 animate-cell-in border motion-reduce:animate-none",
      compact ? "h-1.5 rounded-none" : "h-6 rounded-xs",
      CELL_STYLE[verdict],
      verdict === "unknown" && (compact ? "hatch-dense" : "hatch"),
      // A visible gap before the unassessed group.
      index === firstUnknown && index > 0 && !unavailable && (compact ? "ml-1" : "ml-2"),
      // Must-have criteria carry a notch on their top edge.
      !compact &&
        criterion.kind === "must" &&
        "before:absolute before:-top-1.5 before:left-1/2 before:h-1.5 before:w-0.5 before:-translate-x-1/2 before:bg-ink",
    );
    const style = {
      flexGrow: criterion.weight,
      animationDelay: `calc(var(--motion-stagger) * ${Math.min(index, STAGGER_LIMIT * 2)})`,
    };

    if (compact) return <span key={criterion.id} className={cellClass} style={style} />;

    return (
      <Tooltip
        key={criterion.id}
        content={
          <>
            {criterion.label}
            {criterion.kind === "must" ? " (must-have)" : null} · {VERDICT_LABEL[verdict]}
          </>
        }
      >
        <button
          type="button"
          className={cellClass}
          style={style}
          aria-label={`${criterion.label}${
            criterion.kind === "must" ? ", must-have" : ""
          }: ${VERDICT_LABEL[verdict]}`}
        />
      </Tooltip>
    );
  });

  if (compact) {
    return (
      <div className={cn("flex min-w-0 items-center gap-3", className)}>
        <FitText fit={fit} className="shrink-0 text-xs" />
        <div role="img" aria-label={stripLabel} className="flex min-w-24 flex-1 items-center gap-px">
          {cells}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <FitText fit={fit} />
      <div role="group" aria-label="Criteria" className="flex items-center gap-0.5 pt-1.5">
        {cells}
      </div>
      <p className="text-xs text-ink-secondary">
        {unavailable ? (
          <>None of the {plural(criteria.length, "criterion", "criteria")} could be assessed</>
        ) : (
          <>
            {assessed} of {plural(criteria.length, "criterion", "criteria")} assessable
            {unknown.length > 0 ? (
              <>
                {" "}
                · {unknown.length} unknown: {unknown.map((c) => c.label.toLowerCase()).join(", ")}
              </>
            ) : null}
          </>
        )}
      </p>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted" aria-label="Strip legend">
        <li className="inline-flex items-center gap-1">
          <span className="size-2.5 rounded-xs border border-ink bg-ink" aria-hidden /> Met
        </li>
        <li className="inline-flex items-center gap-1">
          <span className="size-2.5 rounded-xs border border-ink bg-surface" aria-hidden /> Not met
        </li>
        <li className="inline-flex items-center gap-1">
          <span
            className="hatch-dense size-2.5 rounded-xs border border-dashed border-not-checked-line"
            aria-hidden
          />{" "}
          Unknown · could not assess
        </li>
        <li className="inline-flex items-center gap-1">
          <span className="h-2.5 w-0.5 bg-ink" aria-hidden /> Must-have
        </li>
      </ul>
      {caption ? (
        <p className="text-xs text-ink-muted">
          Fit measures match to your criteria. It says nothing about returns
        </p>
      ) : null}
    </div>
  );
}
