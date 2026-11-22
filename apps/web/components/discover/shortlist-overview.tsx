import type { ShortlistItemOut } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { CandidateBars, type CountBar, CountBars, KpiRow, median, StatTile } from "@/components/insight";

/** The city a location record names: its first part, "Nashik" from "Nashik, India". */
function city(location: string): string {
  return location.split(",")[0].trim() || location;
}

function headquarters(ranked: ShortlistItemOut[]): CountBar[] {
  const groups = new Map<string, string[]>();
  const missing: string[] = [];
  for (const item of ranked) {
    const location = item.card.location?.value;
    if (!location) missing.push(item.name);
    else groups.set(city(location), [...(groups.get(city(location)) ?? []), item.name]);
  }
  const rows: CountBar[] = [...groups].map(([label, names]) => ({ label, count: names.length, names }));
  if (missing.length > 0) {
    rows.push({ label: "Location not returned", count: missing.length, names: missing, missing: true });
  }
  return rows;
}

/**
 * The band above the shortlist: how many candidates there are, how many were removed,
 * where fit and coverage sit, then every candidate as a row of bars and the cities they
 * are headquartered in. Every figure here is worked out from the cards below, and each
 * tile says how; the sourced facts themselves stay on the cards with their chips.
 */
export function ShortlistOverview({
  ranked,
  removed,
}: {
  ranked: ShortlistItemOut[];
  removed: ShortlistItemOut[];
}) {
  const scored = ranked.flatMap((item) => (item.fit === null ? [] : [item.fit]));
  const medianFit = median(scored);
  const medianAssessable = median(ranked.map((item) => item.assessable_pct));
  const full = ranked.filter((item) => item.assessable_pct === 100).length;
  const latest = ranked.map((item) => item.card.last_updated).sort().at(-1);

  return (
    <section aria-labelledby="overview-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h3 id="overview-heading" className="text-sm font-medium text-ink">
          Overview
        </h3>
        <p className="font-mono text-2xs text-ink-muted">
          Worked out from the cards below · records retrieved up to{" "}
          {formatDateTime(latest) ?? "an unrecorded time"}
        </p>
      </div>

      <KpiRow label="Shortlist summary">
        <StatTile
          label="Candidates"
          value={ranked.length}
          note="No must-have fails on record"
        />
        <StatTile
          label="Removed"
          value={removed.length}
          note={removed.length > 0 ? "A record conflicts with a must-have" : "No verified must-have fail"}
        />
        {medianFit === null ? (
          <StatTile label="Median fit" missing="Not scored" note="No candidate had an assessable criterion" />
        ) : (
          <StatTile
            label="Median fit"
            value={Math.round(medianFit)}
            note={`Across ${scored.length} scored. Match to criteria, not returns`}
          />
        )}
        <StatTile
          label="Median assessable"
          value={`${Math.round(medianAssessable ?? 0)}%`}
          note={`${full} of ${ranked.length} fully assessable`}
        />
      </KpiRow>

      <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-2">
          <h4 className="text-xs font-medium text-ink-secondary">Fit and coverage by candidate</h4>
          <CandidateBars
            caption="Shortlisted companies by fit, share of criteria assessable and estimated team size"
            rows={ranked.map((item) => ({
              id: item.id,
              rank: item.rank,
              name: item.name,
              href: `#company-${item.id}`,
              fit: item.fit,
              assessablePct: item.assessable_pct,
              headcount: item.card.headcount?.value ?? null,
            }))}
          />
          <p className="text-xs text-ink-secondary">
            The hatched part of a coverage bar is the share of criteria that could not be assessed.
            People is a profile-based estimate, not a payroll count
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <h4 className="text-xs font-medium text-ink-secondary">Headquarters by city</h4>
          <CountBars
            caption="Shortlisted companies by headquarters city"
            unit="company"
            rows={headquarters(ranked)}
          />
          <p className="text-xs text-ink-secondary">
            From each company&apos;s location record. The source is on its card
          </p>
        </div>
      </div>
    </section>
  );
}
