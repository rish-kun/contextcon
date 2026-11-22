"use client";

import { SearchX } from "lucide-react";
import { Fragment } from "react";
import { formatCredits, formatDate } from "@/lib/format";
import {
  NOT_CHECKED_REASON_DETAIL,
  NOT_CHECKED_REASON_LABEL,
  RELIABILITY_LABEL,
} from "@/lib/labels";
import type { Claim } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EstimateLabel } from "@/components/dealproof/estimate-label";
import { SourceClassGlyph, StatusGlyph } from "@/components/dealproof/glyphs";
import { EvidenceDetail, SourceLine } from "@/components/dealproof/source-line";
import { STATUS_INK, StatusMark } from "@/components/dealproof/status-mark";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { trailFromClaim, type EmptySearch, type TrailFact, type TrailSource } from "./derive";
import { ColumnHead, Connector } from "./parts";

/**
 * A source that was read. It is a button: it opens exactly what was taken from it.
 */
function SourceNode({ source }: { source: TrailSource }) {
  const first = source.evidence[0];
  const { label, reliability, class_label: classLabel } = first.source;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source: ${label}. Open the evidence`}
          className="flex w-full min-w-0 items-start gap-2 rounded-md border border-line-strong bg-surface px-2 py-1.5 text-left transition-[background-color,border-color] hover:bg-surface-raised data-[state=open]:border-accent-line data-[state=open]:bg-accent-tint"
        >
          <SourceClassGlyph reliability={reliability} className="mt-0.5 shrink-0 text-ink-muted" />
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-dense text-ink">{label}</span>
            <span className="truncate text-xs text-ink-muted">
              {classLabel ?? RELIABILITY_LABEL[reliability]}
            </span>
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="flex max-h-96 flex-col gap-4 overflow-y-auto">
        {source.evidence.map((evidence, index) => (
          <div key={evidence.id ?? index} className={cn(index > 0 && "border-t border-line pt-4")}>
            <EvidenceDetail evidence={evidence} />
          </div>
        ))}
      </PopoverContent>
    </Popover>
  );
}

/** The as-of date heads each fact, because the date is what the rule reads. */
function FactItem({ fact }: { fact: TrailFact }) {
  const date = formatDate(fact.as_of);
  return (
    <li className="flex min-w-0 flex-col gap-0.5">
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className={cn("font-mono text-xs", date ? "text-ink" : "text-ink-muted")}>
          {date ?? "unknown date"}
        </span>
        {fact.part ? (
          <span className="text-xs text-ink-muted">
            {fact.part === "supported" ? "Supported" : "Not supported"}
          </span>
        ) : null}
      </p>
      <p className="text-dense wrap-break-word text-ink">
        {fact.estimate ? (
          <EstimateLabel kind={fact.estimate.kind} basis={fact.estimate.basis}>
            {fact.text}
          </EstimateLabel>
        ) : (
          fact.text
        )}
      </p>
    </li>
  );
}

/** A search that returned nothing: dashed and hatched, in the Not checked family. */
function EmptyNode({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="hatch flex min-w-0 items-start gap-2 rounded-md border border-dashed border-not-checked-line px-2 py-1.5 text-not-checked">
      <Icon icon={SearchX} className="mt-0.5 shrink-0" />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-dense font-medium">{label}</span>
        <span className="text-xs">{detail}</span>
      </span>
    </div>
  );
}

/** One source, the arrow out of it, and what it gave. Stacks under 56rem of own width. */
function TrailRow({
  node,
  dashed,
  children,
}: {
  node: React.ReactNode;
  dashed?: boolean;
  children: React.ReactNode;
}) {
  return (
    <li className="grid gap-x-0 gap-y-2 @4xl:grid-cols-[minmax(0,5fr)_1.5rem_minmax(0,6fr)] @4xl:items-start">
      {node}
      <Connector dashed={dashed} className="mt-2.5 hidden @4xl:block" />
      <div className="min-w-0 pl-4 @4xl:pl-0">{children}</div>
    </li>
  );
}

export interface EvidenceTrailProps extends Omit<React.ComponentProps<"section">, "children"> {
  claim: Claim;
  /**
   * The rule that fired for this claim, in words. The API does not send it yet; without
   * it the column shows the fixed meaning of the status and says that is what it is.
   */
  rule?: string | null;
  /** Searches that ran and found nothing. Not recorded by the API yet; drawn only when given. */
  emptySearches?: EmptySearch[];
  /** Offers "Run check" on a claim that was not checked. It costs credits, and the button says so. */
  onRunCheck?: (claim: Claim) => void;
}

/**
 * Why a claim has the status it has, drawn left to right in a fixed order: what the
 * seller said, where DealProof looked, what it found and when, the rule, the answer.
 * A search that found nothing is drawn too, dashed, because "we looked and found no
 * record" is part of the reasoning. Static: every mark is a record on the case.
 */
export function EvidenceTrail({
  claim,
  rule,
  emptySearches,
  onRunCheck,
  className,
  onClick,
  ...props
}: EvidenceTrailProps) {
  const trail = trailFromClaim(claim, { rule, emptySearches });
  const reason = claim.not_checked_reason;

  return (
    <section
      aria-label={`Evidence trail for claim ${claim.number}`}
      // The trail often sits inside a row that toggles on click; a click in here is not one.
      onClick={(event) => {
        event.stopPropagation();
        onClick?.(event);
      }}
      className={cn("@container cursor-auto bg-surface px-4 py-4 text-dense", className)}
      {...props}
    >
      <div
        className={cn(
          "flex flex-col gap-4 @4xl:grid @4xl:gap-x-0 @4xl:gap-y-2",
          trail.state === "not_checked"
            ? "@4xl:grid-cols-[minmax(0,5fr)_1.5rem_minmax(0,20fr)]"
            : "@4xl:grid-cols-[minmax(0,5fr)_1.5rem_minmax(0,11fr)_1.5rem_minmax(0,5fr)_1.5rem_minmax(0,4fr)]",
        )}
      >
        {/* 1. What the seller said */}
        <div className="flex min-w-0 flex-col items-start gap-2">
          <ColumnHead>Seller said</ColumnHead>
          <p className="text-ink">“{claim.text}”</p>
          <SourceLine evidence={[claim.stated_in]} />
        </div>

        {trail.state === "not_checked" ? (
          <>
            <Connector dashed className="mt-8 hidden @4xl:block" />
            <div className="hatch flex min-w-0 flex-col items-start gap-2 rounded-md border border-dashed border-not-checked-line p-3 text-not-checked">
              <p className="flex items-center gap-2 font-medium">
                <StatusGlyph status="not_checked" />
                Not checked · {reason ? NOT_CHECKED_REASON_LABEL[reason] : "reason not recorded"}
              </p>
              <p>
                {reason ? NOT_CHECKED_REASON_DETAIL[reason] : "This check did not run"}. No
                source was read, no fact was dated and no rule was applied
              </p>
              {onRunCheck ? (
                <Button size="sm" onClick={() => onRunCheck(claim)}>
                  Run check
                  {claim.retry_credits_estimate != null ? (
                    <span className="font-mono text-xs font-normal text-ink-secondary">
                      about {formatCredits(claim.retry_credits_estimate)}{" "}
                      {Math.round(claim.retry_credits_estimate) === 1 ? "credit" : "credits"}
                    </span>
                  ) : null}
                </Button>
              ) : null}
            </div>
          </>
        ) : (
          <>
            <Connector className="mt-8 hidden @4xl:block" />

            {/* 2 and 3. Where we looked, and what was found and when */}
            <div className="flex min-w-0 flex-col gap-2 border-l border-line-strong pl-4 @4xl:border-l-0 @4xl:pl-0">
              <div className="hidden @4xl:grid @4xl:grid-cols-[minmax(0,5fr)_1.5rem_minmax(0,6fr)]">
                <ColumnHead>Sources</ColumnHead>
                <span />
                <ColumnHead>Dated facts</ColumnHead>
              </div>
              <ColumnHead className="@4xl:hidden">Sources and dated facts</ColumnHead>
              <ul className="flex flex-col gap-3">
                {trail.sources.map((source, index) => (
                  <Fragment key={source.key}>
                    {trail.disagree && index > 0 ? (
                      <li
                        className={cn(
                          "flex items-center gap-2 text-xs font-medium @4xl:pl-[calc(5/11*100%+1.5rem)]",
                          STATUS_INK.conflicting_evidence,
                        )}
                      >
                        <StatusGlyph status="conflicting_evidence" size={14} />
                        disagree
                      </li>
                    ) : null}
                    <TrailRow node={<SourceNode source={source} />}>
                      <ul className="flex flex-col gap-2">
                        {source.facts.map((fact) => (
                          <FactItem key={fact.key} fact={fact} />
                        ))}
                      </ul>
                    </TrailRow>
                  </Fragment>
                ))}
                {trail.emptySearches.map((search, index) => (
                  <TrailRow
                    key={`${search.reliability}-${index}`}
                    dashed
                    node={
                      <EmptyNode
                        label={search.label ?? RELIABILITY_LABEL[search.reliability]}
                        detail="Searched, no record"
                      />
                    }
                  >
                    <p className="pt-1.5 text-not-checked">Nothing found</p>
                  </TrailRow>
                ))}
                {trail.state === "nothing_found" && trail.emptySearches.length === 0 ? (
                  <TrailRow
                    dashed
                    node={<EmptyNode label="Searched" detail="No evidence was attached" />}
                  >
                    <p className="pt-1.5 text-not-checked">
                      Nothing found. Which sources were searched is not recorded
                    </p>
                  </TrailRow>
                ) : null}
              </ul>
            </div>

            <Connector className="mt-8 hidden @4xl:block" />

            {/* 4. The rule */}
            <div className="flex min-w-0 flex-col gap-2 border-l border-line-strong pl-4 @4xl:border-l-0 @4xl:pl-0">
              <ColumnHead>Rule</ColumnHead>
              <p className="text-ink">{trail.rule.text}</p>
              {trail.rule.from === "status_definition" ? (
                <p className="text-xs text-ink-muted">
                  What this status means under the scoring policy
                </p>
              ) : null}
              {trail.findings.map((finding) => (
                <p key={finding} className="text-ink-secondary">
                  {finding}
                </p>
              ))}
              {claim.note ? <p className="text-ink-secondary">{claim.note}</p> : null}
            </div>

            <Connector className="mt-8 hidden @4xl:block" />

            {/* 5. The answer */}
            <div className="flex min-w-0 flex-col items-start gap-2 border-l border-line-strong pl-4 @4xl:border-l-0 @4xl:pl-0">
              <ColumnHead>Status</ColumnHead>
              <StatusMark status={claim.status} />
              {claim.what_would_settle ? (
                <p className="text-ink">
                  <span className="text-ink-muted">What would settle it: </span>
                  {claim.what_would_settle}
                </p>
              ) : null}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
