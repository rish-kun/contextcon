import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { cleanSeries, type SeriesPoint } from "./chart-utils";

/** "135 in Nov 2025 to 160 in Nov 2026", the words behind a sparkline. */
export function seriesSummary(points: SeriesPoint[], unit = ""): string | null {
  const series = cleanSeries(points);
  if (series.length < 2) return null;
  const first = series[0];
  const last = series[series.length - 1];
  const suffix = unit ? ` ${unit}` : "";
  return `${first.value.toLocaleString("en-US")}${suffix} in ${formatDate(first.date.slice(0, 7))} to ${last.value.toLocaleString("en-US")}${suffix} in ${formatDate(last.date.slice(0, 7))}`;
}

/**
 * A small trend line beside a figure. It draws only the points the source returned, a
 * dashed line when the series is an estimate, and it always carries the same trend in
 * words for a reader who cannot see it. Fewer than two points draw nothing.
 */
export function Sparkline({
  points,
  estimate = false,
  label,
  width = 72,
  height = 24,
  className,
}: {
  points: SeriesPoint[];
  /** Draws the line dashed: the series is inferred, not recorded. */
  estimate?: boolean;
  /** What the line shows, in words: "Estimated headcount, 135 in Nov 2025 to 160 in Nov 2026". */
  label: string;
  width?: number;
  height?: number;
  className?: string;
}) {
  const series = cleanSeries(points);
  if (series.length < 2) return null;

  const pad = 4;
  const times = series.map((point) => Date.parse(point.date));
  const values = series.map((point) => point.value);
  const t0 = times[0];
  const t1 = times[times.length - 1];
  const low = Math.min(...values);
  const high = Math.max(...values);
  const x = (time: number) => pad + ((time - t0) / (t1 - t0 || 1)) * (width - pad * 2);
  const y = (value: number) =>
    high === low ? height / 2 : height - pad - ((value - low) / (high - low)) * (height - pad * 2);
  const path = series
    .map((point, index) => `${index ? "L" : "M"}${x(times[index]).toFixed(1)} ${y(point.value).toFixed(1)}`)
    .join(" ");
  const last = series.length - 1;

  return (
    <span className={cn("inline-flex shrink-0", className)}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
        <path
          d={path}
          fill="none"
          className="stroke-ink-secondary"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={estimate ? "3 3" : undefined}
        />
        <circle
          cx={x(times[last])}
          cy={y(values[last])}
          r={3}
          className="fill-ink stroke-surface"
          strokeWidth={1.5}
        />
      </svg>
      <span className="sr-only">{label}</span>
    </span>
  );
}
