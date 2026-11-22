/**
 * Wording and small formatters for investor discovery. The API sends coded values
 * ("series_a", "51-200", "equity venture") and short machine-written sentences; this is
 * where they become the words a reader sees, in the one date format the product uses.
 */
import type { InvestorSearchIn } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

export interface Option {
  value: string;
  label: string;
}

export const STAGE_OPTIONS: Option[] = [
  { value: "pre_seed", label: "Pre-seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C or later" },
  { value: "unfunded", label: "No outside funding yet" },
];

export const SIZE_OPTIONS: Option[] = [
  { value: "1-10", label: "1 to 10 people" },
  { value: "11-50", label: "11 to 50 people" },
  { value: "51-200", label: "51 to 200 people" },
  { value: "201-500", label: "201 to 500 people" },
  { value: "501-1000", label: "501 to 1,000 people" },
  { value: "1001+", label: "More than 1,000 people" },
];

export const FUNDING_OPTIONS: Option[] = [
  { value: "equity venture", label: "Venture equity" },
  { value: "equity growth", label: "Growth equity" },
  { value: "debt", label: "Debt" },
  { value: "grant", label: "Grant" },
];

/** "pre_ipo" → "Pre ipo": a plain fallback for coded values we do not list. */
function humanise(value: string): string {
  const words = value.replace(/[_-]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : value;
}

function labelFrom(options: Option[], value: string): string {
  return options.find((o) => o.value === value)?.label ?? humanise(value);
}

export const stageLabel = (value: string) => labelFrom(STAGE_OPTIONS, value);
export const sizeLabel = (value: string) => labelFrom(SIZE_OPTIONS, value);
export const fundingLabel = (value: string) => labelFrom(FUNDING_OPTIONS, value);

/** Adds the current value to a list of options when the API holds one we do not list. */
export function withCurrent(options: Option[], value: string, label: (v: string) => string) {
  if (!value || options.some((o) => o.value === value)) return options;
  return [...options, { value, label: label(value) }];
}

const ROUND_LABEL: Record<string, string> = {
  pre_seed: "Pre-seed",
  seed: "Seed",
  angel: "Angel",
  venture: "Venture",
  growth: "Growth",
  growth_equity: "Growth equity",
  private_equity: "Private equity",
  debt: "Debt",
  venture_debt: "Venture debt",
  grant: "Grant",
};

/** "series_a" → "Series A". Null when the record carries no round type. */
export function roundLabel(roundType: string | null): string | null {
  if (!roundType) return null;
  const key = roundType.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  const series = /^series_([a-z])$/.exec(key);
  if (series) return `Series ${series[1].toUpperCase()}`;
  return ROUND_LABEL[key] ?? humanise(roundType);
}

/** `$6.0M`, `$750K`. One precision per unit, so a column of amounts lines up. */
export function formatAmountUsd(amount: number): string {
  if (amount >= 1_000_000_000) return `$${(amount / 1_000_000_000).toFixed(1)}B`;
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${Math.round(amount / 1_000)}K`;
  return `$${Math.round(amount)}`;
}

/** Rewrites ISO dates inside a machine-written sentence: "latest 2025-04" → "latest Apr 2025". */
export function humaniseDates(text: string): string {
  return text.replace(/\b\d{4}-\d{2}(?:-\d{2})?\b/g, (iso) => formatDate(iso) ?? iso);
}

export function sentence(text: string): string {
  const clean = humaniseDates(text.trim());
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}

export type Compatibility = "compatible" | "incompatible" | "unknown";

export const COMPATIBILITY_LABEL: Record<Compatibility, string> = {
  compatible: "Compatible",
  incompatible: "Incompatible",
  unknown: "Unknown",
};

/**
 * The API sends compatibility as a sentence built by a rule. Anything the sentence does
 * not settle is read as unknown, so a new wording can never show up as a false "yes".
 */
export function classifyCompatibility(text: string): Compatibility {
  const t = text.trim().toLowerCase();
  if (!t || /unknown|not stated|not recorded/.test(t)) return "unknown";
  if (/^incompatible|records show only/.test(t)) return "incompatible";
  if (/^compatible|has made|\b(led|made|joined) \d+/.test(t)) return "compatible";
  return "unknown";
}

/** The reason under the compatibility mark, in plain words. */
export function compatibilityReason(text: string, sought: string): string {
  const t = text.trim();
  if (!t || /^(unknown|compatible|incompatible)$/i.test(t)) {
    return `The dated records do not say more about ${fundingLabel(sought).toLowerCase()}`;
  }
  // The rule names the kind by its code ("equity venture"); the reader sees its label.
  return sentence(t.replace(sought, fundingLabel(sought).toLowerCase()));
}

/** Profile as one line: "India · Series A · 51 to 200 people · Venture equity". */
export function profileLine(profile: InvestorSearchIn): string {
  return [
    profile.location,
    stageLabel(profile.stage),
    sizeLabel(profile.size),
    fundingLabel(profile.funding_sought),
  ].join(" · ");
}

/** Link back to the form with this profile filled in. */
export function editHref(profile: InvestorSearchIn): string {
  return `/app/investors/new?${new URLSearchParams({ ...profile }).toString()}`;
}
