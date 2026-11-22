"use client";

import { motion, useInView } from "motion/react";
import { useRef } from "react";
import { CriteriaStrip } from "@/components/dealproof";
import { transition } from "@/lib/transitions";
import type { FitResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useReducedMotionPreference } from "./use-reduced-motion";

/**
 * The product's criteria strip, drawn when it scrolls into view: the cells fill left to
 * right with the hatched ones last. Remounting on entry replays the strip's own entrance.
 *
 * Under reduced motion the strip is simply there: no wait for it to scroll into view, no
 * fade and no remount. The CSS override shows it before hydration too, when the
 * preference cannot be read from script yet.
 */
export function FitReadoutInView({
  fit,
  className,
}: {
  fit: FitResult;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotionPreference();
  const shown = inView || reduce === true;
  return (
    <motion.div
      ref={ref}
      data-reveal
      className={cn("motion-reduce:opacity-100!", className)}
      initial={{ opacity: 0 }}
      animate={{ opacity: shown ? 1 : 0 }}
      transition={reduce ? { duration: 0 } : transition.base}
    >
      <CriteriaStrip key={inView && reduce === false ? "in" : "before"} fit={fit} />
    </motion.div>
  );
}
