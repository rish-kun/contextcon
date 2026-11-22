"use client";

import { useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { ClaimLedgerRow } from "@/components/dealproof";
import { duration } from "@/lib/transitions";
import {
  HERO_CLAIMS,
  ILLUSTRATION_COMPANY,
  ILLUSTRATION_LABEL,
} from "./content";
import { IllustrationLabel } from "./primitives";

/** Rows enter first; then the marks settle one by one, 200ms apart. */
const SETTLE_START_MS = 600;
const SETTLE_GAP_MS = duration.base * 1000;

/**
 * The hero's product window: the first claims of the PRD's Pune example in the real
 * ledger rows. Each row starts as a running check and settles in order, once.
 * Always labelled as an illustration. Under reduced motion it is drawn settled.
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
      if (n < HERO_CLAIMS.length) timer = setTimeout(tick, SETTLE_GAP_MS);
    };
    timer = setTimeout(tick, SETTLE_START_MS);
    return () => clearTimeout(timer);
  }, [inView, reduce]);

  const settled = reduce ? HERO_CLAIMS.length : count;

  return (
    <div
      ref={ref}
      className="overflow-hidden rounded-xl border border-line bg-surface text-left shadow-lg"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-4 py-3">
        <p className="text-sm font-medium text-ink">
          {ILLUSTRATION_COMPANY}
          <span className="font-normal text-ink-muted"> · Claims</span>
        </p>
        <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
      </div>
      <div
        role="grid"
        aria-label={`Claim ledger for ${ILLUSTRATION_COMPANY}, an illustration`}
        className="[&>[data-ledger-row]:last-child]:border-b-0"
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
        {HERO_CLAIMS.map((claim, i) => (
          <ClaimLedgerRow
            key={claim.id}
            claim={claim}
            index={i}
            pending={i >= settled}
            defaultExpanded={claim.status === "cannot_verify"}
          />
        ))}
      </div>
    </div>
  );
}
