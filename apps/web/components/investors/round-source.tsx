"use client";

import { ExternalLink } from "lucide-react";
import type { SourceRef } from "@/lib/api/client";
import { formatAsOf, formatDateTime } from "@/lib/format";
import { RELIABILITY_LABEL, RELIABILITY_NOTE } from "@/lib/labels";
import type { ReliabilityClass } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SourceClassGlyph } from "@/components/dealproof";
import { Icon } from "@/components/ui/icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type SourceClass = SourceRef["source_class"];

/** A registry mirror is named as one. Every other class uses the product's shared wording. */
function describe(sourceClass: SourceClass): {
  reliability: ReliabilityClass;
  label: string;
  note: string;
} {
  if (sourceClass === "registry_mirror") {
    return {
      reliability: "registry",
      label: "Registry mirror",
      note: "A secondary copy of official filings. It shows what the mirror held on the stated date, not the filing itself",
    };
  }
  return {
    reliability: sourceClass,
    label: RELIABILITY_LABEL[sourceClass],
    note: RELIABILITY_NOTE[sourceClass],
  };
}

/**
 * The source chip for one funding round: where the record came from and the date of the
 * round, written "as of". It opens the record behind it. Same shape and wording as the
 * shared source chip, drawn from the API's own source reference.
 */
export function RoundSource({
  source,
  asOf,
  company,
  companyId,
  evidenceId,
  className,
}: {
  source: SourceRef;
  /** Date of the round, not of retrieval. */
  asOf: string | null;
  company: string;
  companyId: number;
  evidenceId: string | null;
  className?: string;
}) {
  const asOfText = formatAsOf(asOf);
  const { reliability, label, note } = describe(source.source_class);
  const isUrl = /^https?:\/\//.test(source.url_or_endpoint);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source: ${source.label}, ${asOfText}. Open the record`}
          className={cn(
            "inline-flex h-5.5 max-w-full items-center gap-1 rounded-xs border border-line bg-surface-raised px-1.5 text-xs text-ink-secondary transition-[background-color,border-color] hover:border-line-strong hover:bg-surface-sunken data-[state=open]:border-accent-line data-[state=open]:bg-accent-tint",
            className,
          )}
        >
          <SourceClassGlyph reliability={reliability} className="shrink-0 text-ink-muted" />
          <span className="truncate">{source.label}</span>
          <span aria-hidden className="text-ink-muted">
            ·
          </span>
          <span
            className={cn(
              "shrink-0 font-mono text-2xs",
              asOf ? "text-ink-secondary" : "text-ink-muted",
            )}
          >
            {asOfText}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="flex flex-col gap-3 text-dense">
          <div className="flex flex-col gap-1">
            <p className="flex items-center gap-2 text-sm font-medium text-ink">
              <SourceClassGlyph reliability={reliability} size={16} className="text-ink-muted" />
              {label}
            </p>
            <p className="text-xs text-ink-secondary">{note}</p>
          </div>

          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
            <dt className="text-ink-muted">Source</dt>
            <dd className="text-ink">{source.label}</dd>
            <dt className="text-ink-muted">Round dated</dt>
            <dd className="font-mono text-2xs text-ink">{asOfText}</dd>
            <dt className="text-ink-muted">Retrieved</dt>
            <dd className="font-mono text-2xs text-ink">
              {formatDateTime(source.retrieved_at) ?? "time not recorded"}
            </dd>
            <dt className="text-ink-muted">Provider</dt>
            <dd className="text-ink">{source.provider}</dd>
            <dt className="text-ink-muted">Attached to</dt>
            <dd className="text-ink">
              {company}
              <span className="text-ink-secondary"> · matched on company id {companyId}</span>
            </dd>
            {!isUrl ? (
              <>
                <dt className="text-ink-muted">Request</dt>
                <dd className="font-mono text-2xs break-all text-ink">{source.url_or_endpoint}</dd>
              </>
            ) : null}
            {evidenceId ? (
              <>
                <dt className="text-ink-muted">Record</dt>
                <dd className="font-mono text-2xs break-all text-ink">{evidenceId}</dd>
              </>
            ) : null}
          </dl>

          {isUrl ? (
            <a
              href={source.url_or_endpoint}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-start gap-1 rounded-xs text-xs break-all text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
            >
              <Icon icon={ExternalLink} size={14} className="mt-px shrink-0" />
              {source.url_or_endpoint}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
