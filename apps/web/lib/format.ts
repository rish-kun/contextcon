/**
 * One format per kind of value, everywhere.
 * Dates: `14 Oct 2026`, or `Oct 2026` when only the month is known, or `2014` for a year.
 * Times: `14 Oct 2026, 16:42 IST`.
 */

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/**
 * Formats an ISO date of any precision: `2026-10-14`, `2026-10` or `2026`.
 * A full timestamp is cut to its date part. Returns null when the input is not a date.
 */
export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const match = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(value);
  if (!match) return null;
  const [, year, month, day] = match;
  if (!month) return year;
  const monthName = MONTHS[Number(month) - 1];
  if (!monthName) return null;
  if (!day) return `${monthName} ${year}`;
  return `${Number(day)} ${monthName} ${year}`;
}

/** "as of 12 Mar 2014", or "as of unknown date". Never blank. */
export function formatAsOf(value: string | null | undefined): string {
  return `as of ${formatDate(value) ?? "unknown date"}`;
}

const IST = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function istParts(value: string): Record<string, string> | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts: Record<string, string> = {};
  for (const part of IST.formatToParts(date)) parts[part.type] = part.value;
  return parts;
}

/** `22 Nov 2026, 16:42 IST` from an ISO timestamp. Always shown in IST, on server and client. */
export function formatDateTime(value: string | null | undefined): string | null {
  if (!value) return null;
  const p = istParts(value);
  if (!p) return null;
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute} IST`;
}

/** `16:42 IST` */
export function formatTime(value: string | null | undefined): string | null {
  if (!value) return null;
  const p = istParts(value);
  if (!p) return null;
  return `${p.hour}:${p.minute} IST`;
}

/** `22 Nov, 16:39` for dense tables where the year is clear from context. */
export function formatShortDateTime(
  value: string | null | undefined,
): string | null {
  if (!value) return null;
  const p = istParts(value);
  if (!p) return null;
  return `${p.day} ${p.month}, ${p.hour}:${p.minute}`;
}

/** `$0.42`. Model usage is always in US dollars with two decimals. */
export function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

/** `86` or `1,204`. Crustdata credits are whole numbers. */
export function formatCredits(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

/** `2 min 14 s`, or `48 s` under a minute. */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes === 0 ? `${rest} s` : `${minutes} min ${rest} s`;
}

/** `70%` from a share between 0 and 1. */
export function formatShare(share: number): string {
  return `${Math.round(share * 100)}%`;
}

/** "1 check" / "3 checks" */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
