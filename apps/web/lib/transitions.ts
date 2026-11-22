/**
 * Motion values for `motion/react`, mirroring the CSS tokens in app/globals.css.
 * One curve, three durations. Motion reports work or change; it never decorates.
 * Animate only opacity, transform and colours. Layout changes go through Motion's `layout`.
 */

export const ease = [0.22, 1, 0.36, 1] as const;

/** Seconds, because Motion takes seconds. */
export const duration = {
  /** Hover, press, toggle */
  fast: 0.14,
  /** Popover, status mark settling, tab change */
  base: 0.2,
  /** Row entrance, drawer, layout change */
  slow: 0.36,
  /** One-time changed-value highlight fading out */
  highlight: 1.2,
} as const;

/** Seconds between staggered rows. Six rows at most. */
export const stagger = 0.04;

/** Entrance distance in px. */
export const rise = 8;

/** The most rows that enter one after another; the rest appear with the last. */
export const STAGGER_LIMIT = 6;

export const transition = {
  fast: { duration: duration.fast, ease },
  base: { duration: duration.base, ease },
  slow: { duration: duration.slow, ease },
  /** Exits are always quicker than entrances and never travel. */
  exit: { duration: duration.fast, ease },
} as const;

/**
 * For a connector or a meter growing in: animate `scaleX` from 0 to 1 with
 * `transform-origin: left`, or `pathLength` on an SVG line. Never an animated width.
 */
export const draw = { duration: duration.slow, ease } as const;

/** Delay for the nth item of a staggered list, capped at STAGGER_LIMIT. */
export function staggerDelay(index: number): number {
  return Math.min(index, STAGGER_LIMIT - 1) * stagger;
}
