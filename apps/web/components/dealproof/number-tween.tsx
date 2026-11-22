"use client";

import { animate, useReducedMotion } from "motion/react";
import { useLayoutEffect, useRef } from "react";
import { duration, ease } from "@/lib/transitions";

const round = (n: number) => String(Math.round(n));

/**
 * A figure that tweens to its new value over 360ms when the value changes. Width does
 * not jump because figures are tabular. It renders the final value on the server and on
 * first paint, and under reduced motion it jumps straight to the value.
 *
 * A tween only ever ends on the value it was given. A render that changes nothing, or a
 * new `format` function, leaves a running tween alone; a new value starts from the figure
 * on screen. Stopping a tween part-way would leave an old figure standing as the count.
 */
export function NumberTween({
  value,
  format = round,
  className,
}: {
  value: number;
  format?: (value: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  /** The figure on screen, which mid-tween is between two values. */
  const shown = useRef(value);
  const formatRef = useRef(format);
  const reduced = useReducedMotion();

  useLayoutEffect(() => {
    formatRef.current = format;
  });

  useLayoutEffect(() => {
    const node = ref.current;
    const from = shown.current;
    if (!node || from === value) return;
    if (reduced) {
      shown.current = value;
      node.textContent = formatRef.current(value);
      return;
    }
    // React has just written the new value; start from the figure that was showing.
    node.textContent = formatRef.current(from);
    const controls = animate(from, value, {
      duration: duration.slow,
      ease,
      onUpdate: (latest) => {
        shown.current = latest;
        node.textContent = formatRef.current(latest);
      },
    });
    return () => {
      controls.stop();
      // Whatever replaces this tween, the node never keeps a figure React did not write.
      node.textContent = formatRef.current(shown.current);
    };
  }, [value, reduced]);

  return (
    <span ref={ref} className={className}>
      {format(value)}
    </span>
  );
}
