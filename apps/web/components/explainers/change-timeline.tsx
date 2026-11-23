"use client";

import { FileText } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { formatDateTime, plural } from "@/lib/format";
import { transition } from "@/lib/transitions";
import type { ClaimStatus, NotCheckedReason } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DispositionStamp } from "@/components/dealproof/disposition-stamp";
import { StatusMark } from "@/components/dealproof/status-mark";
import { ChangeList } from "@/components/dealproof/change-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import type { TimelineEntry } from "./derive";

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

/**
 * "What changed and why". One joined view of the assessment history: each version is a
 * node with its one-line state; what arrived between two versions sits on the rail
 * between them; and under the newer version its changes are listed most decision-relevant
 * first: the disposition, the judgments, each claim that moved on evidence of its own,
 * then claims that share one cause as a single row that opens (`ChangeList`).
 *
 * The API does not say which claim change caused which judgment change, so no change is
 * drawn as the consequence of another.
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

                  {diff ? (
                    diff.changes.length === 0 ? (
                      <p className="text-ink-secondary">Nothing changed from v{diff.from_version}</p>
                    ) : (
                      <ChangeList
                        aria-label={`What changed in version ${meta.version}`}
                        changes={diff.changes}
                        highlight={highlight}
                        rowClassName="px-2 py-2"
                        className="border-y border-line"
                      />
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
