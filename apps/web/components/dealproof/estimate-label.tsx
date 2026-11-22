"use client";

import { ESTIMATE_LABEL } from "@/lib/labels";
import type { EstimateKind } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/tooltip";

/**
 * Marks a value that is not a recorded fact, in three ways at once: a leading tilde
 * (estimates only), a dotted underline, and the word Estimate or Signal after it.
 * The basis is on hover and focus, and inline when `showBasis` is set.
 *
 *   <EstimateLabel kind="estimate" basis="from professional profiles, not a payroll count">
 *     180 people
 *   </EstimateLabel>
 */
export function EstimateLabel({
  kind,
  basis,
  children,
  showBasis = false,
  className,
}: {
  kind: EstimateKind;
  /** Plain words: what the value was inferred from. */
  basis: string;
  /** The value, without a tilde. */
  children: React.ReactNode;
  showBasis?: boolean;
  className?: string;
}) {
  const word = ESTIMATE_LABEL[kind];

  return (
    <span className={cn("inline-flex flex-wrap items-baseline gap-x-2", className)}>
      <span className="underline-estimate">
        {kind === "estimate" ? "~" : null}
        {children}
      </span>
      {showBasis ? (
        <span className="font-mono text-2xs text-ink-secondary">
          {word} · {basis}
        </span>
      ) : (
        <Tooltip content={`${word} · ${basis}`}>
          <button
            type="button"
            aria-label={`${word}: ${basis}`}
            className="rounded-xs font-mono text-2xs text-ink-secondary transition-colors hover:text-ink"
          >
            {word}
          </button>
        </Tooltip>
      )}
    </span>
  );
}
