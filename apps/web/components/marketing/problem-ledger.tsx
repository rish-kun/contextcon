"use client";

import { motion, useReducedMotion, useScroll } from "motion/react";
import { useRef } from "react";
import { PROBLEMS } from "./content";
import { Reveal } from "./reveal";

/**
 * What goes wrong on one side, what DealProof does on the other, with a spine
 * between them. The spine is inked in as the reader moves down the list: the one
 * scroll-linked element on the page, and it reports reading progress.
 */
export function ProblemLedger() {
  const ref = useRef<HTMLOListElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 0.75", "end 0.6"],
  });

  return (
    <div className="relative pl-6 lg:pl-0">
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 w-px bg-line-strong lg:left-[calc((100%-4rem)*5/12+2rem)]"
      >
        <motion.div
          className="h-full w-full origin-top bg-ink"
          style={{ scaleY: reduce ? 1 : scrollYProgress }}
        />
      </div>

      <div
        aria-hidden
        className="mb-2 hidden grid-cols-[5fr_7fr] gap-x-16 text-xs text-ink-muted lg:grid"
      >
        <span>What goes wrong</span>
        <span>What DealProof does</span>
      </div>

      <ol ref={ref}>
        {PROBLEMS.map((p, i) => (
          <Reveal
            as="li"
            key={p.wrong}
            className="grid gap-x-16 gap-y-2 border-t border-line py-5 lg:grid-cols-[5fr_7fr] lg:py-6"
          >
            <div className="flex gap-3">
              <span className="w-5 shrink-0 font-mono text-xs leading-6 text-ink-muted">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <p className="text-base text-ink">{p.wrong}</p>
                <p className="text-sm text-ink-muted">{p.cost}</p>
              </div>
            </div>
            <p className="pl-8 text-base text-ink lg:pl-0 lg:text-lg">
              <span className="sr-only">What DealProof does: </span>
              {p.fix}
            </p>
          </Reveal>
        ))}
      </ol>
    </div>
  );
}
