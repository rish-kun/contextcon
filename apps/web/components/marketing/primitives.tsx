/**
 * Home-page versions of the product's marks: status glyph and tag, disposition stamp,
 * source line, estimate. They follow docs/design/design-direction.md section 6.
 *
 * These are static (no popovers). When `components/dealproof` ships StatusMark,
 * DispositionStamp, SourceLine and EstimateValue, the home page should use those.
 */
import {
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  FileText,
  Landmark,
  Megaphone,
  Search,
  Users,
} from "lucide-react";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import type { ClaimStatus, Disposition } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { SourceKind, SourceRef } from "./content";

/* ───────────────────────── Layout ───────────────────────── */

export function Container({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-(--layout-marketing-max) px-4 md:px-6 lg:px-8",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SectionHead({
  eyebrow,
  title,
  lead,
  className,
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  className?: string;
}) {
  return (
    <div className={cn("max-w-2xl", className)}>
      {eyebrow ? (
        <p className="mb-3 text-sm text-ink-muted">{eyebrow}</p>
      ) : null}
      <h2 className="font-serif text-3xl text-balance text-ink lg:text-4xl lg:tracking-display">
        {title}
      </h2>
      {lead ? (
        <p className="mt-4 text-base text-pretty text-ink-secondary lg:text-lg">
          {lead}
        </p>
      ) : null}
    </div>
  );
}

export function IllustrationLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-xs border border-line-strong px-2 text-xs text-ink-secondary",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ───────────────────────── Claim statuses ───────────────────────── */

/** Six glyphs with six silhouettes, so the set reads without colour. */
export function StatusGlyph({
  status,
  className,
}: {
  status: ClaimStatus;
  className?: string;
}) {
  const common = {
    viewBox: "0 0 16 16",
    className: cn("size-4 shrink-0", className),
    fill: "none",
    "aria-hidden": true,
  } as const;
  const stroke = {
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  } as const;
  const knockout = { ...stroke, stroke: "var(--color-surface)" } as const;

  switch (status) {
    case "supported":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="7" fill="currentColor" />
          <path d="m5 8.3 2 2 4-4.5" {...knockout} />
        </svg>
      );
    case "contradicted":
      return (
        <svg {...common}>
          <path
            d="M5.1 1h5.8L15 5.1v5.8L10.9 15H5.1L1 10.9V5.1z"
            fill="currentColor"
          />
          <path d="m5.7 5.7 4.6 4.6m0-4.6-4.6 4.6" {...knockout} />
        </svg>
      );
    case "partially_corroborated":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.25" {...stroke} />
          <path d="M8 1.75a6.25 6.25 0 0 0 0 12.5z" fill="currentColor" />
        </svg>
      );
    case "conflicting_evidence":
      return (
        <svg {...common}>
          <path d="M8 1.2 14.8 8 8 14.8 1.2 8z" {...stroke} />
          <path
            d="M5.4 8h5.2M6.6 6.8 5.4 8l1.2 1.2m2.8-2.4L10.6 8 9.4 9.2"
            {...stroke}
            strokeWidth={1.25}
          />
        </svg>
      );
    case "cannot_verify":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.25" {...stroke} />
          <path d="M6.3 6.4a1.75 1.75 0 1 1 2.7 1.45c-.6.4-1 .8-1 1.4" {...stroke} />
          <circle cx="8" cy="11.4" r="0.8" fill="currentColor" />
        </svg>
      );
    case "not_checked":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.25" {...stroke} strokeDasharray="2.6 2.31" />
        </svg>
      );
  }
}

const STATUS_INK: Record<ClaimStatus, string> = {
  supported: "text-supported",
  contradicted: "text-contradicted",
  partially_corroborated: "text-partial",
  conflicting_evidence: "text-conflicting",
  cannot_verify: "text-cannot-verify",
  not_checked: "text-not-checked",
};

const STATUS_TAG: Record<ClaimStatus, string> = {
  supported: "border-supported-line bg-supported-tint",
  contradicted: "border-contradicted-line bg-contradicted-tint",
  partially_corroborated: "border-partial-line bg-partial-tint",
  conflicting_evidence: "border-conflicting-line bg-conflicting-tint",
  cannot_verify: "border-cannot-verify-line bg-cannot-verify-tint",
  not_checked: "hatch border-dashed border-not-checked-line",
};

export function statusInk(status: ClaimStatus): string {
  return STATUS_INK[status];
}

/** Glyph + label. The default form of a status. */
export function StatusTag({
  status,
  className,
}: {
  status: ClaimStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 text-xs font-medium whitespace-nowrap",
        STATUS_INK[status],
        STATUS_TAG[status],
        className,
      )}
    >
      <StatusGlyph status={status} />
      {CLAIM_STATUS_LABEL[status]}
    </span>
  );
}

/** Glyph + mono number, for summaries. */
export function StatusCount({
  status,
  count,
}: {
  status: ClaimStatus;
  count: number;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs",
        STATUS_INK[status],
      )}
    >
      <StatusGlyph status={status} />
      <span className="font-mono">{count}</span>
      <span className="text-ink-secondary">{CLAIM_STATUS_LABEL[status]}</span>
    </span>
  );
}

/* ───────────────────────── Dispositions ───────────────────────── */

const DISPOSITION_STYLE: Record<Disposition, string> = {
  prioritise: "text-prioritise bg-prioritise-tint",
  investigate_further: "text-investigate bg-investigate-tint",
  deprioritise: "text-deprioritise bg-deprioritise-tint",
  cannot_assess: "text-cannot-assess bg-cannot-assess-tint",
};

function DispositionGlyph({ disposition }: { disposition: Disposition }) {
  const props = {
    className: "size-4 shrink-0",
    strokeWidth: 1.75,
    "aria-hidden": true,
  } as const;
  switch (disposition) {
    case "prioritise":
      return <ArrowUpRight {...props} />;
    case "investigate_further":
      return <Search {...props} />;
    case "deprioritise":
      return <ArrowDownRight {...props} />;
    case "cannot_assess":
      return <StatusGlyph status="cannot_verify" />;
  }
}

/** A disposition is a stamp, not a tag: taller, heavier border, weight 600. */
export function DispositionStamp({
  disposition,
  className,
}: {
  disposition: Disposition;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-8 items-center gap-2 rounded-sm border-stamp border-current px-3 text-sm font-semibold whitespace-nowrap",
        DISPOSITION_STYLE[disposition],
        className,
      )}
    >
      <DispositionGlyph disposition={disposition} />
      {DISPOSITION_LABEL[disposition]}
    </span>
  );
}

/* ───────────────────────── Source line ───────────────────────── */

const SOURCE_ICON: Record<SourceKind, typeof Landmark> = {
  registry: Landmark,
  profiles: Users,
  announcement: Megaphone,
  funding: Banknote,
  document: FileText,
};

/** The signature: where a fact came from and the date of the fact. */
export function SourceChip({ kind, label, asOf }: SourceRef) {
  const Icon = SOURCE_ICON[kind];
  return (
    <span className="inline-flex min-h-5.5 max-w-full items-center gap-1.5 rounded-xs border border-line bg-surface-raised px-1.5 text-xs text-ink-secondary">
      <Icon className="size-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} aria-hidden />
      <span>{label}</span>
      <span className="font-mono text-2xs whitespace-nowrap text-ink-muted">
        as of {asOf}
      </span>
    </span>
  );
}

export function DocChip({ label }: { label: string }) {
  return (
    <span className="inline-flex min-h-5.5 items-center gap-1.5 rounded-xs border border-line bg-surface-raised px-1.5 text-xs text-ink-secondary">
      <FileText className="size-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} aria-hidden />
      {label}
    </span>
  );
}

/** A value that is not a recorded fact: tilde, dotted underline and the word. */
export function Estimate({
  value,
  kind,
}: {
  value: string;
  kind: "Estimate" | "Signal";
}) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="underline-estimate font-mono text-ink">{value}</span>
      <span className="font-mono text-2xs text-ink-muted">{kind}</span>
    </span>
  );
}

/* ───────────────────────── Actions ───────────────────────── */

const BUTTON_BASE =
  "press inline-flex h-11 items-center justify-center gap-2 rounded-md px-5 text-sm font-medium whitespace-nowrap transition-[background-color,border-color,transform]";

export const buttonPrimary = cn(
  BUTTON_BASE,
  "bg-ink text-ink-inverse shadow-xs hover:bg-ink-secondary",
);

export const buttonSecondary = cn(
  BUTTON_BASE,
  "border border-line-strong bg-surface text-ink hover:bg-surface-raised",
);
