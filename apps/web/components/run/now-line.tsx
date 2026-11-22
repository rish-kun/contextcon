"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { duration, ease } from "@/lib/transitions";
import { cn } from "@/lib/utils";

/** The line changes at most this often; labels in between are skipped, never shown late. */
const MIN_CHANGE_MS = 400;
/** After this long with no event, the line says how long it has been. */
const IDLE_AFTER_S = 8;
/** After this long, it names what the run is waiting on. */
const WAITING_AFTER_S = 30;

/** The latest value, changing no more than once per `ms`. */
export function useLatestAtMost<T>(value: T, ms: number): T {
  const [shown, setShown] = useState(value);
  const lastChange = useRef(0);
  useEffect(() => {
    const wait = Math.max(0, lastChange.current + ms - Date.now());
    const timer = setTimeout(() => {
      lastChange.current = Date.now();
      setShown(value);
    }, wait);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return shown;
}

export interface NowLineProps {
  /** The label of the latest status, call or source event. Null before the first one. */
  label: string | null;
  /** When that event happened, in ms. */
  at: number | null;
  /** The clock the idle suffix is counted against. */
  nowMs: number;
  /** When the run was created, for the wait before the first event. */
  startedAt: number | null;
  /** True while no worker has picked the run up. */
  waitingForWorker?: boolean;
  /** The provider of the open call, for "still waiting on …". */
  provider?: "crustdata" | "anthropic" | null;
  className?: string;
}

/**
 * What the run is doing now, in the run's own words. It is the label of a stored event and
 * appears whole: no typewriter, no ellipsis. The only text added here is a clock: how long
 * it has been since the last event, and after 30 s which provider the run is waiting on.
 */
export function NowLine({
  label,
  at,
  nowMs,
  startedAt,
  waitingForWorker = false,
  provider = null,
  className,
}: NowLineProps) {
  const text = useLatestAtMost(label ?? (waitingForWorker ? "Waiting for a worker" : "Starting"), MIN_CHANGE_MS);
  const since = label ? at : startedAt;
  const idle = since === null ? 0 : Math.max(0, Math.floor((nowMs - since) / 1000));
  const suffix =
    label === null
      ? waitingForWorker && idle >= 2
        ? `${idle} s`
        : null
      : idle >= WAITING_AFTER_S && provider
        ? `still waiting on ${provider === "crustdata" ? "Crustdata" : "the model"}`
        : idle >= IDLE_AFTER_S
          ? `${idle} s`
          : null;

  return (
    <p className={cn("relative flex min-h-5 min-w-0 items-baseline gap-2 text-dense text-ink", className)}>
      <span className="relative min-w-0 flex-1 truncate">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={text}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: duration.base, ease }}
            className="block truncate"
          >
            {text}
          </motion.span>
        </AnimatePresence>
      </span>
      {suffix ? <span className="shrink-0 font-mono text-xs text-ink-muted">· {suffix}</span> : null}
    </p>
  );
}
