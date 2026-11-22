"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { isFixtureMode, type RunOut, type ShortlistItemOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { CriteriaStripLegend, Fact, SourceLine } from "@/components/dealproof";
import { factEstimate, factEvidence, toEvidence } from "./adapt";
import { EmptyState } from "./notice";
import { Marker, NoExcerpt, ShortlistCard } from "./shortlist-card";
import { median } from "@/components/insight";
import { fitIsTied, ShortlistOverview } from "./shortlist-overview";

/** Fixture mode keeps the thesis you typed, but the companies are a fixed example. Said once, here. */
function FixedExample({ what }: { what: string }) {
  if (!isFixtureMode) return null;
  return (
    <p className="self-start rounded-xs border border-dashed border-line-strong px-2 py-0.5 text-xs text-ink-secondary">
      Fixed example · {what}
    </p>
  );
}

/** A company removed because a record verifiably failed a must-have. */
function ExcludedRow({ item }: { item: ShortlistItemOut }) {
  const failed = item.criterion_results.filter(
    (result) => result.kind === "must" && result.state === "fail",
  );
  const { business, location } = item.card;

  return (
    <li className="flex flex-col gap-3 px-4 py-4 sm:px-5">
      <div className="flex flex-col gap-1">
        <h4 className="text-sm font-medium text-ink">{item.name}</h4>
        <div className="flex flex-col items-start gap-1 text-dense">
          {business ? (
            <Fact evidence={factEvidence(business)} estimate={factEstimate(business)}>
              {business.value}
            </Fact>
          ) : null}
          {location ? (
            <Fact evidence={factEvidence(location)} estimate={factEstimate(location)}>
              {location.value}
            </Fact>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-ink-secondary">Failed must-have</p>
        {item.exclusion_reason ? (
          <p className="text-dense text-ink">{item.exclusion_reason}</p>
        ) : null}
        {failed.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {failed.map((result) => (
              <li key={result.criterion_id} className="flex gap-2 text-dense">
                <Marker kind="not_met" />
                <div className="flex min-w-0 flex-col items-start gap-1">
                  <p className="text-ink">
                    {result.label}
                    <span className="text-ink-secondary"> · {result.reason}</span>
                  </p>
                  {result.evidence.length > 0 ? (
                    <SourceLine evidence={result.evidence.map(toEvidence)} />
                  ) : (
                    <NoExcerpt />
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="flex flex-wrap items-center gap-2 text-xs text-ink-secondary">
            The failing criterion was not recorded with this removal
            <NoExcerpt />
          </p>
        )}
      </div>
    </li>
  );
}

/**
 * Step 3: the ranked shortlist, then the companies removed for a verified must-have fail,
 * collapsed. Fit says how well a company matches the criteria and nothing about returns;
 * that is said once, above the list, next to the strip's legend.
 */
export function Shortlist({
  items,
  thesisId,
  run,
  onEditCriteria,
}: {
  items: ShortlistItemOut[];
  thesisId: string;
  /** The search run, for its cost in the summary row. */
  run?: RunOut | null;
  onEditCriteria: () => void;
}) {
  const [showRemoved, setShowRemoved] = useState(false);
  const removedId = useId();

  const unsorted = items.filter((item) => !item.excluded);
  // When every fit is the same, the rank says nothing. Order by how much could be assessed,
  // then by name, and say so.
  const tied = fitIsTied(unsorted);
  const ranked = [...unsorted].sort((a, b) =>
    tied
      ? b.assessable_pct - a.assessable_pct || a.name.localeCompare(b.name)
      : (a.rank ?? Infinity) - (b.rank ?? Infinity),
  );
  const tiedFit = tied ? (ranked.find((item) => item.fit !== null)?.fit ?? null) : null;
  const medianAssessable = Math.round(median(ranked.map((item) => item.assessable_pct)) ?? 0);
  const removed = items.filter((item) => item.excluded);

  const removedSection =
    removed.length > 0 ? (
      <section className="rounded-lg border border-line bg-surface">
        <button
          type="button"
          aria-expanded={showRemoved}
          aria-controls={removedId}
          onClick={() => setShowRemoved((value) => !value)}
          className={cn(
            "focus-inset flex min-h-11 w-full items-center justify-between gap-3 rounded-t-lg px-4 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-raised sm:px-5",
            !showRemoved && "rounded-b-lg",
          )}
        >
          <span>
            <span className="font-mono">{removed.length}</span> removed for failing a must-have
          </span>
          <span className="inline-flex items-center gap-1 text-ink-secondary">
            {showRemoved ? "Hide" : "Show"}
            <Icon
              icon={ChevronDown}
              className={cn("transition-transform", showRemoved && "rotate-180")}
            />
          </span>
        </button>
        {showRemoved ? (
          <div id={removedId} className="animate-fade-in border-t border-line motion-reduce:animate-none">
            <p className="border-b border-line bg-surface-sunken px-4 py-2 text-xs text-ink-secondary sm:px-5">
              Removed only where a record conflicts with a must-have. Missing information never
              removes a company.
            </p>
            <ul className="divide-y divide-line">
              {removed.map((item) => (
                <ExcludedRow key={item.id} item={item} />
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    ) : null;

  if (ranked.length === 0) {
    return (
      <section aria-label="Shortlist" className="flex flex-col gap-4">
        <EmptyState
          title="No companies matched all must-haves"
          actions={
            <>
              {removed.length > 0 && !showRemoved ? (
                <Button onClick={() => setShowRemoved(true)}>Show removed companies</Button>
              ) : null}
              <Button variant={removed.length > 0 ? "secondary" : "primary"} onClick={onEditCriteria}>
                Edit criteria
              </Button>
            </>
          }
        >
          {removed.length > 0
            ? `${plural(removed.length, "candidate")} ${
                removed.length === 1 ? "was" : "were"
              } removed for failing a must-have criterion. Review the removed companies or adjust your criteria.`
            : "The search returned no companies for these criteria. Adjust the criteria and search again."}
        </EmptyState>
        {removedSection}
      </section>
    );
  }

  return (
    <section aria-labelledby="shortlist-heading" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h2 id="shortlist-heading" className="text-xl font-medium text-ink">
            Shortlist <span className="text-ink-muted">·</span>{" "}
            <span className="font-mono">{ranked.length}</span>{" "}
            {ranked.length === 1 ? "company" : "companies"}
          </h2>
          <p className="text-xs text-ink-muted">
            {tied
              ? "Fit is the same for all, so sorted by share of criteria assessable, then name"
              : "Sorted by fit score, with ties broken by share of criteria assessable"}
          </p>
        </div>
        <FixedExample what="these companies are fictional and do not change with the thesis or criteria you enter" />
      </div>

      <ShortlistOverview ranked={ranked} removed={removed} run={run} />

      {tied && tiedFit !== null ? (
        <p className="rounded-md border border-line-strong bg-surface px-4 py-3 text-sm text-ink">
          {tiedFit === 100
            ? `All ${ranked.length} candidates meet every criterion that could be assessed.`
            : `All ${ranked.length} candidates have the same fit, ${tiedFit}.`}{" "}
          {medianAssessable < 100 ? (
            <>
              <span className="font-mono">{100 - medianAssessable}%</span> of criteria could not be
              assessed for the typical candidate, so fit does not separate them yet. Opening a case
              checks the criteria that need evidence.
            </>
          ) : (
            "Fit does not separate them."
          )}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <p className="text-xs text-ink-secondary">
          Fit measures match to your criteria and says nothing about returns. Hiring and headcount
          change are operating signals, never proof of revenue
        </p>
        <CriteriaStripLegend />
      </div>

      <div className="flex flex-col gap-4">
        {ranked.map((item, index) => (
          <ShortlistCard key={item.id} item={item} thesisId={thesisId} index={index} position={tied ? index + 1 : null} />
        ))}
      </div>

      {removedSection}
    </section>
  );
}
