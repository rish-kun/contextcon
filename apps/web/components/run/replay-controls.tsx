"use client";

import { Pause, Play, RotateCcw } from "lucide-react";
import { formatDateTime } from "@/lib/format";
import { REPLAY_SPEEDS, type ReplaySpeed, type RunReplay } from "@/lib/run/use-run-activity";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Segmented } from "@/components/ui/toolbar";

/**
 * Stays on screen for the whole replay, so a recording is never mistaken for work
 * happening now.
 */
export function ReplayBanner({ startedAt, className }: { startedAt: string; className?: string }) {
  return (
    <p
      role="note"
      className={cn(
        "rounded-lg border border-dashed border-line-strong bg-surface-raised px-4 py-2 text-dense text-ink",
        className,
      )}
    >
      Replay of the run from {formatDateTime(startedAt) ?? "an earlier time"}
      <span className="text-ink-secondary"> · nothing is being fetched and no credits are spent</span>
    </p>
  );
}

const SPEED_OPTIONS = REPLAY_SPEEDS.map((speed) => ({ value: String(speed), label: `${speed}×` }));

/** Play or pause, the speed, and a scrubber with one tick per step. */
export function ReplayControls({ replay, className }: { replay: RunReplay; className?: string }) {
  const { playing, atEnd, position } = replay;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-2", className)}>
      <Button size="sm" onClick={playing ? replay.pause : replay.play}>
        <Icon icon={playing ? Pause : atEnd ? RotateCcw : Play} />
        {playing ? "Pause" : atEnd ? "Replay again" : "Play"}
      </Button>
      <Segmented
        label="Replay speed"
        value={String(replay.speed)}
        onChange={(value) => replay.setSpeed(Number(value) as ReplaySpeed)}
        options={SPEED_OPTIONS}
      />
      <div className="relative flex h-8 min-w-48 flex-1 items-center">
        <input
          type="range"
          min={0}
          max={1000}
          value={Math.round(position * 1000)}
          onChange={(event) => replay.seek(Number(event.target.value) / 1000)}
          aria-label="Position in the run"
          aria-valuetext={`${Math.round(position * 100)}% of the run`}
          className="h-1 w-full cursor-pointer accent-ink"
        />
        <span aria-hidden className="pointer-events-none absolute inset-x-2 bottom-0 h-2">
          {replay.ticks.map((tick) => (
            <span
              key={tick.stepId}
              title={tick.label}
              className="absolute bottom-0 h-1.5 w-px bg-line-strong"
              style={{ left: `${tick.share * 100}%` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}
