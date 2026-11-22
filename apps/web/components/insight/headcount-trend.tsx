"use client";

import { useId, useState } from "react";
import { formatDate } from "@/lib/format";
import type { Evidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EstimateLabel, SourceLine } from "@/components/dealproof";
import { cleanSeries, niceTicks, type SeriesPoint } from "./chart-utils";
import { useElementWidth } from "./hooks";
import { seriesSummary } from "./sparkline";

const HEIGHT = 176;
const MARGIN = { top: 20, right: 20, bottom: 28, left: 44 };

const monthOf = (iso: string) => formatDate(iso.slice(0, 7)) ?? iso;
const count = (value: number) => Math.round(value).toLocaleString("en-US");

/**
 * Headcount over time, from the provider's dated points. The whole series is an
 * estimate from professional profiles, so the line is dashed, the figure carries a
 * tilde, and the word Estimate with its basis sits in the heading. It is a signal of
 * operating scale and is never placed under a heading that implies revenue.
 *
 * Read it three ways: the line, the hover or arrow-key readout, and the table under it.
 */
export function HeadcountTrend({
  points,
  evidence,
  basis,
  title = "Headcount over time",
  className,
}: {
  points: SeriesPoint[];
  /** The source of the series. Required: no source, no chart. */
  evidence: Evidence[];
  /** Plain words: "from professional profiles, not a payroll count". */
  basis: string;
  title?: string;
  className?: string;
}) {
  const series = cleanSeries(points);
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);
  const width = useElementWidth(frame, 560);
  const [active, setActive] = useState<number | null>(null);
  const tableId = useId();

  if (series.length < 2) {
    return (
      <div className={cn("flex flex-col gap-1", className)}>
        <h4 className="text-sm font-medium text-ink">{title}</h4>
        <p className="text-dense text-ink-muted">
          {series.length === 1
            ? "The source returned one dated point, which is not a trend"
            : "No headcount history returned by the sources searched"}
        </p>
      </div>
    );
  }

  const times = series.map((point) => Date.parse(point.date));
  const values = series.map((point) => point.value);
  const ticks = niceTicks(Math.min(...values), Math.max(...values), 3);
  const low = ticks[0];
  const high = ticks[ticks.length - 1];
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 40);
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const t0 = times[0];
  const t1 = times[times.length - 1];
  const x = (time: number) => MARGIN.left + ((time - t0) / (t1 - t0 || 1)) * innerWidth;
  const y = (value: number) => MARGIN.top + (1 - (value - low) / (high - low || 1)) * innerHeight;
  const line = series
    .map((point, index) => `${index ? "L" : "M"}${x(times[index]).toFixed(1)} ${y(point.value).toFixed(1)}`)
    .join(" ");
  const baseline = MARGIN.top + innerHeight;
  const area = `${line} L${x(t1).toFixed(1)} ${baseline} L${x(t0).toFixed(1)} ${baseline} Z`;

  // Date labels: as many as fit without touching, always the first and the last point.
  const room = Math.max(2, Math.floor(innerWidth / 84));
  const stride = Math.ceil((series.length - 1) / (room - 1));
  const labelled = series
    .map((_, index) => index)
    .filter((index) => index === series.length - 1 || (index % stride === 0 && series.length - 1 - index >= stride / 2));

  const last = series.length - 1;
  const shown = active ?? last;
  const summary = seriesSummary(series, "people");

  function nearest(clientX: number, target: SVGElement) {
    const box = target.getBoundingClientRect();
    const px = clientX - box.left;
    let best = 0;
    for (let index = 1; index < times.length; index += 1) {
      if (Math.abs(x(times[index]) - px) < Math.abs(x(times[best]) - px)) best = index;
    }
    setActive(best);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    const from = active ?? last;
    if (event.key === "ArrowLeft") setActive(Math.max(0, from - 1));
    else if (event.key === "ArrowRight") setActive(Math.min(last, from + 1));
    else if (event.key === "Home") setActive(0);
    else if (event.key === "End") setActive(last);
    else if (event.key === "Escape") setActive(null);
    else return;
    event.preventDefault();
  }

  const readoutLeft = Math.min(Math.max(x(times[shown]), 56), width - 56);

  return (
    <figure className={cn("flex min-w-0 flex-col gap-2", className)}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h4 className="text-sm font-medium text-ink">{title}</h4>
        <EstimateLabel kind="estimate" basis={basis} showBasis>
          <span className="font-mono text-dense text-ink">{count(values[last])} people</span>
        </EstimateLabel>
      </figcaption>

      <div
        ref={setFrame}
        role="group"
        tabIndex={0}
        aria-label={`Estimated headcount, ${summary}. Use the left and right arrow keys to read each point`}
        onKeyDown={onKeyDown}
        onBlur={() => setActive(null)}
        className="relative rounded-md"
      >
        <svg
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          className="block touch-pan-y"
          aria-hidden
          onPointerMove={(event) => nearest(event.clientX, event.currentTarget)}
          onPointerDown={(event) => nearest(event.clientX, event.currentTarget)}
          onPointerLeave={() => setActive(null)}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={MARGIN.left}
                x2={width - MARGIN.right}
                y1={y(tick)}
                y2={y(tick)}
                className="stroke-line"
              />
              <text
                x={MARGIN.left - 8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                className="fill-ink-muted font-mono text-2xs"
              >
                {count(tick)}
              </text>
            </g>
          ))}
          {labelled.map((index) => (
            <text
              key={series[index].date}
              x={x(times[index])}
              y={HEIGHT - 8}
              textAnchor={index === 0 ? "start" : index === last ? "end" : "middle"}
              className="fill-ink-muted font-mono text-2xs"
            >
              {monthOf(series[index].date)}
            </text>
          ))}

          <path d={area} className="fill-ink/5" />
          <path
            d={line}
            fill="none"
            className="stroke-ink"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="5 4"
          />

          {active !== null ? (
            <line
              x1={x(times[active])}
              x2={x(times[active])}
              y1={MARGIN.top}
              y2={baseline}
              className="stroke-line-strong"
            />
          ) : null}
          {series.map((point, index) =>
            index === shown || index === last || series.length <= 12 ? (
              <circle
                key={point.date}
                cx={x(times[index])}
                cy={y(point.value)}
                r={index === shown ? 4.5 : index === last ? 4 : 2.5}
                className={cn("stroke-surface", index === shown || index === last ? "fill-ink" : "fill-ink-secondary")}
                strokeWidth={2}
              />
            ) : null,
          )}
        </svg>

        {active !== null ? (
          <div
            className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-xs bg-ink px-2 py-1 text-center whitespace-nowrap shadow-md"
            style={{ left: readoutLeft }}
          >
            <p className="font-mono text-xs font-medium text-ink-inverse">~{count(values[active])} people</p>
            <p className="font-mono text-2xs text-ink-inverse/80">{monthOf(series[active].date)} · Estimate</p>
          </div>
        ) : null}
        <p aria-live="polite" className="sr-only">
          {active !== null
            ? `${monthOf(series[active].date)}: about ${count(values[active])} people, estimate`
            : ""}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <SourceLine evidence={evidence} />
        <details className="group text-xs text-ink-secondary">
          <summary
            aria-controls={tableId}
            className="cursor-pointer rounded-xs underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink"
          >
            Show the {series.length} points as a table
          </summary>
          <table id={tableId} className="mt-2 border-collapse text-dense text-ink">
            <thead>
              <tr className="text-left text-xs text-ink-muted">
                <th scope="col" className="pr-6 font-normal">
                  Date
                </th>
                <th scope="col" className="text-right font-normal">
                  People, estimate
                </th>
              </tr>
            </thead>
            <tbody>
              {series.map((point) => (
                <tr key={point.date} className="border-t border-line">
                  <td className="py-1 pr-6 font-mono text-xs">{formatDate(point.date)}</td>
                  <td className="py-1 text-right font-mono text-xs">~{count(point.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </figure>
  );
}
