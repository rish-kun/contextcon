import type { InvestorSearchOut } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { sentence } from "./format";
import { InvestorEntry } from "./investor-entry";
import { buildAxis, RoundAxisHeader } from "./round-axis";

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
 * The ranked investors of one search. Every entry is here because a dated funding record
 * connects it to a comparable company; the order is a count of those records weighted
 * toward recent ones, and nothing more.
 */
export function Shortlist({ search }: { search: InvestorSearchOut }) {
  const entries = [...search.entries].sort((a, b) => a.rank - b.rank);
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const companies = new Set(entries.flatMap((e) => e.comparable_rounds.map((r) => r.company_id)));
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

      <div className="rounded-lg border border-line bg-surface">
        {axis ? (
          <div className="hidden grid-cols-[2rem_minmax(0,1fr)] gap-x-3 rounded-t-lg border-b border-line bg-surface-sunken px-5 py-2 lg:grid">
            <span />
            <div className="grid items-end gap-x-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <span className="text-xs text-ink-muted">Investor</span>
              <RoundAxisHeader axis={axis} />
            </div>
          </div>
        ) : null}
        <ol>
          {entries.map((entry, index) => (
            <InvestorEntry
              key={entry.id}
              entry={entry}
              axis={axis}
              fundingSought={search.profile.funding_sought}
              scope={scope}
              duplicates={duplicatesOf(entry.id)}
              index={index}
            />
          ))}
        </ol>
      </div>
    </section>
  );
}
