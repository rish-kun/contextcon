"use client";

import { FileText } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { formatDateTime, plural } from "@/lib/format";
import { transition } from "@/lib/transitions";
import type { AssessmentChange, ClaimStatus, NotCheckedReason } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DispositionStamp } from "@/components/dealproof/disposition-stamp";
import { Unsourced } from "@/components/dealproof/source-line";
import { StatusMark } from "@/components/dealproof/status-mark";
import {
  ChangeBecause,
  ChangeHeading,
  ChangeValues,
  isUnsourcedChange,
} from "@/components/dealproof/version-diff";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { splitChanges, type TimelineEntry } from "./derive";

export interface UnchangedClaim {
  number: number;
  text: string;
  status: ClaimStatus;
  not_checked_reason?: NotCheckedReason | null;
}

/** The rail cell of one row: its node, then the line running on to the next row. */
function Rail({ children, last = false }: { children: React.ReactNode; last?: boolean }) {
  return (
    <span className="flex flex-col items-center" aria-hidden>
      <span className="flex h-5 items-center">{children}</span>
      {last ? null : <span className="w-px flex-1 bg-line-strong" />}
    </span>
  );
}

/** The elbow that hangs a consequence under what caused it. */
function Elbow() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden focusable={false} className="shrink-0 text-ink-muted">
      <path d="M4 0v6a4 4 0 0 0 4 4h9" stroke="currentColor" strokeWidth="1" />
      <path d="m14 7 3.5 3-3.5 3" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Change({
  change,
  highlight,
  consequence = false,
}: {
  change: AssessmentChange;
  highlight: boolean;
  consequence?: boolean;
}) {
  // An unsourced status change shows neither status: the error in development, nothing
  // in production (the omission is logged by Unsourced).
  if (isUnsourcedChange(change) && change.kind === "claim_status") {
    return (
      <li className="py-2">
        <Unsourced what={`Claim ${change.claim_number} status change`} />
      </li>
    );
  }
  return (
    <li
      className={cn(
        "flex gap-1 rounded-sm py-2 pr-2",
        consequence ? "pl-0" : "pl-2",
        highlight && "animate-changed motion-reduce:animate-none",
      )}
    >
      {consequence ? <Elbow /> : null}
      <div className="flex min-w-0 flex-col gap-2">
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
      </div>
    </li>
  );
}

/**
 * "What changed and why". One joined view of the assessment history: each version is a
 * node with its one-line state; what arrived between two versions sits on the rail
 * between them; and under the newer version, each claim that moved is a root with the
 * figures that moved because of it hanging beneath.
 *
 * The API does not yet say which claim change caused which derived change, so derived
 * changes hang as one "As a result" group under the claim changes of that version, and
 * are never attached to a particular claim. With no claim change they are listed at the
 * version's root with their own cause.
 *
 * Static on a page visit. A version that arrives while the page is open fades in, and
 * `highlightVersion` gives its rows the one-time tint.
 */
export function ChangeTimeline({
  entries,
  current,
  viewing,
  onOpen,
  highlightVersion = null,
  unchangedFor,
  className,
}: {
  /** Oldest first. */
  entries: TimelineEntry[];
  current: number;
  /** The version open on the page, when it is not the current one. */
  viewing?: number;
  onOpen?: (version: number) => void;
  /** A version the reader has not seen before: its changed rows take the one-time highlight. */
  highlightVersion?: number | null;
  /** The claims a version left as they were, for "Show". */
  unchangedFor?: (version: number) => UnchangedClaim[];
  className?: string;
}) {
  const [shown, setShown] = useState<number[]>([]);
  const open = viewing ?? current;

  return (
    <ol
      aria-label="What changed and why"
      className={cn("flex flex-col rounded-lg border border-line bg-surface p-4 text-dense", className)}
    >
      {/* `initial={false}`: versions present when the page loads are simply there. */}
      <AnimatePresence initial={false}>
        {entries.map((entry, index) => {
          const { meta, state, cause, diff } = entry;
          const isCurrent = meta.version === current;
          const last = index === entries.length - 1;
          const highlight = highlightVersion === meta.version;
          const split = diff ? splitChanges(diff) : null;
          const unchanged = unchangedFor?.(meta.version) ?? [];
          const showing = shown.includes(meta.version);

          return (
            <motion.li
              key={meta.version}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={transition.base}
              className="flex flex-col"
            >
              {cause ? (
                <div className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3">
                  <Rail>
                    <span className="inline-flex size-5 items-center justify-center rounded-xs border border-line-strong bg-surface-raised text-ink-secondary">
                      <Icon icon={FileText} size={12} />
                    </span>
                  </Rail>
                  <div className="flex min-w-0 flex-col gap-0.5 pb-4">
                    <p className="flex flex-wrap items-baseline gap-x-2 text-ink">
                      {cause.label}
                      {cause.at ? (
                        <span className="font-mono text-xs text-ink-secondary">
                          {formatDateTime(cause.at)}
                        </span>
                      ) : null}
                    </p>
                    <p className="text-xs text-ink-secondary">
                      {[
                        cause.by ? `Uploaded by ${cause.by}` : null,
                        cause.changed_claims.length > 0
                          ? `Changed ${cause.changed_claims.length === 1 ? "claim" : "claims"} ${cause.changed_claims.join(", ")}`
                          : "No claim changed status",
                        cause.at ? null : "Arrival time not recorded",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                </div>
              ) : null}

              <div className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3">
                <Rail last={last}>
                  <span
                    className={cn(
                      "size-3 rounded-full border-2 border-ink",
                      isCurrent ? "bg-ink" : "bg-surface",
                    )}
                  />
                </Rail>
                <div className={cn("flex min-w-0 flex-col gap-3", last ? "pb-0" : "pb-6")}>
                  <div className="flex flex-col gap-1">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className={cn("font-mono text-xs text-ink", isCurrent && "font-medium")}>
                        v{meta.version}
                      </span>
                      <span className="font-mono text-xs text-ink-secondary">
                        {formatDateTime(meta.created_at)}
                      </span>
                      {cause ? null : <span className="text-ink-secondary">· {meta.trigger}</span>}
                      {isCurrent ? <Badge variant="mono">current</Badge> : null}
                      {meta.version === viewing && !isCurrent ? (
                        <Badge variant="accent" className="font-mono text-2xs">
                          reading
                        </Badge>
                      ) : onOpen && meta.version !== open ? (
                        <Button
                          variant="link"
                          size="inline"
                          className="text-xs font-normal"
                          onClick={() => onOpen(meta.version)}
                        >
                          Open version {meta.version}
                        </Button>
                      ) : null}
                    </p>
                    {state ? (
                      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-secondary">
                        <span>
                          {plural(state.claims, "claim")} · {state.settled} settled
                          {state.not_checked > 0 ? ` · ${state.not_checked} not checked` : null}
                        </span>
                        <DispositionStamp disposition={state.disposition} className="h-6 px-2 text-xs" />
                      </p>
                    ) : null}
                  </div>

                  {diff && split ? (
                    diff.changes.length === 0 ? (
                      <p className="text-ink-secondary">Nothing changed from v{diff.from_version}</p>
                    ) : (
                      <ul
                        aria-label={`What changed in version ${meta.version}`}
                        className="flex flex-col divide-y divide-line border-y border-line"
                      >
                        {split.claimChanges.map((change, i) => (
                          <Change key={`claim-${i}`} change={change} highlight={highlight} />
                        ))}
                        {split.derived.length > 0 ? (
                          split.claimChanges.length > 0 ? (
                            <li className="flex flex-col py-2 pl-2">
                              <p className="text-xs text-ink-muted">As a result</p>
                              <ul className="flex flex-col">
                                {split.derived.map((change, i) => (
                                  <Change key={`derived-${i}`} change={change} highlight={highlight} consequence />
                                ))}
                              </ul>
                            </li>
                          ) : (
                            split.derived.map((change, i) => (
                              <Change key={`derived-${i}`} change={change} highlight={highlight} />
                            ))
                          )
                        ) : null}
                      </ul>
                    )
                  ) : null}

                  {diff ? (
                    <div className="flex flex-col gap-2">
                      <p className="flex flex-wrap items-center gap-3 text-xs text-ink-secondary">
                        <span>{plural(diff.unchanged_claims, "claim")} unchanged</span>
                        {unchanged.length > 0 ? (
                          <Button
                            variant="link"
                            size="inline"
                            className="text-xs font-normal"
                            aria-expanded={showing}
                            onClick={() =>
                              setShown((list) =>
                                showing ? list.filter((v) => v !== meta.version) : [...list, meta.version],
                              )
                            }
                          >
                            {showing ? "Hide" : "Show"}
                          </Button>
                        ) : null}
                      </p>
                      {showing ? (
                        <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
                          {unchanged.map((claim) => (
                            <li
                              key={claim.number}
                              className="grid grid-cols-[4rem_minmax(0,1fr)_auto] items-center gap-x-3 px-3 py-2"
                            >
                              <span className="font-mono text-xs text-ink-muted">Claim {claim.number}</span>
                              <span className="truncate text-ink">“{claim.text}”</span>
                              <StatusMark status={claim.status} reason={claim.not_checked_reason} />
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}

                  {entries.length === 1 ? (
                    <p className="text-ink-secondary">
                      No later versions. New evidence will be recorded here
                    </p>
                  ) : null}
                </div>
              </div>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ol>
  );
}
