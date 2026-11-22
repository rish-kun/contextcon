"use client";

import { useState } from "react";
import type { InvestorSearchOut } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { sentence } from "./format";
import { KpiRow, RankedDetail, StatTile } from "@/components/insight";
import { InvestorDetail, InvestorRow } from "./investor-detail";
import { buildAxis } from "./round-axis";

/** "Searched 22 Nov 2026 across 40 comparable companies", from the API's own scope note. */
export function scopeLine(search: InvestorSearchOut): string {
  if (search.scope_note) return sentence(search.scope_note);
  const on = formatDate(search.searched_at ?? search.created_at);
  return `Searched ${on} across ${plural(search.comparables_considered, "comparable company", "comparable companies")}`;
}

/** The fixed line under every shortlist. It stays in view while the list scrolls. */
export function RankingCaveat({ className }: { className?: string }) {
  return (
    <p
      className={cn(
        "sticky bottom-0 z-10 border-t border-line-strong bg-paper py-3 text-dense text-ink-secondary",
        className,
      )}
    >
      This ranking describes past investments. It does not predict whether an investor will
      invest. No personal contact details are collected.
    </p>
  );
}

/**
 * The ranked investors of one search: the list on the left, the selected investor's
 * record on the right. Every entry is here because a dated funding record connects it to
 * a comparable company; the order is a count of those records weighted toward recent
 * ones, and nothing more. No score is shown, because the order is not a prediction.
 */
export function Shortlist({ search }: { search: InvestorSearchOut }) {
  const entries = [...search.entries].sort((a, b) => a.rank - b.rank);
  const [selectedId, setSelectedId] = useState<string | null>(entries[0]?.id ?? null);
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const rounds = entries.flatMap((entry) => entry.comparable_rounds);
  const companies = new Set(rounds.map((round) => round.company_id));
  const latestRound = rounds.map((round) => round.date).sort().at(-1) ?? null;
  const axis = buildAxis(entries, search.searched_at ?? search.created_at);
  const scope = scopeLine(search);

  /** Duplicate flags point one way in the data; the reader sees them on both entries. */
  const duplicatesOf = (id: string) => {
    const own = byId.get(byId.get(id)?.possible_duplicate_of ?? "");
    const pointing = entries.filter((e) => e.possible_duplicate_of === id);
    return own ? [own, ...pointing] : pointing;
  };

  return (
    <section aria-labelledby="shortlist-heading" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="shortlist-heading" className="text-xl font-medium text-ink">
          {plural(entries.length, "investor")}
          <span className="font-normal text-ink-secondary">
            {" · "}from{" "}
            {plural(companies.size, "comparable company", "comparable companies")} with dated
            rounds
          </span>
        </h2>
        <p className="max-w-3xl text-dense text-ink-secondary">
          {scope}. Ranked by comparable investments found in the record, recent ones counting
          more. An investor is listed only where a dated funding record supports it, and any
          message to an investor waits for a person&apos;s approval.
        </p>
      </div>

      <KpiRow label="Investor search summary">
        <StatTile label="Investors" value={entries.length} note="Each named in a dated funding record" />
        <StatTile
          label="Comparable companies"
          value={companies.size}
          note={`Of ${search.comparables_considered} read in this search`}
        />
        <StatTile label="Dated rounds" value={rounds.length} note="Counted once per investor named" />
        {latestRound ? (
          <StatTile
            label="Latest round found"
            value={<span className="font-mono text-lg">{formatDate(latestRound)}</span>}
            note="Within the scope of this search"
          />
        ) : (
          <StatTile label="Latest round found" missing="None found" />
        )}
      </KpiRow>

      <RankedDetail
        items={entries}
        getId={(entry) => entry.id}
        selectedId={selectedId}
        onSelect={setSelectedId}
        label="Investors, ranked by comparable investments found in the record"
        listHeader={
          <p className="flex items-baseline justify-between gap-3 text-xs text-ink-muted">
            <span>Investor · dated comparable rounds</span>
            {axis ? (
              <span className="font-mono text-2xs">
                {axis.years[0]} to {formatDate(axis.searchedOn)}
              </span>
            ) : null}
          </p>
        }
        renderRow={(entry) => <InvestorRow entry={entry} axis={axis} />}
        renderDetail={(entry) => (
          <InvestorDetail
            entry={entry}
            axis={axis}
            fundingSought={search.profile.funding_sought}
            scope={scope}
            duplicates={duplicatesOf(entry.id)}
            onSelect={setSelectedId}
          />
        )}
      />
    </section>
  );
}
