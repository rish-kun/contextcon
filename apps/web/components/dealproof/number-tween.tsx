"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import { duration, ease } from "@/lib/transitions";

/**
 * A figure that tweens to its new value over 360ms when the value changes. Width does
 * not jump because figures are tabular. It renders the final value on the server and on
 * first paint, and under reduced motion it jumps straight to the value.
 */
export function NumberTween({
  value,
  format = (n) => String(Math.round(n)),
  className,
}: {
  value: number;
  format?: (value: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef(value);
  const reduced = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    const from = previous.current;
    previous.current = value;
    if (!node || from === value) return;
    if (reduced) {
      node.textContent = format(value);
      return;
    }
    const controls = animate(from, value, {
      duration: duration.slow,
      ease,
      onUpdate: (latest) => {
        node.textContent = format(latest);
      },
    });
    return () => controls.stop();
  }, [value, format, reduced]);

  return (
    <span ref={ref} className={className}>
      {format(value)}
    </span>
  );
}
