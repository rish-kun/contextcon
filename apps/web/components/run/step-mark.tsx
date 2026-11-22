"use client";

import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import type { StepOut } from "@/lib/api/client";
import { duration, ease } from "@/lib/transitions";
import { cn } from "@/lib/utils";

type StepState = StepOut["state"];

const stroke = {
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

/**
 * A 12px arc that turns once every 900 ms, for as long as the work it stands for is
 * running. Under reduced motion it is a static half-filled ring.
 */
export function ArcSpinner({ className }: { className?: string }) {
  const reduced = useReducedMotion();
  if (reduced) {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden className={className}>
        <circle cx="8" cy="8" r="5.25" {...stroke} />
        <path d="M8 2.75a5.25 5.25 0 0 0 0 10.5z" fill="currentColor" />
      </svg>
    );
  }
  return (
    <motion.svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
      className={className}
      animate={{ rotate: 360 }}
      transition={{ duration: 0.9, ease: "linear", repeat: Infinity }}
    >
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeOpacity="0.18" strokeWidth="1.5" />
      <path d="M8 2.75a5.25 5.25 0 0 1 5.25 5.25" {...stroke} />
    </motion.svg>
  );
}

/**
 * The mark at the left of a step: open ring, spinner, drawn check, dashed ring, cross.
 * A mark only performs when its state changed in front of the reader. A step that was
 * already done when the page opened, or that was replayed from cache, is simply there.
 */
export function StepMark({
  state,
  fromCache = false,
  className,
}: {
  state: StepState;
  fromCache?: boolean;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const [mountedAs] = useState(state);
  // Under reduced motion every mark is simply in its state: no fade, and the check is not drawn.
  const changed = state !== mountedAs && !reduced;
  const settle = changed
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: duration.base, ease } }
    : {};

  if (state === "running") {
    return (
      <motion.span key="running" {...settle} className={cn("inline-flex text-ink", className)}>
        <ArcSpinner />
      </motion.span>
    );
  }

  if (state === "done") {
    return (
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden
        className={cn("text-ink", className)}
      >
        <motion.path
          d="M3.5 8.4 6.6 11.4 12.6 4.8"
          {...stroke}
          initial={changed && !fromCache ? { pathLength: 0 } : false}
          animate={{ pathLength: 1 }}
          transition={{ duration: duration.base, ease }}
        />
      </svg>
    );
  }

  if (state === "failed") {
    return (
      <motion.svg
        key="failed"
        {...settle}
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden
        className={cn("text-contradicted", className)}
      >
        <path d="m4.5 4.5 7 7m0-7-7 7" {...stroke} />
      </motion.svg>
    );
  }

  if (state === "skipped_budget") {
    return (
      <motion.svg
        key="skipped"
        {...settle}
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden
        className={cn("text-not-checked", className)}
      >
        <circle cx="8" cy="8" r="5.25" {...stroke} strokeLinecap="butt" strokeDasharray="2.2 1.92" />
      </motion.svg>
    );
  }

  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
      className={cn("text-ink-muted", className)}
    >
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
