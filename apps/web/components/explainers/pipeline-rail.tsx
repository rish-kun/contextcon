"use client";

import { ArrowRight } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { formatDateTime } from "@/lib/format";
import { transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { WorkingIndicator } from "@/components/dealproof/run-progress";
import { Icon } from "@/components/ui/icon";
import type { Station } from "./derive";
import { draw } from "./parts";

/**
 * The line from one station to the next. Solid ink when the earlier stage produced its
 * result; the share of that stage's work that was not done is hatched at the far end, so
 * the rail cannot look complete when the case is not. Dashed when the stage has no result.
 */
function Segment({ station }: { station: Station }) {
  const done = station.state === "done";
  const share = done ? Math.min(1, Math.max(0, station.not_done_share)) : 0;
  return (
    <span
      aria-hidden
      className="relative flex min-h-6 flex-1 flex-col items-center md:min-h-0 md:flex-row"
    >
      {/* The undone state sits underneath; ink is drawn over it when the stage finishes. */}
      <span className="absolute inset-y-0 left-1/2 border-l border-dashed border-not-checked-line md:inset-x-0 md:inset-y-auto md:top-1/2 md:left-0 md:border-t md:border-l-0" />
      <motion.span
        initial={false}
        animate={{ scaleX: done ? 1 : 0, opacity: done ? 1 : 0 }}
        transition={draw}
        style={{ flexGrow: 1 - share, originX: 0 }}
        className="relative w-0.5 basis-0 bg-ink md:h-0.5 md:w-auto"
      />
      {share > 0 ? (
        <span
          title={station.not_done_note ?? undefined}
          style={{ flexGrow: share }}
          className="hatch-dense relative w-2 min-w-2 basis-0 rounded-xs border border-dashed border-not-checked-line md:h-2 md:min-h-2 md:w-auto md:min-w-4"
        />
      ) : null}
    </span>
  );
}

function Dot({ station }: { station: Station }) {
  if (station.state === "live") {
    return <WorkingIndicator className="size-5 justify-center" />;
  }
  const done = station.state === "done";
  return (
    <span
      aria-hidden
      className="relative inline-flex size-3 shrink-0 rounded-full border-2 border-ink bg-surface"
    >
      <motion.span
        initial={false}
        animate={{ opacity: done ? 1 : 0 }}
        transition={transition.base}
        className="absolute -inset-px rounded-full bg-ink"
      />
    </span>
  );
}

const STATE_WORD: Record<Station["state"], string> = {
  done: "done",
  open: "not done",
  live: "running now",
};

/**
 * Where the case is and what happens next: Discover, Verify, Evaluate, Act. Four fixed
 * stations, read from the case's runs, claims, assessment and request. It is a rail, not
 * a stepper: stations link to their tabs and nothing can be advanced from here.
 *
 * Static on a page visit. A station fills and its connector draws only when its stage
 * finishes while the page is open.
 */
export function PipelineRail({
  stations,
  readOnly = false,
  className,
}: {
  stations: Station[];
  /** No links: the copy that heads the printed memo. */
  readOnly?: boolean;
  className?: string;
}) {
  return (
    <ol
      aria-label="Where this case is"
      className={cn("flex flex-col md:grid md:grid-cols-4", className)}
    >
      {stations.map((station, index) => {
        const last = index === stations.length - 1;
        const when = formatDateTime(station.when);
        return (
          <li
            key={station.key}
            className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 md:flex md:flex-col md:gap-2"
          >
            <span className="flex flex-col items-center md:h-5 md:flex-row">
              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center md:w-auto md:justify-start">
                <Dot station={station} />
              </span>
              {last ? null : <Segment station={station} />}
            </span>

            <div className={cn("flex min-w-0 flex-col gap-0.5 md:pr-6", last ? "pb-0" : "pb-4 md:pb-0")}>
              <p className="flex flex-wrap items-baseline gap-x-2 text-sm font-medium text-ink">
                {readOnly ? (
                  station.label
                ) : (
                  <Link
                    href={station.href}
                    className="rounded-xs underline-offset-2 transition-colors hover:underline"
                  >
                    {station.label}
                  </Link>
                )}
                <span className="sr-only">, {STATE_WORD[station.state]}</span>
                {station.pass ? (
                  <span className="font-mono text-2xs font-normal text-ink-secondary">{station.pass}</span>
                ) : null}
              </p>
              <p className="text-dense text-ink">{station.produced}</p>
              {station.detail ? <p className="text-dense text-ink-secondary">{station.detail}</p> : null}
              {station.not_done_note && station.detail !== station.not_done_note && station.key !== "verify" ? (
                <p className="text-dense text-not-checked">{station.not_done_note}</p>
              ) : null}
              {when ? <p className="font-mono text-2xs text-ink-muted">{when}</p> : null}
              {station.action && !readOnly ? (
                <Link
                  href={station.action.href}
                  className="mt-1 inline-flex items-center gap-1 self-start rounded-xs text-dense text-accent underline underline-offset-2 transition-colors hover:text-accent-hover print:hidden"
                >
                  <Icon icon={ArrowRight} size={14} />
                  {station.action.label}
                </Link>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
