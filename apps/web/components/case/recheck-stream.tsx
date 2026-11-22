"use client";

import { ArrowRight } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import type { CaseDetail } from "@/lib/api/client";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import { duration, ease } from "@/lib/transitions";
import type { ClaimStatus, Disposition } from "@/lib/types";
import { cn } from "@/lib/utils";
import { STATUS_INK } from "@/components/dealproof/status-mark";
import type { FindingsContext } from "@/components/run/run-view";
import { claimStepId } from "@/components/run/wording";
import { Icon } from "@/components/ui/icon";
import { CATEGORY_LABEL } from "./adapt";
import { claimLiveState } from "./claim-live-state";
import { ClaimMark, claimStateLine } from "./claim-stream";

function statusWord(value: string | null | undefined): string {
  return value && value in CLAIM_STATUS_LABEL ? CLAIM_STATUS_LABEL[value as ClaimStatus] : "No earlier result";
}

/**
 * A recheck, as before → after rows. Before is the previous status; after is queued,
 * checking, then the settled status. A status that did not change says "unchanged",
 * which is a result. When the assessment is written the same rows become "what changed":
 * they keep their place and the changed ones take the one-time tint.
 */
export function RecheckStream({
  context,
  detail,
  basePath,
}: {
  context: FindingsContext;
  detail: CaseDetail;
  basePath: string;
}) {
  const { view, run, terminal } = context;
  const touched = new Set<string>([
    ...run.steps.map((step) => claimStepId(step.key)).filter((id): id is string => id !== null),
    ...view.claims.keys(),
  ]);
  const rows = detail.claims.filter((claim) => touched.has(claim.id));
  const untouched = detail.claims.length - rows.length;
  const assessment = view.assessment?.items[0];
  const written = Boolean(assessment?.disposition);

  // An Evaluate run only re-applies rules: the header and the step line say all there is.
  if (rows.length === 0 && !assessment) return null;

  return (
    <div className="flex flex-col">
      <p className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-2 text-dense">
        <span className="font-medium text-ink">
          {written && assessment?.version ? `Version ${assessment.version} · what changed` : "What is being rechecked"}
        </span>
        <span className="font-mono text-xs text-ink-muted">
          {rows.length} {rows.length === 1 ? "claim" : "claims"}
          {untouched > 0 ? ` · ${untouched} unchanged and not re-run` : null}
        </span>
      </p>
      <ol className="flex flex-col border-t border-line">
        {rows.map((claim) => {
          const act = view.claims.get(claim.id);
          const live = claimLiveState(claim.id, {
            detail,
            run,
            runActive: !terminal,
            view,
            events: context.events,
            settledSeq: Number.MAX_SAFE_INTEGER,
          });
          const fresh = context.isNew(act?.seq ?? 0);
          const before = act?.previousStatus ?? claim.history.at(-2)?.status ?? null;
          const done = live?.phase === "settled" || (live === null && (terminal || act?.stage === "settled"));
          const after = (live?.status ?? act?.status ?? claim.status) as ClaimStatus;
          const changed = done && before !== null && before !== after;
          const evidence = live?.evidence?.source ?? act?.source ?? null;
          return (
            <motion.li
              key={claim.id}
              initial={changed && fresh ? { backgroundColor: "var(--color-accent-tint)" } : false}
              animate={{ backgroundColor: "rgba(0,0,0,0)" }}
              transition={{ duration: duration.highlight, ease }}
              className="grid grid-cols-1 items-baseline gap-x-4 gap-y-1 border-b border-line px-4 py-2 text-dense md:grid-cols-[10rem_minmax(0,1fr)_minmax(0,1fr)]"
            >
              <span className="text-ink">{CATEGORY_LABEL[claim.category]}</span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-ink-secondary">{statusWord(before)}</span>
                <Icon icon={ArrowRight} size={14} className="text-ink-muted" label="to" />
                {done ? (
                  <span className={cn("inline-flex items-center gap-1 font-medium", changed ? STATUS_INK[after] : "text-ink-muted")}>
                    <ClaimMark live={live ? { ...live, fresh } : null} status={after} />
                    {changed ? CLAIM_STATUS_LABEL[after] : "unchanged"}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-ink-secondary">
                    <ClaimMark live={live} status={claim.status} />
                    {live ? claimStateLine(live) : "Queued"}
                  </span>
                )}
              </span>
              <span className="min-w-0 truncate text-xs text-ink-secondary">
                {done && evidence ? (evidence.title ?? "Seller document") : null}
              </span>
            </motion.li>
          );
        })}
        <li className="grid grid-cols-1 items-baseline gap-x-4 gap-y-1 px-4 py-2 text-dense md:grid-cols-[10rem_minmax(0,1fr)_minmax(0,1fr)]">
          <span className="text-ink">Assessment{assessment?.version ? ` v${assessment.version}` : null}</span>
          <span className="flex flex-wrap items-center gap-x-2">
            {assessment?.previous_disposition ? (
              <>
                <span className="text-ink-secondary">
                  {DISPOSITION_LABEL[assessment.previous_disposition as Disposition]}
                </span>
                <Icon icon={ArrowRight} size={14} className="text-ink-muted" label="to" />
              </>
            ) : null}
            {written ? (
              <span className="font-medium text-ink">
                {assessment?.disposition === assessment?.previous_disposition
                  ? "unchanged"
                  : DISPOSITION_LABEL[assessment?.disposition as Disposition]}
              </span>
            ) : (
              <span className="text-ink-muted">pending</span>
            )}
          </span>
          <span className="text-xs">
            {written ? (
              <Link
                href={`${basePath}/assessment`}
                className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
              >
                Open the assessment
              </Link>
            ) : null}
          </span>
        </li>
      </ol>
    </div>
  );
}
