"use client";

import { motion } from "motion/react";
import { rise, staggerDelay, transition } from "@/lib/transitions";

/**
 * One entrance for the whole page: a fade and an 8px rise, once, when the block
 * scrolls into view. Under reduced motion the root MotionConfig drops the rise.
 * `data-reveal` lets the no-script fallback in the page show the block.
 */
export function Reveal({
  children,
  className,
  index = 0,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  /** Position in a staggered group. Capped at six, as everywhere else. */
  index?: number;
  as?: "div" | "li" | "section";
}) {
  const Tag = motion[as];
  return (
    <Tag
      data-reveal
      className={className}
      initial={{ opacity: 0, y: rise }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
      transition={{ ...transition.slow, delay: staggerDelay(index) }}
    >
      {children}
    </Tag>
  );
}
