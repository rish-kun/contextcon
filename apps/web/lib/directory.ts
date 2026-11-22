"use client";

import {
  getThesis,
  listTheses,
  type CaseDetail,
  type CaseSummary,
  type ShortlistItemOut,
  type ThesisOut,
  type ThesisSummary,
} from "@/lib/api/client";
import { useLoad, type Load } from "@/lib/use-load";
import { withAssessment, type Workspace } from "@/lib/workspace";

/**
 * Every company DealProof has seen, composed in the browser: each case, plus each company
 * a screening shortlisted or removed. There is no directory endpoint yet, so the shortlist
 * of each of the most recent screenings is read one by one, up to this limit.
 */
export const SCREENING_DETAIL_LIMIT = 12;

export interface Screenings {
  theses: ThesisSummary[];
  /** Full screenings, by id, for the most recent ones that have a shortlist. */
  details: Record<string, ThesisOut>;
  /** Screenings with a shortlist that were not read: beyond the limit, or failed. */
  unread: number;
}

async function readScreenings(): Promise<Screenings> {
  const theses = [...(await listTheses())].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const withShortlist = theses.filter((thesis) => thesis.shortlist_count > 0);
  const within = withShortlist.slice(0, SCREENING_DETAIL_LIMIT);
  const settled = await Promise.allSettled(within.map((thesis) => getThesis(thesis.id)));
  const details: Record<string, ThesisOut> = {};
  settled.forEach((result, index) => {
    if (result.status === "fulfilled") details[within[index].id] = result.value;
  });
  return { theses, details, unread: withShortlist.length - Object.keys(details).length };
}

export function useScreenings(): [Load<Screenings>, () => void] {
  return useLoad("screenings", readScreenings, "The screenings were not returned");
}

export interface CompanyRow {
  key: string;
  name: string;
  domain: string | null;
  hq: string | null;
  /** A count from professional profiles: an estimate, never a payroll figure. */
  headcount: number | null;
  headcountBasis: string | null;
  fit: number | null;
  /** Share of criteria that could be assessed, 0 to 100. Null when nothing was scored. */
  assessablePct: number | null;
  /** Why there is no fit number, in words. */
  fitNote: string | null;
  screening: { id: string; text: string } | null;
  /** Set when the company has a case. */
  item: CaseSummary | null;
  detail: CaseDetail | undefined;
  /** Set when the company came from a shortlist, so a case can be opened from it. */
  shortlist: ShortlistItemOut | null;
  updatedAt: string | null;
}

export function hostOf(website: string | null | undefined): string | null {
  if (!website) return null;
  return website.replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "") || null;
}

const FIT_NOTE: Record<string, string> = {
  identity_unresolved: "Waits on identity",
  awaiting_strategy_criteria: "No criteria set",
  unavailable: "Fit unavailable",
};

const DEFAULT_BASIS = "from professional profiles, not a payroll count";

/** Cases first as their own rows, then every shortlisted company that has no case. */
export function companyRows(workspace: Workspace, screenings: Screenings | null): CompanyRow[] {
  const found = new Map<string, { item: ShortlistItemOut; thesis: ThesisOut }>();
  const shortlistOnly = new Map<number, CompanyRow>();

  for (const summary of screenings?.theses ?? []) {
    const thesis = screenings?.details[summary.id];
    if (!thesis) continue;
    for (const entry of thesis.shortlist) {
      if (entry.case_id) {
        if (!found.has(entry.case_id)) found.set(entry.case_id, { item: entry, thesis });
        continue;
      }
      if (shortlistOnly.has(entry.crustdata_company_id)) continue;
      shortlistOnly.set(entry.crustdata_company_id, {
        key: `shortlist:${entry.id}`,
        name: entry.name,
        domain: hostOf(entry.domain),
        hq: entry.card.location?.value ?? null,
        headcount: entry.card.headcount?.value ?? null,
        headcountBasis: entry.card.headcount?.estimate_basis ?? null,
        fit: entry.excluded ? null : entry.fit,
        assessablePct: entry.excluded ? null : entry.assessable_pct,
        fitNote: entry.excluded
          ? `Removed · ${entry.exclusion_reason ?? "failed a must-have"}`
          : entry.fit === null
            ? (entry.fit_unavailable_reason ?? "Fit unavailable")
            : null,
        screening: { id: thesis.id, text: thesis.text },
        item: null,
        detail: undefined,
        shortlist: entry,
        updatedAt: entry.card.last_updated,
      });
    }
  }

  const cases: CompanyRow[] = workspace.cases.map((raw) => {
    const detail = workspace.details[raw.id];
    const item = withAssessment(raw, detail);
    const origin = found.get(item.id);
    const profile = detail?.profile ?? null;
    const card = origin?.item.card;
    const headcount = profile?.headcount ?? card?.headcount ?? null;
    const thesisId = detail?.opportunity.thesis_id ?? origin?.thesis.id ?? null;
    const thesisText = detail?.opportunity.thesis_text ?? origin?.thesis.text ?? null;
    const scored = item.fit_state === "scored" && item.fit !== null;
    return {
      key: `case:${item.id}`,
      name: item.name,
      domain: hostOf(item.website) ?? hostOf(profile?.domain?.value) ?? hostOf(origin?.item.domain),
      hq: profile?.headquarters?.value ?? profile?.country?.value ?? card?.location?.value ?? null,
      headcount: headcount?.value ?? null,
      headcountBasis: headcount?.estimate_basis ?? null,
      fit: scored ? item.fit : null,
      assessablePct: scored ? (item.assessable_pct ?? 0) : null,
      fitNote: scored ? null : item.fit_state ? (FIT_NOTE[item.fit_state] ?? "Fit unavailable") : "Not assessed yet",
      screening: thesisId ? { id: thesisId, text: thesisText ?? "Screening" } : null,
      item,
      detail,
      shortlist: origin?.item ?? null,
      updatedAt: item.updated_at,
    };
  });

  return [...cases, ...shortlistOnly.values()].map((row) => ({
    ...row,
    headcountBasis: row.headcount === null ? null : (row.headcountBasis ?? DEFAULT_BASIS),
  }));
}
