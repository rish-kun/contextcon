"use client";

import { motion, useInView } from "motion/react";
import { useRef } from "react";
import { CriteriaStrip } from "@/components/dealproof";
import { transition } from "@/lib/transitions";
import type { FitResult } from "@/lib/types";

/**
 * The product's criteria strip, drawn when it scrolls into view: the cells fill left to
 * right with the hatched ones last. Remounting on entry replays the strip's own entrance;
 * under reduced motion the strip is simply shown.
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
  return (
    <motion.div
      ref={ref}
      data-reveal
      className={className}
      initial={{ opacity: 0 }}
      animate={{ opacity: inView ? 1 : 0 }}
      transition={transition.base}
    >
      <CriteriaStrip key={inView ? "in" : "before"} fit={fit} />
    </motion.div>
  );
}
