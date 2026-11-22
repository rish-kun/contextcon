"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { formatCredits } from "@/lib/format";
import {
  CLAIM_STATUS_LABEL,
  NOT_CHECKED_REASON_DETAIL,
  NOT_CHECKED_REASON_LABEL,
} from "@/lib/labels";
import { staggerDelay } from "@/lib/transitions";
import type { Claim, RecordStatement } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { PendingGlyph, StatusGlyph } from "./glyphs";
import { Fact, SourceLine } from "./source-line";
import { STATUS_INK, StatusLegend, StatusMark } from "./status-mark";
import { EvidenceTrail } from "@/components/explainers/evidence-trail";

/** Short labels for the 96px spine, where the full name does not fit on one line. */
const SPINE_LABEL: Record<Claim["status"], string[]> = {
  supported: ["Supported"],
  partially_corroborated: ["Partially", "corroborated"],
  conflicting_evidence: ["Conflicting", "evidence"],
  contradicted: ["Contradicted"],
  cannot_verify: ["Cannot", "verify"],
  not_checked: ["Not", "checked"],
};

function Statement({ statement }: { statement: RecordStatement }) {
  return (
    <Fact evidence={statement.evidence} estimate={statement.estimate} layout="stacked">
      {statement.text}
    </Fact>
  );
}

function RecordSide({
  claim,
  expanded,
  onRunCheck,
}: {
  claim: Claim;
  expanded: boolean;
  onRunCheck?: (claim: Claim) => void;
}) {
  if (claim.status === "not_checked") {
    const reason = claim.not_checked_reason;
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="font-medium text-not-checked">
          {CLAIM_STATUS_LABEL.not_checked} ·{" "}
          {reason ? NOT_CHECKED_REASON_LABEL[reason] : "reason not recorded"}
        </p>
        <p className="text-ink-secondary">
          {reason ? NOT_CHECKED_REASON_DETAIL[reason] : "This check did not run"}
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
    );
  }

  // A result with nothing attached is a result: the search found no record. It says so
  // plainly, with what would settle the claim.
  if (claim.record.length === 0) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="font-medium text-ink">No public record found</p>
        {claim.note ? <p className="text-ink-secondary">{claim.note}</p> : null}
        {claim.what_would_settle ? (
          <p className="text-ink">
            <span className="text-ink-muted">Would settle it: </span>
            {claim.what_would_settle}
          </p>
        ) : null}
      </div>
    );
  }

  const split = claim.status === "partially_corroborated";
  const supported = claim.record.filter((s) => s.part === "supported");
  const notSupported = claim.record.filter((s) => s.part === "not_supported");
  const plain = split ? claim.record.filter((s) => !s.part) : claim.record;
  const visiblePlain = expanded ? plain : plain.slice(0, 1);
  const hiddenCount = expanded ? 0 : plain.length - visiblePlain.length;

  return (
    <div className="flex flex-col items-start gap-3">
      {visiblePlain.map((statement) => (
        <Statement key={statement.text} statement={statement} />
      ))}
      {split && supported.length > 0 ? (
        <div className="flex flex-col items-start gap-1">
          <p className="text-xs text-ink-muted">Supported</p>
          {supported.map((statement) => (
            <Statement key={statement.text} statement={statement} />
          ))}
        </div>
      ) : null}
      {split && notSupported.length > 0 ? (
        <div className="flex flex-col items-start gap-1">
          <p className="text-xs text-ink-muted">Not supported</p>
          {notSupported.map((statement) => (
            <Statement key={statement.text} statement={statement} />
          ))}
        </div>
      ) : null}
      {hiddenCount > 0 ? (
        <p className="text-xs text-ink-muted">
          {hiddenCount} more {hiddenCount === 1 ? "statement" : "statements"}
        </p>
      ) : null}
      {expanded && claim.note ? <p className="text-ink-secondary">{claim.note}</p> : null}
      {claim.what_would_settle ? (
        <p className="text-ink">
          <span className="text-ink-muted">Would settle it: </span>
          {claim.what_would_settle}
        </p>
      ) : null}
    </div>
  );
}

export interface ClaimLedgerRowProps {
  claim: Claim;
  /** Position in the list, for the staggered entrance. */
  index?: number;
  /** The check is still running: the spine shows an open ring and "Checking". */
  pending?: boolean;
  /**
   * True when this row appeared because of an event the reader is watching, such as a
   * claim streamed in by a live run. Only then does it fade and rise. A ledger opened on
   * a finished case is simply there.
   */
  arrived?: boolean;
  /** Selected for the request list: accent tint and a left bar. */
  selected?: boolean;
  defaultExpanded?: boolean;
  /** Where "Changed in v2" links to. */
  changedHref?: string;
  /** Offers "Run check" on a Not checked row. Running it costs credits, and the button says so. */
  onRunCheck?: (claim: Claim) => void;
  /** Shown under the record when the row is expanded: evidence spans, dates, history. */
  detail?: React.ReactNode;
  /**
   * A followed run's view of this row, built from that run's own events. `spine` stands in
   * for the status mark while the claim has no status yet (waiting, queued, checking);
   * `body` stands in for the record; `trail` sits under the record once it has settled.
   */
  live?: { spine?: React.ReactNode; body?: React.ReactNode; trail?: React.ReactNode };
  className?: string;
}

/**
 * One row of the claim ledger: "Seller said" | status spine | "The record shows".
 * Enter, Space or a click expands the row in place; arrow keys move between rows.
 * Under 1024px the row stacks: claim, status tag, then the record.
 */
export function ClaimLedgerRow({
  claim,
  index = 0,
  pending = false,
  arrived = false,
  selected = false,
  defaultExpanded = false,
  changedHref,
  onRunCheck,
  detail,
  live,
  className,
}: ClaimLedgerRowProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  /** No status to show yet: the legacy `pending` flag, or a live run's own spine. */
  const unsettled = pending || live?.spine != null;
  const notChecked = claim.status === "not_checked" && !unsettled;

  function isOwnEvent(event: React.SyntheticEvent<HTMLElement>): boolean {
    const target = event.target as HTMLElement;
    // Events from popovers bubble through React portals; ignore anything outside the row,
    // and anything that is itself a control.
    return event.currentTarget.contains(target) && !target.closest("button, a, input");
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setExpanded((value) => !value);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const sibling =
        event.key === "ArrowDown"
          ? event.currentTarget.nextElementSibling
          : event.currentTarget.previousElementSibling;
      if (sibling instanceof HTMLElement && sibling.dataset.ledgerRow !== undefined) {
        event.preventDefault();
        sibling.focus();
      }
    }
  }

  return (
    <div
      role="row"
      data-ledger-row=""
      tabIndex={0}
      aria-expanded={expanded}
      aria-selected={selected}
      onClick={(event) => {
        if (isOwnEvent(event)) setExpanded((value) => !value);
      }}
      onKeyDown={onKeyDown}
      style={arrived ? { animationDelay: `${staggerDelay(index)}s` } : undefined}
      className={cn(
        arrived && "animate-row-in motion-reduce:animate-none",
        "focus-inset flex cursor-default flex-col border-b border-line text-dense transition-colors",
        selected ? "selected-bar bg-accent-tint" : "hover:bg-surface-raised",
        className,
      )}
    >
      {/* The three cells are one grid; the trail is a block of its own under it, in flow. */}
      <div
        role="presentation"
        className="grid gap-x-0 gap-y-3 px-4 py-3 lg:ledger-grid lg:gap-y-0 lg:px-0 lg:py-0"
      >
      <div role="gridcell" className="flex min-w-0 gap-3 lg:px-4 lg:py-3">
        <span className="w-5 shrink-0 text-right font-mono text-xs leading-5 text-ink-muted">
          {claim.number}
        </span>
        <div className="flex min-w-0 flex-col items-start gap-2">
          <p className={cn("text-ink", !expanded && "line-clamp-2")}>“{claim.text}”</p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs text-ink-muted">{claim.category}</span>
            <SourceLine evidence={[claim.stated_in]} />
            {claim.changed_in_version != null ? (
              changedHref ? (
                <a href={changedHref} className="rounded-xs">
                  <Badge variant="accent" className="font-mono text-2xs">
                    Changed in v{claim.changed_in_version}
                  </Badge>
                </a>
              ) : (
                <Badge variant="accent" className="font-mono text-2xs">
                  Changed in v{claim.changed_in_version}
                </Badge>
              )
            ) : null}
          </div>
        </div>
      </div>

      {/* The spine. From lg it is a continuous band down the ledger; below, a tag. */}
      <div
        role="gridcell"
        className={cn(
          "flex lg:flex-col lg:items-center lg:gap-1 lg:border-x lg:px-2 lg:py-3 lg:text-center",
          unsettled
            ? "text-ink-muted lg:border-line lg:bg-surface-sunken"
            : cn(STATUS_INK[claim.status], lgSurface(claim.status)),
        )}
      >
        {live?.spine != null ? (
          live.spine
        ) : pending ? (
          <span className="inline-flex animate-fade-in items-center gap-1 motion-reduce:animate-none lg:flex-col">
            <PendingGlyph />
            <span className="text-xs">Checking</span>
          </span>
        ) : (
          <>
            <span
              key={claim.status}
              className="hidden animate-settle flex-col items-center gap-1 motion-reduce:animate-none lg:flex"
            >
              <StatusGlyph status={claim.status} />
              <span className="text-xs leading-4 font-medium">
                {SPINE_LABEL[claim.status].map((word) => (
                  <span key={word} className="block">
                    {word}
                  </span>
                ))}
              </span>
            </span>
            <StatusMark
              status={claim.status}
              reason={claim.not_checked_reason}
              className="lg:hidden"
            />
          </>
        )}
      </div>

      <div role="gridcell" className="flex min-w-0 items-start gap-3 lg:px-4 lg:py-3">
        <div className="min-w-0 flex-1">
          {live?.body != null ? (
            live.body
          ) : pending ? (
            <p className="text-ink-muted">Gathering evidence for this claim</p>
          ) : (
            <RecordSide claim={claim} expanded={expanded || notChecked} onRunCheck={onRunCheck} />
          )}
          {live?.trail}
          {expanded && !unsettled && detail ? (
            <div className="mt-3 animate-fade-in border-t border-line pt-3 motion-reduce:animate-none">
              {detail}
            </div>
          ) : null}
        </div>
        <Icon
          icon={ChevronDown}
          className={cn(
            "mt-0.5 shrink-0 text-ink-muted transition-transform",
            expanded && "rotate-180",
          )}
        />
      </div>
      </div>
      {expanded && !unsettled ? (
        <EvidenceTrail claim={claim} role="gridcell" className="border-t border-line" />
      ) : null}
    </div>
  );
}

/** Spine fill from lg up. Written out in full so Tailwind can see every class. */
function lgSurface(status: Claim["status"]): string {
  switch (status) {
    case "supported":
      return "lg:border-supported-line lg:bg-supported-tint";
    case "partially_corroborated":
      return "lg:border-partial-line lg:bg-partial-tint";
    case "conflicting_evidence":
      return "lg:border-conflicting-line lg:bg-conflicting-tint";
    case "contradicted":
      return "lg:border-contradicted-line lg:bg-contradicted-tint";
    case "cannot_verify":
      return "lg:border-cannot-verify-line lg:bg-cannot-verify-tint";
    case "not_checked":
      return "lg:hatch lg:border-dashed lg:border-not-checked-line";
  }
}

/**
 * The ledger frame: the glyph legend, the column heads, and the rows.
 * Pass ClaimLedgerRow elements as children. Not checked rows must stay in the default view.
 */
export function ClaimLedger({
  children,
  label = "Claim ledger",
  legend = true,
  flush = false,
  className,
}: {
  children: React.ReactNode;
  label?: string;
  /** Off where the status filter above the ledger already names every glyph. */
  legend?: boolean;
  /** No frame of its own, for a ledger inside a flush panel body. */
  flush?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {legend ? <StatusLegend /> : null}
      <div
        role="grid"
        aria-label={label}
        className={cn(
          "overflow-hidden bg-surface [&>[data-ledger-row]:last-child]:border-b-0",
          !flush && "rounded-lg border border-line",
        )}
      >
        <div
          role="row"
          className="hidden border-b border-line-strong bg-surface-sunken text-xs font-medium text-ink-secondary lg:grid lg:ledger-grid"
        >
          <span role="columnheader" className="px-4 py-2 pl-12">
            Seller said
          </span>
          <span role="columnheader" className="px-2 py-2 text-center">
            Status
          </span>
          <span role="columnheader" className="px-4 py-2">
            The record shows
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}
