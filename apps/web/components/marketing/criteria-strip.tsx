"use client";

import { animate, motion, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import { duration, ease, stagger, transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import type { CriteriaCell, Verdict } from "./content";

const CELL: Record<Verdict, string> = {
  met: "bg-ink",
  not_met: "border-[1.5px] border-ink-secondary bg-surface",
  unknown: "hatch border border-dashed border-not-checked-line",
};

/**
 * Fit and its assessable share, as one readout that cannot be split.
 * The track is every criterion by weight; whatever could not be assessed is hatched
 * and grouped at the end, so the track is visibly unfinished.
 */
export function CriteriaStrip({
  fit,
  assessable,
  cells,
  compact = false,
  className,
}: {
  fit: number;
  assessable: number;
  cells: CriteriaCell[];
  compact?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const fitRef = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  const play = inView && !reduce;

  // "Fit" counts up to its value once; tabular figures keep the width still.
  useEffect(() => {
    const node = fitRef.current;
    if (!play || !node) return;
    const controls = animate(0, fit, {
      duration: duration.slow,
      ease,
      onUpdate: (v) => {
        node.textContent = String(Math.round(v));
      },
    });
    return () => controls.stop();
  }, [play, fit]);

  const firstUnknown = cells.findIndex((c) => c.verdict === "unknown");
  const met = cells.filter((c) => c.verdict === "met").length;
  const notMet = cells.filter((c) => c.verdict === "not_met").length;
  const unknown = cells.length - met - notMet;

  return (
    <div ref={ref} className={className}>
      <p
        className={cn(
          "flex flex-wrap items-baseline gap-x-2 font-mono font-medium text-ink",
          compact ? "text-dense" : "text-base lg:text-lg",
        )}
      >
        <span>
          Fit <span ref={fitRef}>{fit}</span>
        </span>
        <span aria-hidden>·</span>
        <span>{assessable}% of criteria assessable</span>
      </p>
      <div
        role="img"
        aria-label={`${met} criteria met, ${notMet} not met, ${unknown} could not be assessed`}
        className={cn("mt-2 flex gap-0.5", compact ? "h-1.5" : "h-8")}
      >
        {cells.map((cell, i) => (
          <motion.span
            key={i}
            data-reveal
            initial={{ opacity: 0 }}
            animate={inView || reduce ? { opacity: 1 } : undefined}
            transition={{ ...transition.base, delay: i * stagger }}
            style={{ flexGrow: cell.w }}
            className={cn(
              "basis-0",
              compact ? "rounded-[1px]" : "rounded-xs",
              compact && cell.verdict === "unknown"
                ? "hatch-dense border border-dashed border-not-checked-line"
                : CELL[cell.verdict],
              compact && cell.verdict === "not_met" && "border",
              i === firstUnknown && (compact ? "ml-1" : "ml-2"),
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function CriteriaLegend() {
  const item = "inline-flex items-center gap-2";
  const swatch = "inline-block h-3 w-5 rounded-xs";
  return (
    <p className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-ink-secondary">
      <span className={item}>
        <span aria-hidden className={cn(swatch, CELL.met)} />
        Met
      </span>
      <span className={item}>
        <span aria-hidden className={cn(swatch, CELL.not_met)} />
        Not met
      </span>
      <span className={item}>
        <span aria-hidden className={cn(swatch, CELL.unknown)} />
        Unknown · could not assess
      </span>
    </p>
  );
}
