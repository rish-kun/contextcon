"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { formatShare, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { NumberTween } from "@/components/dealproof/number-tween";
import { Tooltip } from "@/components/ui/tooltip";
import { claimsLeftEstimate, type MeterModel } from "./derive";
import { draw } from "./parts";

/** Credits come in fractions from the provider: `19.5`, `4`, `1,204`. */
const credits = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 1 });

/** Hatched blocks drawn past the end of the track before the rest is given as a number. */
const MAX_BLOCKS = 12;

/**
 * What the case cost, where the credits went, and what the budget stopped. One bar
 * segmented by step in run order, so it says where the credits went and not only how
 * many. Checks the budget left undone are drawn past the end of the track as hatched
 * blocks, one per check: the consequence of the limit, shown where the limit is. The bar
 * never turns red, because reaching a budget is a stated limit and not an error.
 *
 * Credits and model dollars are two currencies: model usage is a separate figure and is
 * never part of the bar.
 *
 * Static on a page visit. While a run is live the running segment grows and the figure
 * tweens each time the credit count changes.
 */
export function CostMeter({
  model,
  variant = "full",
  notCheckedHref,
  usdDigits = 2,
  className,
}: {
  model: MeterModel;
  /** compact: a 48px bar beside "86 cr · $0.42", for the case header and dashboard rows. */
  variant?: "full" | "compact";
  /** Where the hatched blocks lead: the claims that were not checked. */
  notCheckedHref?: string;
  /** Decimals on the model figure. Per-step usage is a fraction of a cent, so the Cost tab uses 4. */
  usdDigits?: number;
  className?: string;
}) {
  const [active, setActive] = useState<string | null>(null);
  const formatUsd = (value: number) => `$${value.toFixed(usdDigits)}`;
  const { used, budget, segments } = model;
  // The track is the budget. If more was spent than budgeted, the track grows to hold it.
  const scale = Math.max(budget, used, 0);
  const share = budget > 0 ? Math.min(1, used / budget) : 0;
  const reached = budget > 0 && used >= budget;
  const notRun = model.checks_not_run;
  const words = `${credits(used)} of ${credits(budget)} credits`;

  if (variant === "compact") {
    return (
      <span
        className={cn("inline-flex items-center gap-2 font-mono text-xs whitespace-nowrap text-ink-secondary", className)}
        aria-label={`${credits(used)} Crustdata credits of ${credits(budget)} and ${formatUsd(model.model_usd)} model usage${
          notRun > 0 ? `. ${plural(notRun, "check")} not run` : ""
        }`}
      >
        <span aria-hidden>
          {credits(used)} cr · {formatUsd(model.model_usd)}
        </span>
        <span aria-hidden className="inline-flex items-center gap-0.5">
          <span className="relative inline-block h-1 w-12 overflow-hidden rounded-full bg-surface-sunken ring-1 ring-line-strong">
            <span className="absolute inset-y-0 left-0 bg-ink" style={{ width: `${share * 100}%` }} />
          </span>
          {notRun > 0 ? (
            <span className="hatch-dense inline-block h-1 w-2 border border-dashed border-not-checked-line" />
          ) : null}
        </span>
      </span>
    );
  }

  const left = claimsLeftEstimate(model);
  const live = segments.some((segment) => segment.running);
  const blocks = Math.min(notRun, MAX_BLOCKS);
  const notRunText = `${plural(notRun, "check")} not run`;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-1">
        <p className="font-mono text-xl font-medium text-ink">
          <NumberTween value={used} format={credits} /> of {credits(budget)} credits
        </p>
        <p className="font-mono text-sm text-ink-secondary">
          Model usage <span className="font-medium text-ink">{formatUsd(model.model_usd)}</span>
        </p>
      </div>

      <div className="flex items-center gap-2">
        <div
          role="meter"
          aria-label="Crustdata credits used against the budget, by step"
          aria-valuemin={0}
          aria-valuemax={budget}
          aria-valuenow={Math.min(used, budget)}
          aria-valuetext={words}
          className="flex h-3 min-w-0 flex-1 gap-0.5 rounded-xs bg-surface-sunken ring-1 ring-line-strong"
        >
          {scale > 0
            ? segments.map((segment) => {
                const width = (segment.credits / scale) * 100;
                const dimmed = active !== null && active !== segment.key;
                return (
                  <Tooltip
                    key={segment.key}
                    content={`${segment.label}: ${credits(segment.credits)} credits${
                      segment.steps > 1 ? `, ${segment.steps} steps` : ""
                    } · ${formatShare(budget > 0 ? segment.credits / budget : 0)} of the budget${
                      segment.running ? " · running now" : ""
                    }`}
                  >
                    <motion.span
                      // `layout` moves the segment by transform when its width changes during
                      // a run. Nothing plays on mount.
                      layout
                      transition={draw}
                      tabIndex={0}
                      onPointerEnter={() => setActive(segment.key)}
                      onPointerLeave={() => setActive(null)}
                      onFocus={() => setActive(segment.key)}
                      onBlur={() => setActive(null)}
                      style={{ width: `${width}%` }}
                      className={cn(
                        "h-full min-w-0.5 transition-colors first:rounded-l-xs",
                        segment.running ? "bg-ink-muted" : dimmed ? "bg-ink-muted" : "bg-ink",
                        segment.running && dimmed && "opacity-60",
                      )}
                    />
                  </Tooltip>
                );
              })
            : null}
        </div>
        <span className="font-mono text-xs text-ink-muted">{credits(budget)}</span>
        {notRun > 0 ? (
          <span
            role="img"
            aria-label={`${notRunText}, drawn past the end of the budget`}
            className="flex items-center gap-0.5"
          >
            {Array.from({ length: blocks }, (_, index) => (
              <span
                key={index}
                className="hatch-dense h-3 w-3 rounded-[2px] border border-dashed border-not-checked-line"
              />
            ))}
            {notRun > blocks ? (
              <span className="pl-1 font-mono text-xs text-not-checked">+{notRun - blocks}</span>
            ) : null}
          </span>
        ) : null}
      </div>

      {/* The parts in bar order. The bar's own text would not fit a narrow segment. */}
      {segments.length > 0 ? (
        <ol className="flex flex-wrap gap-x-5 gap-y-1 text-xs" aria-label="Credits by step, in run order">
          {segments.map((segment, index) => (
            <li
              key={segment.key}
              onPointerEnter={() => setActive(segment.key)}
              onPointerLeave={() => setActive(null)}
              className={cn(
                "inline-flex items-baseline gap-1.5 transition-colors",
                active !== null && active !== segment.key ? "text-ink-muted" : "text-ink-secondary",
              )}
            >
              <span className="font-mono text-2xs text-ink-muted">{index + 1}</span>
              <span>{segment.running ? `Now: ${segment.label}` : segment.label}</span>
              <span className="font-mono text-ink">
                {credits(segment.credits)}
                {segment.running ? " so far" : ""}
              </span>
            </li>
          ))}
          <li className="inline-flex items-baseline gap-1.5 text-ink-muted">
            <span className="font-mono">{credits(Math.max(0, budget - used))}</span> left
          </li>
        </ol>
      ) : (
        <p className="text-xs text-ink-secondary">Nothing spent yet · 0 of {credits(budget)} credits</p>
      )}

      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-xs text-ink-secondary">
        <span>{reached ? "Budget reached" : `${formatShare(share)} of the credit budget`}</span>
        {notRun > 0 ? (
          notCheckedHref ? (
            <Link
              href={notCheckedHref}
              className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
            >
              {notRunText}
            </Link>
          ) : (
            <span className="text-not-checked">{notRunText}</span>
          )
        ) : null}
        {model.cached_steps > 0 ? (
          <span>From cache: {plural(model.cached_steps, "step")} · 0 credits</span>
        ) : null}
        {live && left !== null ? (
          <span>
            Budget would stop after about {plural(left, "more claim")}{" "}
            <span className="font-mono text-2xs">Estimate</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}
