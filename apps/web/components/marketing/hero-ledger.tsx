"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { CLAIM_STATUS_LABEL } from "@/lib/labels";
import { duration, rise, staggerDelay, transition } from "@/lib/transitions";
import type { ClaimStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ILLUSTRATION_COMPANY,
  ILLUSTRATION_LABEL,
  LEDGER_ROWS,
  LEDGER_SUMMARY,
  type LedgerRow,
} from "./content";
import {
  DispositionStamp,
  DocChip,
  Estimate,
  IllustrationLabel,
  SourceChip,
  StatusCount,
  StatusGlyph,
  StatusTag,
  statusInk,
} from "./primitives";

/** Rows enter first; then the marks settle one by one, 200ms apart. */
const SETTLE_START_MS = 520;
const SETTLE_GAP_MS = duration.base * 1000;

/**
 * The claim ledger from the PRD's Pune example: what the seller said, the status on
 * the spine, what the record shows. Always labelled as an illustration.
 */
export function HeroLedger() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.15 });
  const reduce = useReducedMotion();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!inView || reduce) return;
    let n = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      n += 1;
      setCount(n);
      if (n < LEDGER_ROWS.length) timer = setTimeout(tick, SETTLE_GAP_MS);
    };
    timer = setTimeout(tick, SETTLE_START_MS);
    return () => clearTimeout(timer);
  }, [inView, reduce]);

  // Reduced motion: the ledger is drawn in its final state.
  const settled = reduce ? LEDGER_ROWS.length : count;
  const done = settled >= LEDGER_ROWS.length;

  return (
    <div
      ref={ref}
      className="overflow-hidden rounded-xl border border-line bg-surface text-left shadow-lg"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-4 py-3 lg:px-6">
        <p className="text-sm font-medium text-ink">
          {ILLUSTRATION_COMPANY}
          <span className="font-normal text-ink-muted"> · Claims</span>
        </p>
        <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
      </div>

      <div
        aria-hidden
        className="hidden grid-cols-[minmax(0,5fr)_var(--layout-spine)_minmax(0,7fr)] border-b border-line bg-surface-sunken text-xs text-ink-muted lg:grid"
      >
        <span className="px-6 py-2">Seller said</span>
        <span className="py-2 text-center">Status</span>
        <span className="px-6 py-2">The record shows</span>
      </div>

      <ol>
        {LEDGER_ROWS.map((row, i) => (
          <motion.li
            key={row.n}
            data-reveal
            initial={{ opacity: 0, y: rise }}
            animate={inView || reduce ? { opacity: 1, y: 0 } : undefined}
            transition={{ ...transition.slow, delay: staggerDelay(i) }}
            className="grid border-b border-line lg:grid-cols-[minmax(0,5fr)_var(--layout-spine)_minmax(0,7fr)]"
          >
            <ClaimSide row={row} />
            <div className="pr-4 pb-3 pl-11 lg:hidden">
              <Settle on={i < settled}>
                <StatusTag status={row.status} />
              </Settle>
            </div>
            <div className="hidden border-x border-line bg-paper px-2 py-4 lg:block">
              <Settle on={i < settled} className="flex justify-center">
                <SpineMark status={row.status} />
              </Settle>
            </div>
            <RecordSide row={row} />
          </motion.li>
        ))}
      </ol>

      <motion.div
        data-reveal
        initial={{ opacity: 0 }}
        animate={{ opacity: done ? 1 : 0 }}
        transition={transition.slow}
        className="flex flex-col gap-4 bg-paper px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-6"
      >
        <div className="flex flex-col gap-2">
          <p className="text-sm text-ink">{LEDGER_SUMMARY.line}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {LEDGER_SUMMARY.counts.map((c) => (
              <StatusCount key={c.status} status={c.status} count={c.count} />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 lg:items-end">
          <DispositionStamp
            disposition={LEDGER_SUMMARY.disposition}
            className="self-start lg:self-auto"
          />
          <p className="text-dense text-ink-secondary">{LEDGER_SUMMARY.next}</p>
        </div>
      </motion.div>
    </div>
  );
}

function ClaimSide({ row }: { row: LedgerRow }) {
  return (
    <div className="flex gap-3 px-4 pt-4 pb-3 lg:px-6 lg:py-4">
      <span className="w-4 shrink-0 font-mono text-xs leading-5 text-ink-muted">
        {row.n}
      </span>
      <div className="min-w-0">
        <p className="text-dense text-ink lg:text-sm">
          <span className="lg:hidden">Seller said: </span>
          &ldquo;{row.claim}&rdquo;
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          {row.category}
          <DocChip label={row.page} />
        </p>
      </div>
    </div>
  );
}

function RecordSide({ row }: { row: LedgerRow }) {
  return (
    <div className="min-w-0 px-4 pb-4 pl-11 lg:px-6 lg:py-4">
      <p className="text-dense text-ink lg:text-sm">
        {row.estimate ? (
          <>
            <Estimate {...row.estimate} />
            <span className="text-ink-muted"> · </span>
          </>
        ) : null}
        {row.record}
      </p>
      <p className="mt-2 flex flex-wrap gap-2">
        {row.sources.map((s) => (
          <SourceChip key={s.label} {...s} />
        ))}
      </p>
      {row.notes || row.settle ? (
        <dl className="mt-3 grid gap-1 text-dense">
          {row.notes?.map((note) => (
            <div key={note.label} className="flex flex-wrap gap-x-2">
              <dt className="text-ink-muted">{note.label}</dt>
              <dd className="text-ink-secondary">{note.text}</dd>
            </div>
          ))}
          {row.settle ? (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-ink-muted">What would settle it</dt>
              <dd className="font-medium text-ink">{row.settle}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </div>
  );
}

function SpineMark({ status }: { status: ClaimStatus }) {
  return (
    <span
      className={cn(
        "flex flex-col items-center gap-1 text-center text-2xs font-medium",
        statusInk(status),
      )}
    >
      <StatusGlyph status={status} />
      {CLAIM_STATUS_LABEL[status]}
    </span>
  );
}

/** A pending ring that gives way to the status mark when the rule fires. */
function Settle({
  on,
  className,
  children,
}: {
  on: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span className={cn("relative block", className)}>
      <motion.span
        aria-hidden
        data-pending
        initial={false}
        animate={{ opacity: on ? 0 : 1 }}
        transition={transition.base}
        className="pointer-events-none absolute top-1 left-0 flex w-full justify-start lg:top-0 lg:justify-center"
      >
        <span className="size-4 rounded-full border-[1.5px] border-line-strong" />
      </motion.span>
      <motion.span
        data-reveal
        initial={false}
        animate={{ opacity: on ? 1 : 0, scale: on ? 1 : 0.9 }}
        transition={transition.base}
        className="inline-block origin-center"
      >
        {children}
      </motion.span>
    </span>
  );
}
