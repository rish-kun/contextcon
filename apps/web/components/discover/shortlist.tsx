"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import type { ShortlistItemOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { CriteriaStripLegend, Fact, SourceLine } from "@/components/dealproof";
import { factEstimate, factEvidence, toEvidence } from "./adapt";
import { EmptyState } from "./notice";
import { Marker, NoExcerpt, ShortlistCard } from "./shortlist-card";
import { ShortlistOverview } from "./shortlist-overview";

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
  onEditCriteria,
}: {
  items: ShortlistItemOut[];
  thesisId: string;
  onEditCriteria: () => void;
}) {
  const [showRemoved, setShowRemoved] = useState(false);
  const removedId = useId();

  const ranked = items
    .filter((item) => !item.excluded)
    .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));
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
            Sorted by fit score, with ties broken by share of criteria assessable
          </p>
        </div>
        <div className="flex flex-col gap-2 rounded-md border border-line bg-surface-raised px-4 py-3">
          <p className="text-sm text-ink">
            Fit measures match to your criteria. It says nothing about returns.
          </p>
          <p className="text-xs text-ink-secondary">
            Hiring and headcount change are operating signals. They are never treated as proof of
            revenue.
          </p>
          <CriteriaStripLegend className="pt-1" />
        </div>
      </div>

      <ShortlistOverview ranked={ranked} removed={removed} />

      <div className="flex flex-col gap-4">
        {ranked.map((item, index) => (
          <ShortlistCard key={item.id} item={item} thesisId={thesisId} index={index} />
        ))}
      </div>

      {removedSection}
    </section>
  );
}
