"use client";

import { CirclePause } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { Fragment } from "react";
import { formatDate, plural } from "@/lib/format";
import type { SourceRow } from "@/lib/run/activity-store";
import { duration, ease } from "@/lib/transitions";
import type { ClaimStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ClaimLedgerRow,
  type ClaimLedgerRowProps,
} from "@/components/dealproof/claim-ledger";
import { PendingGlyph } from "@/components/dealproof/glyphs";
import { Favicon } from "@/components/run/favicon";
import { ArcSpinner } from "@/components/run/step-mark";
import { failedReadText, sourceClassLabel, sourceName } from "@/components/run/wording";
import { Icon } from "@/components/ui/icon";
import { useCase } from "./case-context";
import type { ClaimLive, ClaimPhase } from "./claim-live-state";

const fade = { duration: duration.base, ease };

/** The words under the glyph on the ledger spine while a claim has no status yet. */
function Spine({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 lg:flex-col">
      {children}
      <span className="text-xs">{label}</span>
    </span>
  );
}

const DETAILED: { phase: ClaimPhase; label: string }[] = [
  { phase: "queued", label: "Queued" },
  { phase: "gathering", label: "Gathering" },
  { phase: "reading", label: "Reading" },
  { phase: "deciding", label: "Deciding" },
  { phase: "settled", label: "Settled" },
];
// With only the step to go on, what happens between "started" and "settled" is not known.
const PLAIN: { phase: ClaimPhase; label: string }[] = [
  { phase: "queued", label: "Queued" },
  { phase: "gathering", label: "Checking" },
  { phase: "settled", label: "Settled" },
];

/** queued → gathering → reading → deciding → settled, with the current one named. */
function PhaseSteps({ live }: { live: ClaimLive }) {
  const steps = live.detailed ? DETAILED : PLAIN;
  const phase = !live.detailed && (live.phase === "reading" || live.phase === "deciding") ? "gathering" : live.phase;
  const at = steps.findIndex((step) => step.phase === phase);
  return (
    <ol aria-label="Where this check is" className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {steps.map((step, index) => {
        const done = index < at;
        const current = index === at;
        return (
          <Fragment key={step.phase}>
            {index > 0 ? (
              <li aria-hidden className={cn("h-px w-4", done || current ? "bg-ink" : "bg-line-strong")} />
            ) : null}
            <li
              aria-current={current ? "step" : undefined}
              className={cn(
                "inline-flex items-center gap-1 text-2xs transition-colors duration-(--duration-base)",
                current ? "font-medium text-ink" : done ? "text-ink-secondary" : "text-ink-muted",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "size-1.5 rounded-full border transition-colors duration-(--duration-base)",
                  done || current ? "border-ink bg-ink" : "border-line-strong bg-surface",
                )}
              />
              {step.label}
              {done ? <span className="sr-only">, done</span> : null}
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}

/** One page or record read for this claim: favicon, domain, the date of what it states. */
function SourceChip({ row, claimId, enter }: { row: SourceRow; claimId: string; enter: boolean }) {
  const { source } = row;
  const failed = source.state !== "read";
  const body = (
    <>
      <Favicon domain={source.domain} sourceClass={source.source_class} muted={failed} />
      <span className={failed ? "text-ink-muted" : "text-ink"}>{sourceName(source)}</span>
      <span className="text-ink-muted">
        {failed ? failedReadText(source) : `as of ${formatDate(source.as_of) ?? "no date"}`}
      </span>
    </>
  );
  const shape =
    "inline-flex max-w-full items-center gap-1 rounded-md border border-line bg-surface px-2 py-0.5 text-xs whitespace-nowrap";
  return (
    <motion.li
      layoutId={`claim-source-${claimId}-${row.seq}`}
      initial={enter ? { opacity: 0, y: 4 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.slow, ease }}
      title={source.title ? `${source.title} · ${sourceClassLabel(source.source_class)}` : sourceClassLabel(source.source_class)}
    >
      {source.url && !failed ? (
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer noopener"
          className={cn(shape, "transition-colors hover:bg-surface-raised")}
        >
          {body}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : (
        <span className={shape}>{body}</span>
      )}
    </motion.li>
  );
}

function Sources({ live, claimId, settledSeq, label }: { live: ClaimLive; claimId: string; settledSeq: number; label: string }) {
  if (live.sources.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-2xs text-ink-muted">{label}</p>
      <ul className="flex flex-wrap gap-1">
        {live.sources.map((row) => (
          <SourceChip key={row.seq} row={row} claimId={claimId} enter={row.seq > settledSeq} />
        ))}
      </ul>
    </div>
  );
}

function factsLine(live: ClaimLive): string | null {
  if (live.factCount === 0 && live.rejected === 0) return null;
  const parts = [`${plural(live.factCount, "fact")} extracted`];
  if (live.rejected > 0) parts.push(`${live.rejected} discarded: no matching passage`);
  return parts.join(" · ");
}

/** What the check is doing for this claim, and what it has read and found so far. */
function ClaimFeed({ live, claimId, settledSeq }: { live: ClaimLive; claimId: string; settledSeq: number }) {
  const line = live.line ?? "Checking this claim";
  const count = factsLine(live);
  return (
    <div className="flex flex-col gap-2">
      <p className="relative flex min-h-5 items-baseline gap-2 text-ink">
        <span className="relative min-w-0 flex-1">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={line}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -4 }}
              transition={fade}
              className="block"
            >
              {line}
            </motion.span>
          </AnimatePresence>
        </span>
        {live.progress ? (
          <span className="shrink-0 font-mono text-xs text-ink-muted">
            {live.progress.done} of {live.progress.total}
          </span>
        ) : null}
      </p>
      <PhaseSteps live={live} />
      {live.detailed ? (
        live.sources.length > 0 ? (
          <Sources live={live} claimId={claimId} settledSeq={settledSeq} label="Read so far" />
        ) : (
          <p className="text-xs text-ink-muted">No pages read yet</p>
        )
      ) : null}
      {live.facts.length > 0 ? (
        <div className="flex flex-col gap-1">
          <p className="text-2xs text-ink-muted">Found so far</p>
          <ul className="flex flex-col gap-0.5">
            {live.facts.map((fact) => (
              <motion.li
                key={fact.key}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={fade}
                className="flex items-baseline gap-2 text-xs text-ink-secondary"
              >
                <span className="shrink-0 font-mono text-2xs text-ink-muted">
                  {formatDate(fact.asOf) ?? "no date"}
                </span>
                <span className="min-w-0 truncate">{fact.text}</span>
              </motion.li>
            ))}
          </ul>
        </div>
      ) : null}
      {count ? <p className="font-mono text-2xs text-ink-muted">{count}</p> : null}
    </div>
  );
}

/**
 * Shown from the moment the rule fires until the reloaded case brings the full evidence:
 * the status is already on the spine, and this is the proof, arriving 140 ms after it.
 */
function SettledPreview({ live }: { live: ClaimLive }) {
  const evidence = live.evidence;
  return (
    <motion.div
      initial={live.fresh ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      transition={{ ...fade, delay: duration.fast }}
      className="flex flex-col gap-1"
    >
      {evidence?.source ? (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-secondary">
          <Favicon domain={evidence.source.domain} sourceClass={evidence.source.source_class} />
          <span className="text-ink">{evidence.source.title ?? sourceName(evidence.source)}</span>
          <span className="font-mono text-2xs text-ink-muted">
            {sourceClassLabel(evidence.source.source_class)} · as of {formatDate(evidence.source.as_of) ?? "unknown date"}
          </span>
        </p>
      ) : null}
      {evidence?.snippet ? <p className="text-ink">“{evidence.snippet}”</p> : null}
      {evidence?.gap ? <p className="text-ink-secondary">{evidence.gap}</p> : null}
      {!evidence?.source && !evidence?.snippet && !evidence?.gap ? (
        <p className="text-ink-secondary">Loading the evidence for this result</p>
      ) : null}
    </motion.div>
  );
}

const CLAIM_STATUS_SET = new Set<string>([
  "supported",
  "partially_corroborated",
  "conflicting_evidence",
  "contradicted",
  "cannot_verify",
  "not_checked",
]);

/**
 * A ledger row that follows the run. While a check is waiting, queued or running, the
 * row shows exactly that, from the run's own steps and events: what is being done, what
 * has been read, what has been found. When the rule fires the spine takes the status and
 * the evidence follows; the row keeps its place and nothing is swapped out.
 */
export function LiveClaimRow(props: ClaimLedgerRowProps) {
  const { claimLive, feed, basePath, runActive } = useCase();
  const claimId = props.claim.id;
  const live = claimLive(claimId);
  if (!live) return <ClaimLedgerRow {...props} />;
  const settledSeq = feed.settled.sources;

  if (live.phase === "settled") {
    const status =
      live.status && CLAIM_STATUS_SET.has(live.status) ? (live.status as ClaimStatus) : props.claim.status;
    // Until the reloaded case agrees with the event, the event's own evidence line is shown.
    // Once the run has ended the stored case is the record, and the row shows that.
    const stale = runActive && props.claim.status !== status;
    return (
      <ClaimLedgerRow
        {...props}
        claim={stale ? { ...props.claim, status, not_checked_reason: null } : props.claim}
        live={{
          body: stale ? <SettledPreview live={live} /> : undefined,
          trail:
            live.sources.length > 0 ? (
              <div className="mt-3 border-t border-line pt-2">
                <Sources live={live} claimId={claimId} settledSeq={settledSeq} label="Read during this check" />
              </div>
            ) : undefined,
        }}
      />
    );
  }

  if (live.phase === "waiting_identity") {
    return (
      <ClaimLedgerRow
        {...props}
        live={{
          spine: (
            <Spine label="Waiting">
              <Icon icon={CirclePause} />
            </Spine>
          ),
          body: (
            <div className="flex flex-col gap-1">
              <p className="font-medium text-ink">Waiting for identity</p>
              <p className="text-ink-secondary">
                {live.identityRunning
                  ? (live.line ?? "The run is confirming which company this is")
                  : "This check is paused until the legal entity is confirmed"}
                {live.identityRunning ? null : (
                  <>
                    {" · "}
                    <Link
                      href={`${basePath}/identity`}
                      className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
                    >
                      Resolve identity
                    </Link>
                  </>
                )}
              </p>
            </div>
          ),
        }}
      />
    );
  }

  if (live.phase === "queued") {
    return (
      <ClaimLedgerRow
        {...props}
        live={{
          spine: (
            <Spine label="Queued">
              <PendingGlyph />
            </Spine>
          ),
          body: (
            <div className="flex flex-col gap-2">
              <p className="text-ink-secondary">
                Queued
                {live.ahead === null
                  ? " · its check has not started"
                  : live.ahead === 0
                    ? " · next to be checked"
                    : ` · ${live.ahead} ahead`}
              </p>
              <PhaseSteps live={live} />
            </div>
          ),
        }}
      />
    );
  }

  return (
    <ClaimLedgerRow
      {...props}
      live={{
        spine: (
          <Spine label="Checking">
            <ArcSpinner className="text-ink" />
          </Spine>
        ),
        body: <ClaimFeed live={live} claimId={claimId} settledSeq={settledSeq} />,
      }}
    />
  );
}
