"use client";

import { SearchX } from "lucide-react";
import { Fragment } from "react";
import { formatCredits, formatDate } from "@/lib/format";
import { CLAIM_STATUS_LABEL, NOT_CHECKED_REASON_LABEL, RELIABILITY_LABEL } from "@/lib/labels";
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

/** Every node of the chain is this tall, so the connectors meet them on one line. */
const NODE = "flex min-h-7 items-center";

/** A source that was read. It is a button: it opens exactly what was taken from it. */
function SourceNode({ source }: { source: TrailSource }) {
  const first = source.evidence[0];
  const { label, reliability, class_label: classLabel } = first.source;
  const kind = classLabel ?? RELIABILITY_LABEL[reliability];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source: ${label}, ${kind}. Open the evidence`}
          title={`${label} · ${kind}`}
          className="inline-flex h-7 max-w-full min-w-0 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-2 text-left transition-[background-color,border-color] hover:bg-surface-raised data-[state=open]:border-accent-line data-[state=open]:bg-accent-tint"
        >
          <SourceClassGlyph reliability={reliability} className="shrink-0 text-ink-muted" />
          <span className="truncate text-ink">{label}</span>
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
    <li className={cn(NODE, "min-w-0 flex-wrap gap-x-2")}>
      <span className={cn("shrink-0 font-mono text-xs", date ? "text-ink-secondary" : "text-ink-muted")}>
        {date ?? "unknown date"}
      </span>
      <span className="min-w-0 wrap-break-word text-ink @3xl:line-clamp-2" title={fact.text}>
        {fact.estimate ? (
          <EstimateLabel kind={fact.estimate.kind} basis={fact.estimate.basis}>
            {fact.text}
          </EstimateLabel>
        ) : (
          fact.text
        )}
      </span>
      {fact.part ? (
        <span className="shrink-0 text-xs text-ink-muted">
          {fact.part === "supported" ? "Supported" : "Not supported"}
        </span>
      ) : null}
    </li>
  );
}

/** A search that returned nothing: dashed and hatched, in the Not checked family. */
function EmptyNode({ label }: { label: string }) {
  return (
    <span
      title={label}
      className="hatch inline-flex h-7 max-w-full min-w-0 items-center gap-1.5 rounded-md border border-dashed border-not-checked-line px-2 text-not-checked"
    >
      <Icon icon={SearchX} className="shrink-0" />
      <span className="truncate font-medium">{label}</span>
    </span>
  );
}

/** One source, the arrow out of it, and what it gave. Wide: one line. Narrow: facts under the source. */
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
    <li className={cn("grid gap-y-1 @3xl:items-start", PAIR)}>
      <div className={cn(NODE, "min-w-0")}>{node}</div>
      <span className={cn(NODE, "hidden justify-center @3xl:flex")}>
        <Connector dashed={dashed} />
      </span>
      <div className="min-w-0">{children}</div>
    </li>
  );
}

/** Source | arrow | dated fact, shared by the column heads and every row under them. */
const PAIR = "@3xl:grid-cols-[minmax(0,2fr)_2rem_minmax(0,3fr)]";

/**
 * One step of the chain. Narrow: a vertical stepper, with a dot on a rail. Wide: a column
 * whose head sits on one line and whose first node sits on the next, with the arrow into
 * it on that same line.
 */
function Step({
  label,
  first = false,
  last = false,
  dashed = false,
  className,
  children,
}: {
  /** The quiet head above the step. A node, for the step that has two heads. */
  label: React.ReactNode;
  first?: boolean;
  last?: boolean;
  dashed?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <li className={cn("flex min-w-0", className)}>
      {/* Narrow: the rail. */}
      <span aria-hidden className="mr-3 flex w-2 shrink-0 flex-col items-center @3xl:hidden">
        <span className="mt-1.5 size-2 shrink-0 rounded-full border border-ink-muted bg-surface" />
        {last ? null : <span className="w-px flex-1 bg-line-strong" />}
      </span>
      {/* Wide: the arrow in, on the line of the first node. */}
      {first ? null : (
        <span aria-hidden className="hidden shrink-0 flex-col gap-1 px-2 @3xl:flex">
          <span className="h-4" />
          <span className={NODE}>
            <Connector dashed={dashed} />
          </span>
        </span>
      )}
      <div className={cn("flex min-w-0 flex-1 flex-col gap-1", last ? "pb-0" : "pb-4 @3xl:pb-0")}>
        {typeof label === "string" ? <ColumnHead className="leading-4">{label}</ColumnHead> : label}
        {children}
      </div>
    </li>
  );
}

/** The full rule behind its one short line: asked for, never in the way. */
function RuleWhy({ children }: { children: React.ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger className="inline-flex h-7 shrink-0 items-center rounded-xs text-xs text-ink-muted underline decoration-dotted underline-offset-4 transition-colors hover:text-ink data-[state=open]:text-ink print:hidden">
        Why?
      </PopoverTrigger>
      <PopoverContent align="end" className="flex flex-col gap-2 text-dense text-ink-secondary">
        {children}
      </PopoverContent>
    </Popover>
  );
}

export interface EvidenceTrailProps extends Omit<React.ComponentProps<"section">, "children"> {
  claim: Claim;
  /**
   * The rule that fired for this claim, in words. The API does not send it yet; without
   * it the step names the status rule in a few words and "Why?" gives its full meaning.
   */
  rule?: string | null;
  /** Searches that ran and found nothing. Not recorded by the API yet; drawn only when given. */
  emptySearches?: EmptySearch[];
  /** Offers "Run check" on a claim that was not checked. It costs credits, and the button says so. */
  onRunCheck?: (claim: Claim) => void;
}

/**
 * Why a claim has the status it has, as one chain in a fixed order: where the seller
 * said it, where DealProof looked, what it found and when, the rule, the answer. A
 * search that found nothing is drawn too, dashed, because "we looked and found no
 * record" is part of the reasoning.
 *
 * The chain only. The claim's words, the finding, the note and what would settle it
 * belong to the ledger row the trail sits under, and are not said twice. Wide, it is one
 * line of small nodes joined by arrows; under 48rem of its own width it is a vertical
 * stepper. Static: every mark is a record on the case.
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
      className={cn("@container cursor-auto bg-surface px-4 py-3 text-dense", className)}
      {...props}
    >
      <ol className="flex flex-col @3xl:flex-row @3xl:items-start">
        {/* 1. Where the seller said it */}
        <Step label="Seller said" first className="@3xl:max-w-64 @3xl:shrink-0">
          <div className={NODE}>
            <SourceLine evidence={[claim.stated_in]} />
          </div>
        </Step>

        {trail.state === "not_checked" ? (
          <Step label="Status" last dashed className="@3xl:flex-1">
            <div className="hatch flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 self-start rounded-md border border-dashed border-not-checked-line px-2 py-1 text-not-checked">
              <p className="flex items-center gap-1.5 font-medium">
                <StatusGlyph status="not_checked" />
                Not checked · {reason ? NOT_CHECKED_REASON_LABEL[reason] : "reason not recorded"}
              </p>
              <p>No source was read, no fact was dated and no rule was applied</p>
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
          </Step>
        ) : (
          <>
            {/* 2 and 3. Where we looked, and what was found and when */}
            <Step
              className="@3xl:flex-1"
              label={
                <>
                  <ColumnHead className="leading-4 @3xl:hidden">Sources and dated facts</ColumnHead>
                  <div className={cn("hidden @3xl:grid", PAIR)}>
                    <ColumnHead className="leading-4">Sources</ColumnHead>
                    <span />
                    <ColumnHead className="leading-4">Dated facts</ColumnHead>
                  </div>
                </>
              }
            >
              <ul className="flex flex-col gap-2 @3xl:gap-1">
                {trail.sources.map((source, index) => (
                  <Fragment key={source.key}>
                    {trail.disagree && index > 0 ? (
                      <li className={cn("flex items-center gap-1.5 text-xs font-medium", STATUS_INK.conflicting_evidence)}>
                        <StatusGlyph status="conflicting_evidence" size={14} />
                        disagree
                      </li>
                    ) : null}
                    <TrailRow node={<SourceNode source={source} />}>
                      <ul className="flex flex-col pl-3 @3xl:pl-0">
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
                    node={<EmptyNode label={search.label ?? RELIABILITY_LABEL[search.reliability]} />}
                  >
                    <p className={cn(NODE, "pl-3 text-not-checked @3xl:pl-0")}>Searched, no record</p>
                  </TrailRow>
                ))}
                {trail.state === "nothing_found" && trail.emptySearches.length === 0 ? (
                  <TrailRow dashed node={<EmptyNode label="No evidence attached" />}>
                    <p className={cn(NODE, "pl-3 text-not-checked @3xl:pl-0")}>
                      Which sources were searched is not recorded
                    </p>
                  </TrailRow>
                ) : null}
              </ul>
            </Step>

            {/* 4. The rule: one short line, the full text behind "Why?" */}
            <Step label="Rule" className="@3xl:max-w-64 @3xl:shrink-0">
              <div className={cn(NODE, "min-w-0 gap-2")}>
                <span className="min-w-0 truncate text-ink" title={trail.rule.short}>
                  {trail.rule.short}
                </span>
                <RuleWhy>
                  <p className="text-ink">{trail.rule.text}</p>
                  {trail.rule.from === "status_definition" ? (
                    <p className="text-xs text-ink-muted">
                      What {CLAIM_STATUS_LABEL[claim.status]} means under the scoring policy. The
                      rule that fired for this claim is not recorded
                    </p>
                  ) : null}
                </RuleWhy>
              </div>
            </Step>

            {/* 5. The answer */}
            <Step label="Status" last className="@3xl:shrink-0">
              <div className={NODE}>
                <StatusMark status={claim.status} />
              </div>
            </Step>
          </>
        )}
      </ol>
    </section>
  );
}
