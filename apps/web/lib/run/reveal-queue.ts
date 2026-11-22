/**
 * Pacing for one region of the live run view (the source ticker, the findings stream).
 *
 * Events arrive in bursts. Showing a burst at once is unreadable and trickling it slowly
 * would misstate time, so each region reveals at most one item per 150 ms and is never
 * more than 1.5 s behind what was received. Past that, everything older appears at once,
 * settled, with a count of what was skipped.
 *
 * The queue only ever delays. It never invents an item and never reorders: items are
 * identified by their event `seq`, and "revealed" is a single rising watermark.
 */

export interface RevealSnapshot {
  /** Events with `seq` at or below this are on screen. */
  upto: number;
  /** Events at or below this are drawn settled, with no entrance. */
  settledUpto: number;
  /** Received and not shown yet. Non-zero while paused or mid-burst. */
  held: number;
  /** The last time a burst was cut short: how many rows appeared at once. */
  skipped: { count: number; seq: number } | null;
}

export interface RevealOptions {
  /** One reveal per this many ms. */
  intervalMs?: number;
  /** The longest an item may wait. */
  maxDelayMs?: number;
  /** Reduced motion: no stagger, one settled batch per 400 ms. */
  reduced?: boolean;
  onChange?: (snapshot: RevealSnapshot) => void;
  /** Injected in tests. */
  now?: () => number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

const REDUCED_BATCH_MS = 400;

export class RevealQueue {
  private pending: { seq: number; at: number }[] = [];
  private upto = 0;
  private settledUpto = 0;
  private skipped: RevealSnapshot["skipped"] = null;
  private skippedAt = 0;
  private paused = false;
  private timer: unknown = null;
  private readonly intervalMs: number;
  private readonly maxDelayMs: number;
  private reduced: boolean;
  private readonly onChange: (snapshot: RevealSnapshot) => void;
  private readonly now: () => number;
  private readonly setTimer: (fn: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;

  constructor(options: RevealOptions = {}) {
    this.intervalMs = options.intervalMs ?? 150;
    this.maxDelayMs = options.maxDelayMs ?? 1500;
    this.reduced = options.reduced ?? false;
    this.onChange = options.onChange ?? (() => {});
    this.now = options.now ?? (() => Date.now());
    this.setTimer = options.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearTimer =
      options.clearTimer ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  }

  snapshot(): RevealSnapshot {
    return {
      upto: this.upto,
      settledUpto: this.settledUpto,
      held: this.pending.length,
      skipped: this.skipped,
    };
  }

  /**
   * Take one event. `backlog` marks history (sent before the stream went live, or older
   * than a few seconds on arrival): it is drawn settled, at once.
   */
  push(seq: number, backlog = false): void {
    if (seq <= this.upto || this.pending.some((item) => item.seq === seq)) return;
    if (backlog && this.pending.length === 0 && !this.paused) {
      this.upto = seq;
      this.settledUpto = seq;
      this.emit();
      return;
    }
    this.pending.push({ seq, at: this.now() });
    if (this.paused) {
      this.emit();
      return;
    }
    this.trim();
    this.emit();
    this.schedule();
  }

  setReduced(reduced: boolean): void {
    this.reduced = reduced;
  }

  setPaused(paused: boolean): void {
    if (this.paused === paused) return;
    this.paused = paused;
    if (paused) {
      this.cancel();
    } else {
      this.trim();
      this.schedule();
    }
    this.emit();
  }

  /** Show everything now, settled. Called when the run ends: nothing may keep arriving. */
  flush(): void {
    this.cancel();
    const last = this.pending.at(-1);
    if (last) {
      this.upto = last.seq;
      this.settledUpto = last.seq;
      this.pending = [];
    }
    this.emit();
  }

  dispose(): void {
    this.cancel();
    this.pending = [];
  }

  /** Cuts the backlog down to what can be shown inside the delay limit. */
  private trim(): void {
    const capacity = Math.max(1, Math.floor(this.maxDelayMs / this.intervalMs));
    const overdue = this.pending.findLastIndex((item) => this.now() - item.at > this.maxDelayMs);
    const excess = Math.max(this.pending.length - capacity, overdue + 1);
    if (excess <= 0) return;
    const cut = this.pending.splice(0, excess);
    const seq = cut[cut.length - 1].seq;
    this.upto = seq;
    this.settledUpto = seq;
    // Cuts that belong to one burst are counted together.
    const sameBurst = this.skipped !== null && this.now() - this.skippedAt <= this.maxDelayMs;
    this.skipped = { count: cut.length + (sameBurst ? (this.skipped?.count ?? 0) : 0), seq };
    this.skippedAt = this.now();
  }

  private schedule(): void {
    if (this.timer !== null || this.paused || this.pending.length === 0) return;
    this.timer = this.setTimer(
      () => {
        this.timer = null;
        this.step();
      },
      this.reduced ? REDUCED_BATCH_MS : this.intervalMs,
    );
  }

  private step(): void {
    if (this.paused) return;
    if (this.reduced) {
      // One batch, in place: nothing rises and nothing is staggered.
      const last = this.pending.at(-1);
      if (last) {
        this.upto = last.seq;
        this.settledUpto = last.seq;
        this.pending = [];
      }
    } else {
      this.trim();
      const next = this.pending.shift();
      if (next) this.upto = next.seq;
    }
    this.emit();
    this.schedule();
  }

  private cancel(): void {
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
  }

  private emit(): void {
    this.onChange(this.snapshot());
  }
}
