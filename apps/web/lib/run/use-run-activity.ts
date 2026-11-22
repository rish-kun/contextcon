"use client";

/**
 * Following a run: the stream, the activity log, the pacing queues and the clocks.
 *
 *   const { feed, setPaused } = useRunActivity(seed, { onSettled });
 *   <RunView run={feed.run} feed={feed} onPause={setPaused} … />
 *
 * `RunFeed` is the same thing without React, for a provider that already owns the run's
 * subscription (the case context). `useRunReplay` plays a finished run's stored events
 * back through the same snapshot shape, so the live view and the replay are one component.
 */
import { useReducedMotion } from "motion/react";
import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import {
  isFixtureMode,
  subscribeRun,
  type RunOut,
  type RunStreamEvent,
  type StepOut,
} from "@/lib/api/client";
import { withStepSpend } from "@/lib/api/run-cost";
import { appendActivities, regionOf, type Region } from "./activity-store";
import { RevealQueue, type RevealSnapshot } from "./reveal-queue";
import type { Activity } from "./types";

/** Events older than this on arrival are history: drawn settled, never animated in. */
const BACKLOG_AGE_MS = 3000;

export interface RunFeedSnapshot {
  run: RunOut | null;
  /** Every activity received, oldest first. */
  events: Activity[];
  /** Per paced region: events at or below this `seq` are on screen. */
  upto: Record<Region, number>;
  /** Per paced region: events at or below this `seq` are drawn without an entrance. */
  settled: Record<Region, number>;
  /** Per paced region: the last burst that was shown at once, and how many rows it held. */
  skipped: Record<Region, RevealSnapshot["skipped"]>;
  /** Received and not shown yet, across regions. */
  held: number;
  paused: boolean;
  terminal: boolean;
  /** When the clock for this run started, in ms. */
  startedAt: number | null;
  /** When it stopped, in ms. Null while the run is going. */
  endedAt: number | null;
}

export const EMPTY_FEED: RunFeedSnapshot = {
  run: null,
  events: [],
  upto: { sources: 0, findings: 0 },
  settled: { sources: 0, findings: 0 },
  skipped: { sources: null, findings: null },
  held: 0,
  paused: false,
  terminal: false,
  startedAt: null,
  endedAt: null,
};

const isTerminal = (run: RunOut | null) => run?.state === "done" || run?.state === "failed";

function mergeStep(steps: StepOut[], step: StepOut): StepOut[] {
  const next = steps.filter((s) => s.id !== step.id);
  next.push(step);
  return next.sort((a, b) => a.position - b.position);
}

/** One run being followed. Create, `start()`, and `stop()` when done. */
export class RunFeed {
  private snapshot: RunFeedSnapshot;
  private listeners = new Set<(snapshot: RunFeedSnapshot) => void>();
  private queues: Record<Region, RevealQueue>;
  private unsubscribe: (() => void) | null = null;
  private readonly runId: string;
  private readonly onEvent: ((event: RunStreamEvent) => void) | undefined;

  constructor(
    seed: RunOut,
    options: { reduced?: boolean; onEvent?: (event: RunStreamEvent) => void } = {},
  ) {
    this.runId = seed.id;
    this.onEvent = options.onEvent;
    const created = Date.parse(seed.created_at);
    // A replayed fixture run carries an old start time, so its clock starts when watching does.
    const startedAt = isFixtureMode || !Number.isFinite(created) ? Date.now() : created;
    this.snapshot = { ...EMPTY_FEED, run: seed, startedAt };
    const queue = (region: Region) =>
      new RevealQueue({
        reduced: options.reduced,
        onChange: (reveal) => this.onReveal(region, reveal),
      });
    this.queues = { sources: queue("sources"), findings: queue("findings") };
  }

  start(): void {
    if (this.unsubscribe) return;
    this.unsubscribe = subscribeRun(this.runId, (event) => this.handle(event));
  }

  stop(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.queues.sources.dispose();
    this.queues.findings.dispose();
    this.listeners.clear();
  }

  subscribe(listener: (snapshot: RunFeedSnapshot) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getSnapshot(): RunFeedSnapshot {
    return this.snapshot;
  }

  /** Freeze the paced regions. Events keep arriving and are counted as held. */
  setPaused(paused: boolean): void {
    this.queues.sources.setPaused(paused);
    this.queues.findings.setPaused(paused);
    this.set({ paused });
  }

  setReduced(reduced: boolean): void {
    this.queues.sources.setReduced(reduced);
    this.queues.findings.setReduced(reduced);
  }

  private set(patch: Partial<RunFeedSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener(this.snapshot);
  }

  private onReveal(region: Region, reveal: RevealSnapshot): void {
    const other = region === "sources" ? this.queues?.findings : this.queues?.sources;
    this.set({
      upto: { ...this.snapshot.upto, [region]: reveal.upto },
      settled: { ...this.snapshot.settled, [region]: reveal.settledUpto },
      skipped: { ...this.snapshot.skipped, [region]: reveal.skipped },
      held: reveal.held + (other?.snapshot().held ?? 0),
    });
  }

  private handle(event: RunStreamEvent): void {
    this.onEvent?.(event);
    if (event.event === "live") return;
    if (event.event === "activity") {
      const events = appendActivities(this.snapshot.events, [event.data]);
      if (events === this.snapshot.events) return;
      this.set({ events });
      const region = regionOf(event.data);
      if (region) {
        // History is drawn settled. `EventSource` hides the stream's `: live` comment, so
        // an event's own age is what tells a backlog from something that just happened.
        const age = Date.now() - Date.parse(event.data.at);
        this.queues[region].push(event.data.seq, !(age < BACKLOG_AGE_MS));
      }
      return;
    }
    const current = this.snapshot.run;
    if (event.event === "step") {
      // The header's spend never lags the step rows (see `withStepSpend`).
      if (current)
        this.set({ run: withStepSpend({ ...current, steps: mergeStep(current.steps, event.data) }) });
      return;
    }
    // The stream's `run` events carry no steps; a polling snapshot carries all of them.
    const steps = event.data.steps.length > 0 ? event.data.steps : (current?.steps ?? []);
    const run = withStepSpend({
      ...event.data,
      steps: [...steps].sort((a, b) => a.position - b.position),
    });
    if (isTerminal(run) && !this.snapshot.terminal) {
      // A finished run must not keep "arriving": everything held appears at once.
      this.queues.sources.setPaused(false);
      this.queues.findings.setPaused(false);
      this.queues.sources.flush();
      this.queues.findings.flush();
      this.set({ run, terminal: true, paused: false, endedAt: Date.now() });
    } else {
      this.set({ run });
    }
  }
}

/** A run that has not reported yet is shown as running from an empty step list. */
export function asLiveSeed(run: RunOut): RunOut {
  return isTerminal(run) ? { ...run, state: "running", steps: [], finished_at: null } : run;
}

/**
 * Follow one run for as long as the component is mounted. `onSettled` fires once, when
 * the run reports done or failed.
 */
export function useRunActivity(
  seed: RunOut | null,
  options: { onSettled?: (run: RunOut) => void } = {},
): { feed: RunFeedSnapshot; setPaused: (paused: boolean) => void } {
  const reduced = useReducedMotion() ?? false;
  const [feed, setFeed] = useState<RunFeedSnapshot>(EMPTY_FEED);
  const feedRef = useRef<RunFeed | null>(null);
  const settle = useEffectEvent((run: RunOut) => options.onSettled?.(run));
  const seedId = seed?.id ?? null;
  const seedRef = useRef(seed);
  useEffect(() => {
    seedRef.current = seed;
  });

  useEffect(() => {
    const first = seedRef.current;
    if (!seedId || !first) return;
    let settled = false;
    const runFeed = new RunFeed(asLiveSeed(first), {
      onEvent: (event) => {
        if (event.event === "run" && isTerminal(event.data) && !settled) {
          settled = true;
          // After the feed has folded the terminal event into its snapshot.
          queueMicrotask(() => settle(event.data));
        }
      },
    });
    feedRef.current = runFeed;
    setFeed(runFeed.getSnapshot());
    const off = runFeed.subscribe(setFeed);
    runFeed.start();
    return () => {
      off();
      runFeed.stop();
      feedRef.current = null;
    };
  }, [seedId]);

  useEffect(() => {
    feedRef.current?.setReduced(reduced);
  }, [reduced, seedId]);

  const setPaused = useCallback((paused: boolean) => feedRef.current?.setPaused(paused), []);
  return { feed, setPaused };
}

/** A clock that re-renders its caller. Stops when `active` is false. */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const tick = () => setNow(Date.now());
    const timer = setInterval(tick, intervalMs);
    return () => clearInterval(timer);
  }, [active, intervalMs]);
  return now;
}

/* ───────────────────────── Replay ───────────────────────── */

export const REPLAY_SPEEDS = [1, 8, 30] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

/** Real gaps longer than this are shortened, so a slow call does not stall a replay. */
const LONG_GAP_MS = 2000;
const LONG_GAP_AS_MS = 600;
const TAIL_MS = 800;

interface Timeline {
  /** Compressed offset of each event from the start, in ms. */
  offsets: number[];
  duration: number;
  /** One tick per step, at the offset of its first event. */
  ticks: { stepId: string; label: string; share: number }[];
}

function buildTimeline(run: RunOut, events: Activity[]): Timeline {
  const offsets: number[] = [];
  let clock = 0;
  let previous: number | null = null;
  for (const event of events) {
    const at = Date.parse(event.at);
    const gap = previous === null || !Number.isFinite(at) ? 0 : Math.max(0, at - previous);
    clock += gap > LONG_GAP_MS ? LONG_GAP_AS_MS : gap;
    if (Number.isFinite(at)) previous = at;
    offsets.push(clock);
  }
  const duration = clock + TAIL_MS;
  const ticks: Timeline["ticks"] = [];
  for (const step of run.steps) {
    const index = events.findIndex((event) => event.step_id === step.id);
    if (index >= 0) ticks.push({ stepId: step.id, label: step.label, share: offsets[index] / duration });
  }
  return { offsets, duration, ticks };
}

const NO_COST = { crustdata_credits: 0, llm_usd: 0, input_tokens: 0, output_tokens: 0, unknown_cost_calls: 0 };

/** The run as it stood `shown` events in: each step pending, running or in its final state. */
function runAt(run: RunOut, events: Activity[], shown: number, atEnd: boolean): RunOut {
  if (atEnd) return run;
  const first = new Map<string, number>();
  const last = new Map<string, number>();
  events.forEach((event, index) => {
    if (!event.step_id) return;
    if (!first.has(event.step_id)) first.set(event.step_id, index);
    last.set(event.step_id, index);
  });
  const steps = run.steps.map((step): StepOut => {
    const start = first.get(step.id);
    const end = last.get(step.id);
    if (start === undefined || end === undefined) {
      // A step that recorded nothing settles when the step after it has started.
      const laterStarted = run.steps.some(
        (other) => other.position > step.position && (first.get(other.id) ?? Infinity) < shown,
      );
      return laterStarted ? step : { ...step, state: "pending", result: null, error: null, cost: NO_COST };
    }
    if (shown <= start) return { ...step, state: "pending", result: null, error: null, cost: NO_COST };
    // Still running until something after its last event has been shown.
    if (shown <= end + 1) return { ...step, state: "running", result: null, error: null, cost: NO_COST };
    return step;
  });
  return { ...run, state: "running", finished_at: null, error: null, cost: NO_COST, steps };
}

export interface RunReplay {
  feed: RunFeedSnapshot;
  /** The recorded time at the replay position, for "read 2 s ago". */
  nowMs: number;
  playing: boolean;
  speed: ReplaySpeed;
  /** Position between 0 and 1. */
  position: number;
  ticks: Timeline["ticks"];
  atEnd: boolean;
  play: () => void;
  pause: () => void;
  seek: (position: number) => void;
  setSpeed: (speed: ReplaySpeed) => void;
}

/**
 * Plays a finished run's stored events back at a chosen speed. Nothing is fetched while
 * it plays and nothing is spent: the events and the run are the ones already loaded.
 */
export function useRunReplay(run: RunOut, events: Activity[]): RunReplay {
  const timeline = useMemo(() => buildTimeline(run, events), [run, events]);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(8);
  const [elapsed, setElapsed] = useState(0);
  /** Rows shown at the last seek are drawn settled; rows after it animate in. */
  const [settledSeq, setSettledSeq] = useState(0);

  const elapsedRef = useRef(0);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let previous = performance.now();
    const tick = (time: number) => {
      const next = Math.min(timeline.duration, elapsedRef.current + (time - previous) * speed);
      previous = time;
      elapsedRef.current = next;
      setElapsed(next);
      if (next >= timeline.duration) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, timeline.duration]);

  const shown = useMemo(() => {
    let count = 0;
    while (count < timeline.offsets.length && timeline.offsets[count] <= elapsed) count += 1;
    return count;
  }, [timeline.offsets, elapsed]);
  const atEnd = elapsed >= timeline.duration;

  const feed = useMemo<RunFeedSnapshot>(() => {
    const visible = events.slice(0, shown);
    const lastSeq = visible.at(-1)?.seq ?? 0;
    const settled = atEnd && !playing ? lastSeq : Math.min(settledSeq, lastSeq);
    const startedAt = Date.parse(events[0]?.at ?? run.created_at);
    return {
      run: runAt(run, events, shown, atEnd),
      events: visible,
      upto: { sources: lastSeq, findings: lastSeq },
      settled: { sources: settled, findings: settled },
      skipped: { sources: null, findings: null },
      held: 0,
      paused: false,
      terminal: atEnd,
      startedAt: Number.isFinite(startedAt) ? startedAt : null,
      endedAt: null,
    };
  }, [events, shown, atEnd, playing, settledSeq, run]);

  // The recorded clock: the time of the last event shown, plus the time played since it.
  const lastShownAt = shown > 0 ? Date.parse(events[shown - 1].at) : Date.parse(events[0]?.at ?? run.created_at);
  const since = shown > 0 ? elapsed - timeline.offsets[shown - 1] : 0;
  const nowMs = (Number.isFinite(lastShownAt) ? lastShownAt : 0) + Math.max(0, since);

  const seek = useCallback(
    (position: number) => {
      const target = Math.min(1, Math.max(0, position)) * timeline.duration;
      let count = 0;
      while (count < timeline.offsets.length && timeline.offsets[count] <= target) count += 1;
      setSettledSeq(events[count - 1]?.seq ?? 0);
      elapsedRef.current = target;
      setElapsed(target);
    },
    [events, timeline],
  );

  const play = useCallback(() => {
    if (elapsedRef.current >= timeline.duration) {
      setSettledSeq(0);
      elapsedRef.current = 0;
      setElapsed(0);
    }
    setPlaying(true);
  }, [timeline.duration]);

  return {
    feed,
    nowMs,
    playing,
    speed,
    position: timeline.duration > 0 ? elapsed / timeline.duration : 0,
    ticks: timeline.ticks,
    atEnd,
    play,
    pause: useCallback(() => setPlaying(false), []),
    seek,
    setSpeed,
  };
}
