"use client";

import { ChevronDown } from "lucide-react";
import { motion } from "motion/react";
import { useId, useState } from "react";
import type { RunOut, ShortlistItemOut } from "@/lib/api/client";
import { formatShare, plural } from "@/lib/format";
import { candidateCounts, type CompanyRow } from "@/lib/run/activity-store";
import type { MarkState } from "@/lib/run/types";
import { duration, ease, rise, transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { CriteriaStripLegend } from "@/components/dealproof";
import { NumberTween } from "@/components/dealproof/number-tween";
import type { FindingsContext } from "@/components/run/run-view";
import { Icon } from "@/components/ui/icon";
import { ShortlistCard } from "./shortlist-card";
import { ShortlistOverview } from "./shortlist-overview";

const MARKS: { key: string; label: string; none: string }[] = [
  { key: "funding", label: "funding", none: "no funding record" },
  { key: "headcount", label: "headcount", none: "no headcount series" },
  { key: "hiring", label: "hiring", none: "no open roles found" },
];

/** One enrichment mark: a ring while it is being read, then a check or a dash. */
function EnrichMark({ label, none, state }: { label: string; none: string; state: MarkState | undefined }) {
  if (!state) return null;
  const found = state === "found";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        found ? "text-ink" : "text-ink-muted",
      )}
    >
      {
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden>
          {state === "pending" ? (
            // Being read: an open ring, still. Only steps and claims being checked spin.
            <circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.5" />
          ) : found ? (
            <path d="M2.5 6.3 5 8.6l4.5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          ) : state === "not_checked" ? (
            <circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 1.6" />
          ) : (
            <path d="M3 6h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          )}
        </svg>
      }
      {state === "none" ? none : state === "not_checked" ? `${label} not checked` : label}
    </span>
  );
}

function CandidateRow({ row, ranked }: { row: CompanyRow; ranked: boolean }) {
  const scored = ranked && row.rank != null;
  const facts = [
    row.location,
    row.headcount != null
      ? `${row.headcount_is_estimate ? "about " : ""}${row.headcount.toLocaleString("en-US")} people${
          row.headcount_is_estimate ? " (estimate)" : ""
        }`
      : null,
  ].filter(Boolean);
  const waiting = row.stage === "found";
  return (
    <div className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-start gap-x-3 px-4 py-3 text-dense">
      <span className="pt-0.5 text-right font-mono text-xs text-ink-muted">{scored ? row.rank : null}</span>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium text-ink">{row.name ?? "Unnamed company"}</span>
          {row.domain ? <span className="font-mono text-xs text-ink-muted">{row.domain}</span> : null}
        </p>
        {facts.length > 0 ? <p className="text-xs text-ink-secondary">{facts.join(" · ")}</p> : null}
        {Object.keys(row.marks).length > 0 ? (
          <p className="flex flex-wrap gap-x-3 gap-y-1">
            {MARKS.map((mark) => (
              <EnrichMark key={mark.key} label={mark.label} none={mark.none} state={row.marks[mark.key]} />
            ))}
          </p>
        ) : null}
        {row.highlight ? (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: duration.base, ease }}
            className="text-xs text-ink-secondary"
          >
            {row.highlight}
          </motion.p>
        ) : null}
        {row.stage === "explained" ? (
          <p className="text-xs text-ink-muted">Reason written · it is on the card when the search finishes</p>
        ) : null}
      </div>
      <p className="text-right font-mono text-xs whitespace-nowrap text-ink-secondary">
        {scored ? (
          row.fit != null ? (
            <>
              <span className="text-sm font-medium text-ink">Fit {Math.round(row.fit)}</span>
              {row.assessable != null ? ` · ${formatShare(row.assessable)} assessable` : null}
            </>
          ) : (
            "Fit not available"
          )
        ) : waiting ? (
          <span className="font-sans text-ink-muted">found</span>
        ) : null}
      </p>
    </div>
  );
}

function Count({ value, label }: { value: number; label: string }) {
  return (
    <span className="whitespace-nowrap">
      <NumberTween value={value} className="text-ink" /> {label}
    </span>
  );
}

export interface CandidateStreamProps {
  context: FindingsContext;
  thesisId: string;
  /**
   * The finished shortlist, once the thesis has been read again. Each candidate row that
   * made the list becomes its full card in place; the row is not replaced.
   */
  settled?: ShortlistItemOut[];
  /** The finished run, for the overview's cost line. */
  run?: RunOut | null;
}

/**
 * The Discover findings: the shortlist being assembled. A company is a row from the
 * moment the search returns it, and the same row gains detail as each step reaches it.
 *
 * Before the score step there is no rank and no fit number: rows are in arrival order
 * and the list is called "Candidates". It becomes "Shortlist" when ranking is done, and
 * the rows move to rank order once. Dropped companies are kept, with the criterion's own
 * reason. Totals come from `candidateCounts`, so the heading and the dropped list state
 * the same numbers: found is always in play plus dropped, and a duplicate the gate removed
 * is a dropped company. Where an event named fewer rows than it counted, the difference
 * is said in words.
 */
export function CandidateStream({ context, thesisId, settled, run }: CandidateStreamProps) {
  const { view, isNew } = context;
  const [showDropped, setShowDropped] = useState(false);
  const droppedId = useId();
  const all = view.companies.rows;
  const counts = view.companies.counts;
  const ranked = view.companiesScoredSeq !== null && context.stepSettled(view.companiesScoredStep);
  const dropped = all.filter((row) => row.stage === "dropped");
  const inPlay = all.filter((row) => row.stage !== "dropped");
  const cards = new Map((settled ?? []).filter((item) => !item.excluded).map((item) => [item.id, item]));
  const folded = settled !== undefined;

  const arrival = (a: CompanyRow, b: CompanyRow) => a.firstSeq - b.firstSeq || a.slot - b.slot;
  const ordered = [...inPlay].sort((a, b) => {
    if (folded) {
      const ra = cards.get(a.id)?.rank ?? Infinity;
      const rb = cards.get(b.id)?.rank ?? Infinity;
      if (ra !== rb) return ra - rb;
    }
    if (ranked && (a.rank ?? Infinity) !== (b.rank ?? Infinity)) return (a.rank ?? Infinity) - (b.rank ?? Infinity);
    return arrival(a, b);
  });
  // Once the shortlist is in, only what made the list stays; the rest was never ranked.
  const rows = folded ? ordered.filter((row) => cards.has(row.id)) : ordered;
  // A finished shortlist row with no stream row (the stream names at most eight per event).
  const unstreamed = folded ? [...cards.values()].filter((item) => !all.some((row) => row.id === item.id)) : [];

  // One reckoning for the heading, the notes and the dropped list.
  const totals = candidateCounts(view);
  const { found, dropped: droppedCount, inPlay: inPlayCount } = totals;
  const enrichedRows = inPlay.filter((row) => ["enriched", "scored", "explained"].includes(row.stage)).length;
  const enrichedCount = counts.enriched ?? enrichedRows;
  const requested = view.tally.rows.get("company_enrich")?.counts.requested ?? null;
  const unlisted = Math.max(0, inPlayCount - inPlay.length);
  // The dropped total, split by cause. The parts always add up to it.
  const droppedParts = [
    totals.duplicates > 0 ? plural(totals.duplicates, "duplicate") : null,
    totals.failedMustHave > 0 ? `${totals.failedMustHave} failed a must-have` : null,
    totals.notRanked > 0 ? `${totals.notRanked} not ranked` : null,
  ].filter(Boolean);
  const shortlistItems = [...cards.values()].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));

  return (
    <section aria-labelledby="candidates-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 id="candidates-heading" className="text-xl font-medium text-ink">
          {ranked || folded ? "Shortlist" : "Candidates"}
          {folded ? (
            <>
              {" "}
              <span className="text-ink-muted">·</span> <span className="font-mono">{cards.size}</span>{" "}
              {cards.size === 1 ? "company" : "companies"}
            </>
          ) : null}
        </h2>
        {all.length > 0 || found > 0 ? (
          <p className="flex flex-wrap gap-x-2 font-mono text-xs text-ink-muted">
            <Count value={found} label="found" />
            <span>·</span>
            <Count value={inPlayCount} label="in play" />
            <span>·</span>
            <Count value={droppedCount} label="dropped" />
          </p>
        ) : null}
      </div>

      {folded && shortlistItems.length > 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={transition.slow}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-2 rounded-md border border-line bg-surface-raised px-4 py-3">
            <p className="text-sm text-ink">Fit measures match to your criteria. It says nothing about returns.</p>
            <CriteriaStripLegend className="pt-1" />
          </div>
          <ShortlistOverview
            ranked={shortlistItems}
            removed={(settled ?? []).filter((item) => item.excluded)}
            run={run}
          />
        </motion.div>
      ) : null}

      {all.length === 0 && !folded ? (
        <p className="rounded-lg border border-dashed border-line-strong px-4 py-3 text-dense text-ink-muted">
          No company has been returned yet
        </p>
      ) : (
        <ol className={cn("flex flex-col", folded ? "gap-4" : "rounded-lg border border-line bg-surface")}>
          {rows.map((row, index) => {
            const card = cards.get(row.id);
            const enter = !folded && isNew(row.firstSeq);
            return (
              <motion.li
                key={row.id}
                layout="position"
                initial={enter ? { opacity: 0, y: rise } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...transition.slow, delay: enter ? row.slot * 0.06 : 0 }}
                className={cn(!folded && "border-b border-line last:border-b-0")}
              >
                {card ? (
                  <ShortlistCard item={card} thesisId={thesisId} index={index} />
                ) : (
                  <CandidateRow row={row} ranked={ranked} />
                )}
              </motion.li>
            );
          })}
          {unstreamed.map((item, index) => (
            <li key={item.id}>
              <ShortlistCard item={item} thesisId={thesisId} index={rows.length + index} />
            </li>
          ))}
        </ol>
      )}

      {folded ? null : (
        <ul className="flex flex-col gap-1 text-xs text-ink-secondary">
          {unlisted > 0 ? (
            <li>
              {unlisted} more in play · the run names the first rows of each batch and counts the rest
            </li>
          ) : null}
          {enrichedCount > enrichedRows ? (
            <li>
              {enrichedCount} enriched in all, {enrichedCount - enrichedRows} of them not listed here
            </li>
          ) : null}
          {requested !== null && !ranked && inPlayCount > requested ? (
            <li>
              {inPlayCount - requested} not in the top {requested} (kept, not enriched)
            </li>
          ) : null}
        </ul>
      )}

      {droppedCount > 0 ? (
        <div className="rounded-lg border border-line bg-surface">
          <button
            type="button"
            aria-expanded={showDropped}
            aria-controls={droppedId}
            onClick={() => setShowDropped((value) => !value)}
            className={cn(
              "focus-inset flex min-h-9 w-full items-center justify-between gap-3 rounded-t-lg px-4 py-2 text-left text-dense text-ink transition-colors hover:bg-surface-raised",
              !showDropped && "rounded-b-lg",
            )}
          >
            <span>
              <span className="font-mono">{droppedCount}</span> dropped
              {droppedParts.length > 0 ? (
                <span className="text-ink-secondary"> · {droppedParts.join(" · ")}</span>
              ) : null}
            </span>
            <Icon icon={ChevronDown} className={cn("text-ink-muted transition-transform", showDropped && "rotate-180")} />
          </button>
          {showDropped ? (
            <ul id={droppedId} className="divide-y divide-line border-t border-line">
              {dropped.map((row) => (
                <li key={row.id} className="flex flex-col gap-0.5 px-4 py-2 text-dense">
                  <span className="text-ink-muted">{row.name ?? "Unnamed company"}</span>
                  <span className="text-xs text-ink-secondary">{row.reason ?? "No reason was recorded"}</span>
                </li>
              ))}
              {view.companyDuplicates.map((row) => (
                <li key={`${row.id}-duplicate`} className="flex flex-col gap-0.5 px-4 py-2 text-dense">
                  <span className="text-ink-muted">{row.name ?? "Unnamed company"}</span>
                  <span className="text-xs text-ink-secondary">
                    Returned twice by the search · one copy kept, still in play
                  </span>
                </li>
              ))}
              {droppedCount > totals.named ? (
                <li className="px-4 py-2 text-xs text-ink-muted">
                  {plural(droppedCount - totals.named, "more company", "more companies")} dropped, not named in the
                  run&rsquo;s events
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
