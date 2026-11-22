/** One dated value of a series. `date` is an ISO date, `value` the figure on that date. */
export interface SeriesPoint {
  date: string;
  value: number;
}

/** Points with a readable date and a finite value, oldest first. */
export function cleanSeries(points: SeriesPoint[]): SeriesPoint[] {
  return points
    .filter((point) => Number.isFinite(Date.parse(point.date)) && Number.isFinite(point.value))
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** Round axis values that cover `min` to `max` in about `count` steps. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    const pad = Math.max(1, Math.abs(min) * 0.1);
    min -= pad;
    max += pad;
  }
  const raw = (max - min) / Math.max(1, count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const start = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let tick = start; tick < max + step; tick += step) {
    ticks.push(Math.round(tick * 1e6) / 1e6);
    if (tick >= max) break;
  }
  return ticks;
}

/** The middle value of a list. Null for an empty list. */
export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
