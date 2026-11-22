"use client";

import { ExternalLink } from "lucide-react";
import { useId, useState } from "react";
import { formatAsOf, formatDateTime } from "@/lib/format";
import { RELIABILITY_LABEL, RELIABILITY_NOTE } from "@/lib/labels";
import type { EstimateMeta, Evidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RuleBreakBlock } from "./blocks";
import { EstimateLabel } from "./estimate-label";
import { SourceClassGlyph } from "./glyphs";

/**
 * The source chip: class glyph, source name, mono "as of" date. It is a button; click or
 * Enter opens the evidence popover with the exact quote or field, the reliability class
 * in words, the URL or request, the retrieval time and the entity it was attached to.
 */
export function SourceChip({
  evidence,
  compact = false,
  className,
}: {
  evidence: Evidence;
  /**
   * For tight places such as a stat tile: the glyph and the date when it is known, or the
   * glyph and the source name when it is not. The full name and "as of" line are in the
   * hint and in the popover.
   */
  compact?: boolean;
  className?: string;
}) {
  const { source } = evidence;
  const asOf = formatAsOf(source.as_of);
  const dated = Boolean(source.as_of);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source: ${source.label}, ${asOf}. Open the evidence`}
          title={compact ? `${source.label} · ${asOf}` : undefined}
          className={cn(
            "inline-flex h-5.5 max-w-full items-center gap-1 rounded-xs border border-line bg-surface-raised px-1.5 text-xs text-ink-secondary transition-[background-color,border-color] hover:border-line-strong hover:bg-surface-sunken data-[state=open]:border-accent-line data-[state=open]:bg-accent-tint",
            className,
          )}
        >
          <SourceClassGlyph reliability={source.reliability} className="shrink-0 text-ink-muted" />
          {compact && dated ? null : <span className="truncate">{source.label}</span>}
          {compact || !dated ? null : (
            <span aria-hidden className="text-ink-muted">
              ·
            </span>
          )}
          {/* An unknown date is not printed. The popover says the fact is undated. */}
          {!dated ? null : (
            <span
              className={cn(
                "shrink-0 font-mono text-2xs",
                dated ? "text-ink-secondary" : "text-ink-muted",
              )}
            >
              {asOf}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <EvidenceDetail evidence={evidence} />
      </PopoverContent>
    </Popover>
  );
}

/** The body of the evidence popover. Also usable inside a drawer on small screens. */
export function EvidenceDetail({ evidence }: { evidence: Evidence }) {
  const { source } = evidence;
  const retrieved = formatDateTime(source.retrieved_at);

  return (
    <div className="flex flex-col gap-3 text-dense">
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <SourceClassGlyph reliability={source.reliability} size={16} className="text-ink-muted" />
          {source.class_label ?? RELIABILITY_LABEL[source.reliability]}
        </p>
        <p className="text-xs text-ink-secondary">{source.class_note ?? RELIABILITY_NOTE[source.reliability]}</p>
      </div>

      {evidence.quote ? (
        <blockquote className="border-l-2 border-line-strong pl-3 text-ink">
          “{evidence.quote}”
        </blockquote>
      ) : null}
      {evidence.field_path ? (
        <p className="rounded-xs bg-surface-sunken px-2 py-1 font-mono text-2xs break-all text-ink">
          {evidence.field_path}
          {evidence.value ? ` = ${evidence.value}` : null}
        </p>
      ) : null}

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <dt className="text-ink-muted">Source</dt>
        <dd className="text-ink">{source.label}</dd>
        <dt className="text-ink-muted">Fact dated</dt>
        <dd className="font-mono text-2xs text-ink">{formatAsOf(source.as_of)}</dd>
        <dt className="text-ink-muted">Retrieved</dt>
        <dd className="font-mono text-2xs text-ink">{retrieved ?? "time not recorded"}</dd>
        <dt className="text-ink-muted">Provider</dt>
        <dd className="text-ink">{source.provider}</dd>
        {evidence.attached_to ? (
          <>
            <dt className="text-ink-muted">Attached to</dt>
            <dd className="text-ink">
              {evidence.attached_to.entity_name}
              <span className="text-ink-secondary">
                {" "}
                · matched on {evidence.attached_to.matched_on}
              </span>
            </dd>
          </>
        ) : null}
        {source.request ? (
          <>
            <dt className="text-ink-muted">Request</dt>
            <dd className="font-mono text-2xs break-all text-ink">{source.request}</dd>
          </>
        ) : null}
      </dl>

      {source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-start gap-1 rounded-xs text-xs break-all text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
        >
          <Icon icon={ExternalLink} size={14} className="mt-px shrink-0" />
          {source.url}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : null}
    </div>
  );
}

/** True when a fact carries at least one evidence reference. Check it before drawing the value. */
export function hasSource(evidence: Evidence[] | null | undefined): evidence is Evidence[] {
  return Array.isArray(evidence) && evidence.length > 0;
}

/**
 * The source line: the chips that end every fact. At most `max` are visible; the rest
 * open in place behind "+N". That button stays where it is once opened and becomes
 * "Show fewer", so keyboard focus is never left on a control that has gone.
 */
export function SourceLine({
  evidence,
  max = 2,
  compact = false,
  className,
}: {
  evidence: Evidence[];
  max?: number;
  /** Short chips for tight places: see `SourceChip`. */
  compact?: boolean;
  className?: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const id = useId();
  if (!hasSource(evidence)) return <Unsourced />;

  const extra = Math.max(evidence.length - max, 0);
  const visible = showAll ? evidence : evidence.slice(0, max);

  return (
    <span
      id={id}
      className={cn("inline-flex max-w-full flex-wrap items-center gap-1", className)}
    >
      {visible.map((item, index) => (
        <SourceChip key={item.id ?? `${item.source.label}-${index}`} evidence={item} compact={compact} />
      ))}
      {extra > 0 ? (
        <button
          type="button"
          onClick={() => setShowAll((value) => !value)}
          aria-expanded={showAll}
          aria-controls={id}
          aria-label={`${extra} more ${extra === 1 ? "source" : "sources"}`}
          className={cn(
            "inline-flex h-5.5 items-center rounded-xs border border-line bg-surface px-1.5 text-2xs text-ink-secondary transition-colors hover:bg-surface-raised",
            !showAll && "font-mono",
          )}
        >
          {showAll ? "Show fewer" : `+${extra}`}
        </button>
      ) : null}
    </span>
  );
}

/**
 * No source, no render. In development a missing evidence reference shows a visible
 * error; in production the fact is left out and the omission is logged.
 */
export function Unsourced({ what }: { what?: string }) {
  if (process.env.NODE_ENV === "production") {
    console.error(`DealProof: a fact was omitted because it has no source${what ? `: ${what}` : ""}`);
    return null;
  }
  return <UnsourcedBlock what={what} />;
}

/** The visible form of the "Unsourced" error. Exported so the gallery can show it. */
export function UnsourcedBlock({ what }: { what?: string }) {
  return (
    <RuleBreakBlock title="Unsourced" className="inline-block">
      {what ? `“${what}” has` : "This fact has"} no evidence reference. It is left out in
      production.
    </RuleBreakBlock>
  );
}

/**
 * A rendered fact: the statement, then its source line. `evidence` is required and must
 * not be empty; without it nothing is shown.
 *
 *   <Fact evidence={[registryEvidence]}>Incorporated 2014, Pune</Fact>
 *   <Fact evidence={[profiles]} estimate={{ kind: "estimate", basis: "…" }}>180 people</Fact>
 */
export function Fact({
  children,
  evidence,
  estimate,
  layout = "inline",
  className,
}: {
  children: React.ReactNode;
  evidence: Evidence[];
  /** Marks the value as an Estimate or a Signal. */
  estimate?: EstimateMeta | null;
  /** inline: chips follow the text. stacked: chips sit on their own line under it. */
  layout?: "inline" | "stacked";
  className?: string;
}) {
  if (!hasSource(evidence)) {
    return <Unsourced what={typeof children === "string" ? children : undefined} />;
  }
  return (
    <span
      className={cn(
        layout === "stacked"
          ? "flex flex-col items-start gap-1"
          : "inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1",
        className,
      )}
    >
      <span className="text-ink">
        {estimate ? (
          <EstimateLabel kind={estimate.kind} basis={estimate.basis}>
            {children}
          </EstimateLabel>
        ) : (
          children
        )}
      </span>
      <SourceLine evidence={evidence} />
    </span>
  );
}
