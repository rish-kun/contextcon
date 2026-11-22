/**
 * Words for the run view. Every string here names something an event stated: an endpoint
 * family, a source class, a reason a page was not read. Nothing here describes progress.
 */
import type { RunOut, StepOut } from "@/lib/api/client";
import { formatCredits, formatTime, plural } from "@/lib/format";
import { RELIABILITY_LABEL } from "@/lib/labels";
import type { TallyRow } from "@/lib/run/activity-store";
import type { ActivitySource } from "@/lib/run/types";
import type { ReliabilityClass } from "@/lib/types";

export const RUN_KIND_WORD: Record<RunOut["kind"], string> = {
  discover: "Discover",
  investor_discover: "Investor search",
  verify: "Verify",
  evaluate: "Evaluate",
  recheck: "Recheck",
};

export const ENDPOINT_LABEL: Record<string, string> = {
  company_identify: "Company identify",
  company_search: "Company search",
  company_enrich: "Company enrich",
  person_search: "Person search",
  job_search: "Job search",
  web_search: "Web search",
  web_fetch: "Web fetch",
};

/** The endpoint families each kind of run can use, in the order the run reaches them. */
export const ENDPOINTS_BY_KIND: Record<RunOut["kind"], string[]> = {
  discover: ["company_search", "company_enrich", "job_search"],
  investor_discover: ["company_search", "company_enrich"],
  verify: ["company_identify", "company_enrich", "person_search", "job_search", "web_search", "web_fetch"],
  recheck: [],
  evaluate: [],
};

/** What one endpoint row returned, in a phrase. Null when the events carried no count. */
export function tallyPhrase(row: TallyRow): string | null {
  const c = row.counts;
  switch (row.endpoint) {
    case "company_identify":
      return c.candidates !== undefined ? plural(c.candidates, "candidate") : null;
    case "company_search": {
      const matched = c.new ?? c.returned;
      return matched !== undefined ? `${matched} matched` : null;
    }
    case "company_enrich":
      return c.returned !== undefined
        ? `${c.returned} of ${c.requested ?? c.returned} returned`
        : null;
    case "person_search":
      return c.returned !== undefined ? plural(c.returned, "person", "people") : null;
    case "job_search":
      return c.postings !== undefined ? plural(c.postings, "posting") : null;
    case "web_search":
      return c.hits !== undefined ? plural(c.hits, "result") : null;
    case "web_fetch":
      return c.read !== undefined ? `${plural(c.read, "page")} read` : null;
    default:
      return null;
  }
}

/** The field groups an enrich call came back with, as the spec's sub-line. */
export function enrichBreakdown(row: TallyRow): string | null {
  if (row.endpoint !== "company_enrich") return null;
  const c = row.counts;
  const parts = [
    c.with_funding ? `funding for ${c.with_funding}` : null,
    c.with_headcount_series ? `headcount series for ${c.with_headcount_series}` : null,
    c.with_web_traffic ? `web traffic for ${c.with_web_traffic}` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : null;
}

const FAIL_REASON: Record<string, string> = {
  http_403: "403",
  timeout: "timed out",
  robots: "blocked by robots",
  empty: "the page was empty",
  too_large: "the page was too large",
  budget: "budget reached",
};

/** "could not be read · 403". */
export function failedReadText(source: ActivitySource): string {
  const reason = source.reason ? (FAIL_REASON[source.reason] ?? source.reason.replace(/_/g, " ")) : null;
  const verb = source.state === "skipped" ? "not read" : "could not be read";
  return reason ? `${verb} · ${reason}` : verb;
}

const KNOWN_CLASSES = new Set(Object.keys(RELIABILITY_LABEL));

export function reliabilityOf(sourceClass: string): ReliabilityClass {
  return (KNOWN_CLASSES.has(sourceClass) ? sourceClass : "data_provider") as ReliabilityClass;
}

export function sourceClassLabel(sourceClass: string): string {
  return RELIABILITY_LABEL[reliabilityOf(sourceClass)] ?? sourceClass.replace(/_/g, " ");
}

/** What the ticker calls a row: the domain, or the kind of Crustdata record. */
export function sourceName(source: ActivitySource): string {
  if (source.type === "crustdata_record") {
    const kind = source.title?.split(" · ").at(-1);
    return kind && kind !== source.title ? `Crustdata · ${kind}` : "Crustdata record";
  }
  return source.domain ?? "Unnamed page";
}

/** The record's subject, without the kind that `sourceName` already shows. */
export function sourceTitle(source: ActivitySource): string | null {
  if (!source.title) return null;
  if (source.type !== "crustdata_record") return source.title;
  const parts = source.title.split(" · ");
  return parts.length > 1 ? parts.slice(0, -1).join(" · ") : source.title;
}

/**
 * "read 2 s ago" for a minute, then per minute, then the clock time. Counted from the
 * event's own `at`, so pacing never changes what a row says about time.
 */
export function readAgo(at: string, nowMs: number): string {
  const then = Date.parse(at);
  if (!Number.isFinite(then)) return "";
  const seconds = Math.max(0, Math.floor((nowMs - then) / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return formatTime(at) ?? "";
}

/** `16:42:07`, in IST, for the run log. */
const CLOCK = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function clockTime(at: string | null | undefined): string {
  if (!at) return "";
  const date = new Date(at);
  return Number.isNaN(date.getTime()) ? "" : CLOCK.format(date);
}

/** Model usage. An amount under a cent is said to be under a cent, not shown as zero. */
export function modelUsd(value: number): string {
  if (value > 0 && value < 0.005) return "under $0.01";
  return `$${value.toFixed(2)}`;
}

/** What a finished step cost. Credits and model dollars are never added together. */
export function stepCost(step: StepOut): string | null {
  if (step.state !== "done") return null;
  if (step.from_cache) return "from cache · 0 cr";
  const parts: string[] = [];
  if (step.cost.crustdata_credits > 0) parts.push(`${formatCredits(step.cost.crustdata_credits)} cr`);
  if (step.cost.llm_usd > 0) parts.push(modelUsd(step.cost.llm_usd));
  return parts.length > 0 ? parts.join(" · ") : "0 cr";
}

/** A step that checks one claim. Its key ends in the claim's id. */
export function claimStepId(key: string): string | null {
  const split = key.indexOf(":");
  if (split < 0) return null;
  return /(^|\.)(claim|facts)$/.test(key.slice(0, split)) ? key.slice(split + 1) : null;
}

export const isRunTerminal = (run: Pick<RunOut, "state">) =>
  run.state === "done" || run.state === "failed";
