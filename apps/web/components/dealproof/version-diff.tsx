import { ArrowRight } from "lucide-react";
import { formatDateTime, plural } from "@/lib/format";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import type { AssessmentChange, AssessmentDiff, AssessmentVersionMeta } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { RuleBreakBlock } from "./blocks";
import { DispositionStamp } from "./disposition-stamp";
import { hasSource, SourceLine, Unsourced } from "./source-line";
import { StatusMark } from "./status-mark";

/**
 * On the Assessment tab the rail and the diff are drawn as one joined view,
 * `ChangeTimeline` in components/explainers, which puts the cause between two versions
 * and hangs the consequences under the claim that moved. `VersionRail` and `VersionDiff`
 * stay for places that need one without the other; the timeline reuses the parts
 * exported below so a change is drawn the same way everywhere.
 */

/**
 * The version rail: dated nodes, oldest first. The current version is a filled node and
 * says "current" in words. Pass `onOpen` to let a reader open an earlier version read-only.
 */
export function VersionRail({
  versions,
  current,
  viewing,
  onOpen,
  className,
}: {
  versions: AssessmentVersionMeta[];
  current: number;
  /** The version open on the page, when it is not the current one. */
  viewing?: number;
  onOpen?: (version: number) => void;
  className?: string;
}) {
  return (
    <ol className={cn("flex flex-col", className)} aria-label="Assessment history">
      {versions.map((item, index) => {
        const isCurrent = item.version === current;
        const last = index === versions.length - 1;
        return (
          <li key={item.version} className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-3">
            <span className="flex flex-col items-center" aria-hidden>
              <span
                className={cn(
                  "mt-1 size-3 shrink-0 rounded-full border-2 border-ink",
                  isCurrent ? "bg-ink" : "bg-surface",
                )}
              />
              {last ? null : <span className="w-px flex-1 bg-line-strong" />}
            </span>
            <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1", last ? "pb-0" : "pb-4")}>
              <span className={cn("font-mono text-xs text-ink", isCurrent && "font-medium")}>
                v{item.version}
              </span>
              <span className="font-mono text-xs text-ink-secondary">
                {formatDateTime(item.created_at)}
              </span>
              <span className="text-dense text-ink-secondary">· {item.trigger}</span>
              {isCurrent ? (
                <Badge variant="mono">current</Badge>
              ) : null}
              {item.version === viewing && !isCurrent ? (
                <Badge variant="accent" className="font-mono text-2xs">
                  reading
                </Badge>
              ) : onOpen && item.version !== (viewing ?? current) ? (
                <Button
                  variant="link"
                  size="inline"
                  className="text-xs font-normal"
                  onClick={() => onOpen(item.version)}
                >
                  Open version {item.version}
                </Button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Shown above a case that is open at an earlier version. */
export function ReadingOldVersionBanner({
  reading,
  current,
  className,
  children,
}: {
  reading: number;
  current: number;
  className?: string;
  /** A way back, for example a link that opens the current version. */
  children?: React.ReactNode;
}) {
  return (
    <p
      role="status"
      className={cn(
        "rounded-md border border-accent-line bg-accent-tint px-3 py-2 text-dense text-accent",
        className,
      )}
    >
      You are reading version {reading}. Version {current} is current
      {children ? <> · {children}</> : null}
    </p>
  );
}

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

/** What a change is about: the claim, the disposition, or the name of a derived figure. */
export function ChangeHeading({ change }: { change: AssessmentChange }) {
  if (change.kind === "claim_status") {
    return (
      <>
        <span className="font-mono text-xs text-ink-muted">Claim {change.claim_number}</span>
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
 * through. An upgrade and a downgrade are drawn the same way.
 */
export function ChangeValues({ change }: { change: AssessmentChange }) {
  if (change.kind === "claim_status") {
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
  const reason = change.reason;
  const evidence = change.evidence ?? [];
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
 * A claim status is a fact about the record, so a changed one needs its evidence.
 * Dispositions and derived figures move because a claim did, and may carry none.
 */
export function isUnsourcedChange(change: AssessmentChange): boolean {
  return change.kind === "claim_status" && !hasSource(change.evidence);
}

const PRODUCTION = process.env.NODE_ENV === "production";

function ChangeRow({ change, highlight }: { change: AssessmentChange; highlight: boolean }) {
  // A claim status is a fact about the record, so a changed one needs its evidence, and
  // that is checked before anything is drawn: an unsourced change shows neither status.
  // In production the row is left out and logged; in development it is the error alone.
  // Dispositions and derived figures move because a claim did, and may carry none.
  if (isUnsourcedChange(change) && change.kind === "claim_status") {
    const what = `Claim ${change.claim_number} status change`;
    if (PRODUCTION) return <Unsourced what={what} />;
    return (
      <li className="flex flex-col items-start gap-2 px-4 py-3 text-dense">
        <Unsourced what={what} />
      </li>
    );
  }

  return (
    <li
      className={cn(
        "flex flex-col gap-2 px-4 py-3 text-dense",
        highlight && "animate-changed motion-reduce:animate-none",
      )}
    >
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <ChangeHeading change={change} />
        {highlight ? (
          <Badge variant="accent" className="hidden font-mono text-2xs motion-reduce:inline-flex">
            Changed
          </Badge>
        ) : null}
      </p>
      <ChangeValues change={change} />
      <ChangeBecause change={change} />
    </li>
  );
}

/**
 * What changed between two assessment versions. Every change is shown as old → new with
 * both drawn in full: the old value keeps its real mark with the label struck through.
 * A downgrade looks exactly like an upgrade: no celebration and no softening.
 */
export function VersionDiff({
  diff,
  highlight = false,
  onShowUnchanged,
  className,
}: {
  diff: AssessmentDiff;
  /** One-time accent highlight on each changed row, for a version that has just arrived. */
  highlight?: boolean;
  onShowUnchanged?: () => void;
  className?: string;
}) {
  return (
    <section
      aria-label={`What changed in version ${diff.to_version}`}
      className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h3 className="text-sm font-medium text-ink">What changed in v{diff.to_version}</h3>
        <p className="font-mono text-2xs text-ink-secondary">
          v{diff.from_version} → v{diff.to_version}
        </p>
      </header>
      {diff.changes.length === 0 ? (
        <p className="px-4 py-3 text-dense text-ink-secondary">Nothing changed</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line">
          {diff.changes.map((change, index) => (
            <ChangeRow key={index} change={change} highlight={highlight} />
          ))}
        </ul>
      )}
      <footer className="flex flex-wrap items-center gap-3 border-t border-line bg-surface-raised px-4 py-2 text-xs text-ink-secondary">
        <span>{plural(diff.unchanged_claims, "claim")} unchanged</span>
        {onShowUnchanged ? (
          <Button variant="link" size="inline" className="text-xs font-normal" onClick={onShowUnchanged}>
            Show
          </Button>
        ) : null}
      </footer>
    </section>
  );
}
