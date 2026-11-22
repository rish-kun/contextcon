"use client";

import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { formatCredits } from "@/lib/format";
import type { CostDelta } from "@/lib/run/activity-store";
import { ease } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { NumberTween } from "@/components/dealproof/number-tween";
import { modelUsd } from "./wording";

const SEGMENTS = 10;
/** From this share of the budget the meter says how much is left. */
const LOW_FROM = 0.8;

/** "+3", once, beside the figure a call just added to. A cache hit reads "+0 · cache". */
function Delta({ delta }: { delta: CostDelta | null }) {
  const reduced = useReducedMotion();
  // Only a call that returned in front of the reader is announced; history is not.
  const [mountedAt] = useState(delta?.seq ?? 0);
  const show = delta !== null && delta.credits !== null && delta.seq > mountedAt;

  return (
    <span className="relative inline-block h-4 w-0" aria-hidden>
      {show ? (
        <motion.span
          key={delta.seq}
          initial={{ opacity: 1, y: 0 }}
          animate={reduced ? { opacity: [1, 1, 0] } : { opacity: 0, y: -8 }}
          transition={reduced ? { duration: 1, times: [0, 0.95, 1] } : { duration: 0.6, ease }}
          className="absolute bottom-0 left-1 font-mono text-2xs whitespace-nowrap text-ink-secondary"
        >
          +{formatCredits(delta.credits ?? 0)}
          {delta.fromCache ? " · cache" : null}
        </motion.span>
      ) : null}
    </span>
  );
}

export interface CostMeterProps {
  credits: number;
  budget: number;
  usd: number;
  /** The call that last changed the totals, for the one-time "+3". */
  delta?: CostDelta | null;
  /** Hide the segment track where there is no room for it. */
  compact?: boolean;
  className?: string;
}

/**
 * Credits against the run's budget, in ten segments, and model dollars beside it. They
 * are two currencies and are never added. Reaching the budget is a stated limit, so the
 * meter turns hatched and nothing turns red.
 */
export function CostMeter({ credits, budget, usd, delta = null, compact = false, className }: CostMeterProps) {
  const share = budget > 0 ? Math.min(1, credits / budget) : 0;
  const reached = budget > 0 && credits >= budget;
  const low = !reached && share >= LOW_FROM;
  const filled = Math.round(share * SEGMENTS);
  const left = Math.max(0, Math.round((1 - share) * 100));

  return (
    <div
      className={cn("flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1", className)}
    >
      {compact ? null : (
        <span
          role="meter"
          aria-label="Crustdata credits used against the run budget"
          aria-valuemin={0}
          aria-valuemax={budget}
          aria-valuenow={Math.min(credits, budget)}
          aria-valuetext={`${formatCredits(credits)} of ${formatCredits(budget)} credits`}
          className="inline-flex shrink-0 gap-0.5"
        >
          {Array.from({ length: SEGMENTS }, (_, index) => {
            const on = index < filled;
            // The segment that crosses 80% of the budget is drawn in the Not checked ink.
            const crossing = on && index >= SEGMENTS * LOW_FROM;
            return (
              <span
                key={index}
                className={cn(
                  "h-3 w-1.5 rounded-[1px] border transition-colors duration-(--duration-base)",
                  reached
                    ? "hatch-dense border-dashed border-not-checked-line"
                    : on
                      ? crossing
                        ? "border-not-checked bg-not-checked"
                        : "border-ink bg-ink"
                      : "border-line-strong bg-surface",
                )}
              />
            );
          })}
        </span>
      )}
      <p className="font-mono text-xs whitespace-nowrap text-ink-secondary">
        <span className="text-ink">
          <NumberTween value={credits} format={formatCredits} />
        </span>{" "}
        of {formatCredits(budget)} cr
        <Delta delta={delta} />
        {usd > 0 ? <span> · {modelUsd(usd)}</span> : null}
        {reached ? (
          <span className="font-medium text-not-checked"> · Budget reached</span>
        ) : low ? (
          <span className="text-not-checked"> · {left}% left</span>
        ) : null}
      </p>
    </div>
  );
}
