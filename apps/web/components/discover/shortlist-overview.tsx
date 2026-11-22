import type { RunOut, ShortlistItemOut } from "@/lib/api/client";
import { formatCredits } from "@/lib/format";
import { CandidateBars, KpiRow, median, StatTile } from "@/components/insight";

/** The city a location record names: its first part, "Nashik" from "Nashik, India". */
function city(location: string): string {
  return location.split(",")[0].trim() || location;
}

/**
 * Where the candidates are headquartered, as one line of words. Cities with more than
 * one candidate are named with their count; the rest are counted together. Nothing is
 * charted: with one company per city, bars would all be the same length.
 */
function headquartersLine(ranked: ShortlistItemOut[]): string | null {
  const groups = new Map<string, number>();
  let missing = 0;
  for (const item of ranked) {
    const location = item.card.location?.value;
    if (!location) missing += 1;
    else groups.set(city(location), (groups.get(city(location)) ?? 0) + 1);
  }
  if (groups.size === 0) return null;
  const shared = [...groups].filter(([, count]) => count > 1).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const single = groups.size - shared.length;
  const parts = shared.map(([name, count]) => `${name} ${count}`);
  if (single > 0) {
    parts.push(shared.length > 0 ? `${single} other ${single === 1 ? "city" : "cities"}, one each` : `${single} ${single === 1 ? "city" : "cities"}, one company each`);
  }
  if (missing > 0) parts.push(`${missing} with no location returned`);
  return parts.join(" · ");
}

/** True when two or more candidates are scored and every score is the same. */
export function fitIsTied(ranked: ShortlistItemOut[]): boolean {
  const scored = ranked.flatMap((item) => (item.fit === null ? [] : [item.fit]));
  return scored.length > 1 && new Set(scored).size === 1;
}

/**
 * The slim band above the shortlist: four figures, then one line on where the candidates
 * are. The row-by-row comparison is one click away and closed by default, so the list of
 * companies stays the main thing on the page. Every figure is worked out from the cards
 * below, and each tile says how.
 */
export function ShortlistOverview({
  ranked,
  removed,
  run,
}: {
  ranked: ShortlistItemOut[];
  removed: ShortlistItemOut[];
  /** The search run, for what it cost. */
  run?: RunOut | null;
}) {
  const scored = ranked.flatMap((item) => (item.fit === null ? [] : [item.fit]));
  const medianFit = median(scored);
  const medianAssessable = Math.round(median(ranked.map((item) => item.assessable_pct)) ?? 0);
  const tied = fitIsTied(ranked);
  const headquarters = headquartersLine(ranked);

  return (
    <section aria-label="Shortlist summary" className="flex flex-col gap-2">
      <KpiRow label="Shortlist summary">
        <StatTile label="Candidates" value={ranked.length} note="No must-have fails on record" />
        <StatTile
          label="Removed"
          value={removed.length}
          note={removed.length > 0 ? "A record conflicts with a must-have" : "No verified must-have fail"}
        />
        {medianFit === null ? (
          <StatTile label="Fit and coverage" missing="Not scored" note="No criterion could be assessed" />
        ) : (
          <StatTile
            label={tied ? "Fit and coverage" : "Median fit and coverage"}
            value={
              <span className="font-mono text-lg">
                {Math.round(medianFit)} · {medianAssessable}%
              </span>
            }
            note={tied ? "Every candidate has the same fit. Coverage is the median" : "Fit, then share of criteria assessable"}
          />
        )}
        {run ? (
          <StatTile
            label="Search cost"
            value={formatCredits(run.cost.crustdata_credits)}
            unit="credits"
            note={`of a ${formatCredits(run.budget_credits)} credit budget`}
          />
        ) : null}
      </KpiRow>

      {headquarters ? (
        <p className="text-xs text-ink-secondary">
          <span className="text-ink-muted">Headquarters · </span>
          {headquarters}
        </p>
      ) : null}

      {ranked.length > 1 ? (
        <details className="group">
          <summary className="cursor-pointer self-start rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover">
            Compare coverage and size across the {ranked.length} candidates
          </summary>
          <div className="flex flex-col gap-2 pt-3">
            <CandidateBars
              caption="Shortlisted companies by fit, share of criteria assessable and estimated team size"
              fitTied={tied}
              rows={ranked.map((item, index) => ({
                id: item.id,
                rank: tied ? index + 1 : item.rank,
                name: item.name,
                href: `#company-${item.id}`,
                fit: item.fit,
                assessablePct: item.assessable_pct,
                headcount: item.card.headcount?.value ?? null,
              }))}
            />
            <p className="text-xs text-ink-secondary">
              The hatched part of a coverage bar is the share of criteria that could not be
              assessed. People is a profile-based estimate, not a payroll count
            </p>
          </div>
        </details>
      ) : null}
    </section>
  );
}
