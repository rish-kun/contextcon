"use client";

import { ArrowRight, ChevronRight } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import type { AssessmentChange } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Icon } from "@/components/ui/icon";
import { RuleBreakBlock } from "./blocks";
import { type ClaimChange, type ClaimGroup, organiseChanges, shortPolicyPair } from "./change-groups";
import { DispositionStamp } from "./disposition-stamp";
import { hasSource, SourceLine, Unsourced } from "./source-line";
import { StatusMark } from "./status-mark";

function BeforeAfter({
  before,
  after,
  srBefore,
  srAfter,
}: {
  before: React.ReactNode;
  after: React.ReactNode;
  srBefore: string;
  srAfter: string;
}) {
  return (
    <p className="flex flex-wrap items-center gap-2">
      <span className="sr-only">
        Changed from {srBefore} to {srAfter}.
      </span>
      <span aria-hidden className="inline-flex items-center rounded-sm bg-diff-removed p-1">
        {before}
      </span>
      <Icon icon={ArrowRight} className="text-ink-muted" />
      <span aria-hidden className="inline-flex items-center rounded-sm bg-diff-added p-1">
        {after}
      </span>
    </p>
  );
}

/** A value with nothing before it: said in words, never as a struck-through blank. */
function FirstValue({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <p className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-ink-muted">{label}</span>
      {children}
    </p>
  );
}

/** A scoring-policy version pair in mono, short when the two share a month. */
function PolicyPair({ from, to, arrow = false }: { from: string; to: string; arrow?: boolean }) {
  const [a, b] = shortPolicyPair(from, to);
  return (
    <span className="font-mono text-xs whitespace-nowrap" title={`Scoring policy ${from} to ${to}`}>
      {a} {arrow ? "→" : "to"} {b}
    </span>
  );
}

/** What a change is about: the claim, the disposition, or the name of a judgment. */
export function ChangeHeading({ change }: { change: AssessmentChange }) {
  if (change.kind === "claim_status") {
    return (
      <>
        {change.claim_number > 0 ? (
          <span className="font-mono text-xs text-ink-muted">Claim {change.claim_number}</span>
        ) : null}
        <span className="text-ink">“{change.claim_text}”</span>
      </>
    );
  }
  return (
    <span className="text-ink">
      {change.kind === "disposition" ? "Screening disposition" : change.label}
    </span>
  );
}

/**
 * Old → new, both drawn in full: the old value keeps its real mark with the label struck
 * through. An upgrade and a downgrade are drawn the same way. A first value has no old
 * one, and says "New status".
 */
export function ChangeValues({ change }: { change: AssessmentChange }) {
  if (change.kind === "claim_status") {
    if (change.before === null) {
      return (
        <FirstValue label="New status">
          <StatusMark status={change.after} />
        </FirstValue>
      );
    }
    return (
      <BeforeAfter
        srBefore={CLAIM_STATUS_LABEL[change.before]}
        srAfter={CLAIM_STATUS_LABEL[change.after]}
        before={<StatusMark status={change.before} struck />}
        after={<StatusMark status={change.after} />}
      />
    );
  }
  if (change.kind === "disposition") {
    return (
      <BeforeAfter
        srBefore={DISPOSITION_LABEL[change.before]}
        srAfter={DISPOSITION_LABEL[change.after]}
        before={<DispositionStamp disposition={change.before} struck />}
        after={<DispositionStamp disposition={change.after} />}
      />
    );
  }
  if (change.before === null) {
    return (
      <FirstValue label="New">
        <span className="font-mono text-xs font-medium text-ink">{change.after}</span>
      </FirstValue>
    );
  }
  return (
    <BeforeAfter
      srBefore={change.before}
      srAfter={change.after}
      before={
        <span className="px-1 font-mono text-xs text-ink-secondary line-through">{change.before}</span>
      }
      after={<span className="px-1 font-mono text-xs font-medium text-ink">{change.after}</span>}
    />
  );
}

/** Why a change happened, with its source. A status or disposition with no cause is a bug. */
export function ChangeBecause({ change }: { change: AssessmentChange }) {
  const evidence = change.evidence ?? [];
  const cause = change.kind === "claim_status" ? change.cause : undefined;

  if (cause?.kind === "policy") {
    return (
      <p className="text-ink">
        <span className="text-ink-muted">Because: </span>the scoring policy changed from{" "}
        <PolicyPair from={cause.from} to={cause.to} />
      </p>
    );
  }
  if (cause?.kind === "evidence" && hasSource(evidence)) {
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ink">
        <span className="text-ink-muted">Because of new evidence</span>
        <SourceLine evidence={evidence} />
      </p>
    );
  }

  const reason = cause?.kind === "evidence_removed" ? `evidence no longer used: ${cause.sources}` : change.reason;
  if (!reason) {
    // Derived figures may move without their own cause; a status or disposition may not.
    if (change.kind === "value") return null;
    return (
      <RuleBreakBlock title="No stated cause">
        Every change must say why it happened and carry a source.
      </RuleBreakBlock>
    );
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <p className="text-ink">
        <span className="text-ink-muted">Because: </span>
        {reason}
      </p>
      {hasSource(evidence) ? <SourceLine evidence={evidence} /> : null}
    </div>
  );
}

/**
 * A claim status is a fact about the record, so a changed one needs its evidence. The
 * one exception names its own cause: a scoring-policy update re-reads the same evidence.
 * Dispositions and judgments move because a claim did, and may carry none.
 */
export function isUnsourcedChange(change: AssessmentChange): boolean {
  return (
    change.kind === "claim_status" && change.cause?.kind !== "policy" && !hasSource(change.evidence)
  );
}

const CHANGED = "animate-changed motion-reduce:animate-none";

function ChangedTag() {
  return (
    <Badge variant="accent" className="hidden font-mono text-2xs motion-reduce:inline-flex">
      Changed
    </Badge>
  );
}

function ChangeRow({
  change,
  highlight,
  rowClassName,
}: {
  change: AssessmentChange;
  highlight: boolean;
  rowClassName: string;
}) {
  // Checked before anything is drawn: an unsourced status change shows neither status.
  // In production the row is left out and logged; in development it is the error alone.
  if (isUnsourcedChange(change) && change.kind === "claim_status") {
    const what = `Claim ${change.claim_number} status change`;
    if (process.env.NODE_ENV === "production") return <Unsourced what={what} />;
    return (
      <li className={cn("flex flex-col items-start gap-2", rowClassName)}>
        <Unsourced what={what} />
      </li>
    );
  }
  return (
    <li className={cn("flex flex-col gap-2", rowClassName, highlight && CHANGED)}>
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <ChangeHeading change={change} />
        {highlight ? <ChangedTag /> : null}
      </p>
      <ChangeValues change={change} />
      <ChangeBecause change={change} />
    </li>
  );
}

/** One claim of a group, on one line: which claim, and the status it took. */
function GroupLine({ change, allFirst }: { change: ClaimChange; allFirst: boolean }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2">
      <span className="flex min-w-0 flex-1 basis-56 items-baseline gap-2">
        {change.claim_number > 0 ? (
          <span className="shrink-0 font-mono text-xs text-ink-muted">Claim {change.claim_number}</span>
        ) : null}
        <span className="truncate text-ink" title={change.claim_text}>
          “{change.claim_text}”
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {change.before !== null ? (
          <>
            <span className="sr-only">
              Changed from {CLAIM_STATUS_LABEL[change.before]} to {CLAIM_STATUS_LABEL[change.after]}.
            </span>
            <StatusMark status={change.before} struck />
            <Icon icon={ArrowRight} className="text-ink-muted" />
          </>
        ) : allFirst ? null : (
          <span className="text-xs text-ink-muted">New status</span>
        )}
        <StatusMark status={change.after} />
      </span>
    </li>
  );
}

/**
 * Many claims, one cause: a single row that says what happened and how the claims came
 * out, and opens to one line per claim. In print the lines are always there.
 */
function GroupRow({
  group,
  highlight,
  rowClassName,
}: {
  group: ClaimGroup;
  highlight: boolean;
  rowClassName: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const count = group.changes.length;
  return (
    <li className={cn("flex flex-col gap-2", rowClassName, highlight && CHANGED)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-2 rounded-xs text-left"
      >
        <Icon
          icon={ChevronRight}
          className={cn("mt-0.5 shrink-0 text-ink-muted transition-transform print:hidden", open && "rotate-90")}
        />
        <span className="flex min-w-0 flex-col items-start gap-2">
          <span className="text-ink">
            Policy update <PolicyPair from={group.cause.from} to={group.cause.to} arrow />{" "}
            {group.allFirst
              ? `gave ${count} claims their first status`
              : `changed the status of ${count} claims`}
            {highlight ? (
              <>
                {" "}
                <ChangedTag />
              </>
            ) : null}
          </span>
          <span className="flex flex-wrap items-center gap-1">
            {group.counts.map(({ status, count: n }) => (
              <StatusMark key={status} status={status} count={n} />
            ))}
          </span>
        </span>
      </button>
      <ul
        id={id}
        aria-label={`The ${count} claims`}
        className={cn(
          "ml-6 flex-col divide-y divide-line rounded-md border border-line bg-surface",
          open ? "flex" : "hidden print:flex",
        )}
      >
        {group.changes.map((change, index) => (
          <GroupLine key={`${change.claim_number}-${index}`} change={change} allFirst={group.allFirst} />
        ))}
      </ul>
    </li>
  );
}

/**
 * What changed in a version, in the order a reader decides by: the disposition, the
 * judgments, then each claim that moved for a reason of its own (contradicted and
 * supported first, with the source that moved it), and last the claims that share one
 * cause, folded into a single row. Used by the memo's diff and by the change timeline,
 * so a change is drawn one way everywhere.
 */
export function ChangeList({
  changes,
  highlight = false,
  rowClassName = "px-4 py-3",
  className,
  ...props
}: {
  changes: AssessmentChange[];
  /** One-time accent highlight on each row, for a version that has just arrived. */
  highlight?: boolean;
  /** Padding of each row, which differs between a panel and the timeline. */
  rowClassName?: string;
} & Omit<React.ComponentProps<"ul">, "children">) {
  const organised = useMemo(() => organiseChanges(changes), [changes]);
  const rows = [...organised.disposition, ...organised.judgments, ...organised.claims];
  return (
    <ul className={cn("flex flex-col divide-y divide-line text-dense", className)} {...props}>
      {rows.map((change, index) => (
        <ChangeRow key={index} change={change} highlight={highlight} rowClassName={rowClassName} />
      ))}
      {organised.groups.map((group) => (
        <GroupRow key={group.key} group={group} highlight={highlight} rowClassName={rowClassName} />
      ))}
    </ul>
  );
}
