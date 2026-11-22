"use client";

import { motion } from "motion/react";
import Link from "next/link";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import { duration, ease } from "@/lib/transitions";
import type { ClaimStatus, Disposition } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PendingGlyph, StatusGlyph } from "@/components/dealproof/glyphs";
import { STATUS_INK } from "@/components/dealproof/status-mark";
import type { FindingsContext } from "@/components/run/run-view";
import { ArcSpinner } from "@/components/run/step-mark";
import { sourceClassLabel, sourceName } from "@/components/run/wording";
import { Panel, PanelHeader } from "@/components/ui/card";
import { CATEGORY_LABEL } from "./adapt";
import { claimLiveState, type ClaimLive } from "./claim-live-state";

const settle = { duration: duration.base, ease };

function isStatus(value: string | null | undefined): value is ClaimStatus {
  return value != null && value in CLAIM_STATUS_LABEL;
}

/** The mark at the left of a claim: open ring, spinner, then the status glyph, settling. */
export function ClaimMark({ live, status }: { live: ClaimLive | null; status: ClaimStatus }) {
  if (live?.phase === "queued" || live?.phase === "waiting_identity") {
    return <PendingGlyph className="text-ink-muted" />;
  }
  if (live && live.phase !== "settled") return <ArcSpinner className="text-ink" />;
  const shown = live && isStatus(live.status) ? live.status : status;
  return (
    <motion.span
      key={shown}
      initial={live?.fresh ? { opacity: 0, scale: 0.9 } : false}
      animate={{ opacity: 1, scale: 1 }}
      transition={settle}
      className={cn("inline-flex", STATUS_INK[shown])}
    >
      <StatusGlyph status={shown} />
    </motion.span>
  );
}

/** What a claim row says on its second line, from the run's own events. */
export function claimStateLine(live: ClaimLive): string {
  if (live.phase === "waiting_identity") return "Waiting for identity";
  if (live.phase === "queued") {
    return live.ahead === null ? "Queued" : live.ahead === 0 ? "Queued · next" : `Queued · ${live.ahead} ahead`;
  }
  const line = live.line ?? "Checking";
  return live.progress ? `${line} · ${live.progress.done} of ${live.progress.total}` : line;
}

function IdentityBand({ context, detail, basePath }: { context: FindingsContext; detail: CaseDetail; basePath: string }) {
  const finding = context.view.identity;
  const step = context.run.steps.find((s) => s.key.includes("identity"));
  if (!finding && !step) return null;
  const stage = finding?.stage;
  const candidates = finding?.counts.candidates;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-4 py-3 text-dense">
      <span className="font-medium text-ink">Identity</span>
      {stage === "confirmed" ? (
        <span className="text-ink">
          Confirmed · {finding?.items[0]?.name ?? detail.identity.entity_name ?? "the company"}
          {finding?.items[0]?.matched_keys?.length ? (
            <span className="text-ink-secondary"> · matched on {finding.items[0].matched_keys.join(" + ").replace(/_/g, " ")}</span>
          ) : null}
        </span>
      ) : stage === "ambiguous" || stage === "unresolved" ? (
        <>
          <span className="text-cannot-verify">
            {stage === "ambiguous" ? `${candidates ?? "Several"} companies match` : "No company matched"}
          </span>
          <span className="text-ink-secondary">The run stops here and the claims stay queued</span>
          <Link
            href={`${basePath}/identity`}
            className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Resolve identity
          </Link>
        </>
      ) : (
        <span className="text-ink-secondary">
          Confirming which company this is{candidates ? ` · ${plural(candidates, "candidate")}` : null}
        </span>
      )}
    </p>
  );
}

/**
 * The Verify findings: identity, then the claims flipping queued → checking → status with
 * the evidence line, then what else the run found. The claim text is already on the page
 * from the case; the stream carries only ids, categories, statuses and public evidence.
 * Rows keep their ledger order: nothing jumps when it settles.
 */
export function ClaimStream({
  context,
  detail,
  basePath,
}: {
  context: FindingsContext;
  detail: CaseDetail;
  basePath: string;
}) {
  const { view, run, terminal } = context;
  const rows = detail.claims
    .map((claim) => ({
      claim,
      live: claimLiveState(claim.id, {
        detail,
        run,
        runActive: !terminal,
        view,
        events: context.events,
        settledSeq: Number.MAX_SAFE_INTEGER,
      }),
      fresh: context.isNew(view.claims.get(claim.id)?.seq ?? 0),
    }))
    .filter((row) => row.live !== null || view.claims.has(row.claim.id));
  const count = (phase: string[]) => rows.filter((row) => row.live && phase.includes(row.live.phase)).length;
  const settled = count(["settled"]);
  const checking = count(["gathering", "reading", "deciding"]);
  const queued = count(["queued", "waiting_identity"]);
  const latestEvent = view.events.rows.at(-1);
  const assessment = view.assessment?.items[0];

  return (
    <Panel aria-label="Findings">
      <IdentityBand context={context} detail={detail} basePath={basePath} />
      <PanelHeader
        title="Claims"
        meta={rows.length > 0 ? `${settled} settled · ${checking} checking · ${queued} queued` : undefined}
        action={
          <Link
            href={`${basePath}/claims`}
            className="rounded-xs text-dense text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Open the ledger
          </Link>
        }
      />
      {rows.length === 0 ? (
        <p className="px-4 py-3 text-dense text-ink-muted">No claim has been queued yet</p>
      ) : (
        <ol className="flex flex-col">
          {rows.map(({ claim, live, fresh }) => {
            const done = live?.phase === "settled";
            const status = live && isStatus(live.status) ? live.status : claim.status;
            const notChecked = done && status === "not_checked";
            return (
              <li
                key={claim.id}
                className={cn(
                  "grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-x-3 border-b border-line px-4 py-2 text-dense last:border-b-0",
                  notChecked && "hatch",
                )}
              >
                <span className="mt-0.5">
                  <ClaimMark live={live ? { ...live, fresh } : null} status={claim.status} />
                </span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate text-ink">{claim.normalised_text}</span>
                  {live && !done ? <span className="text-xs text-ink-secondary">{claimStateLine(live)}</span> : null}
                  {done && live?.evidence?.source ? (
                    <motion.span
                      initial={fresh ? { opacity: 0 } : false}
                      animate={{ opacity: 1 }}
                      transition={{ ...settle, delay: duration.fast }}
                      className="text-xs text-ink-secondary"
                    >
                      {sourceName(live.evidence.source)} · {sourceClassLabel(live.evidence.source.source_class)} · as of{" "}
                      {formatDate(live.evidence.source.as_of) ?? "unknown date"}
                      {live.evidence.snippet ? <span className="text-ink"> · “{live.evidence.snippet}”</span> : null}
                    </motion.span>
                  ) : null}
                  {done && live?.evidence?.gap ? (
                    <span className="text-xs text-ink-muted">{live.evidence.gap}</span>
                  ) : null}
                </span>
                <span className={cn("text-right text-xs whitespace-nowrap", done ? cn("font-medium", STATUS_INK[status]) : "text-ink-muted")}>
                  {done ? CLAIM_STATUS_LABEL[status] : CATEGORY_LABEL[claim.category]}
                </span>
              </li>
            );
          })}
        </ol>
      )}
      <div className="flex flex-col gap-1 border-t border-line px-4 py-2 text-xs text-ink-secondary">
        <p>
          Events <span className="font-mono text-ink">{view.events.counts.events ?? view.events.rows.length}</span>
          <span className="text-ink-muted"> · </span>
          Comparables <span className="font-mono text-ink">{view.peers.counts.peers ?? view.peers.rows.length}</span>
          {latestEvent ? (
            <span>
              <span className="text-ink-muted"> · </span>Latest: {formatDate(latestEvent.date) ?? "no date"} ·{" "}
              {latestEvent.title ?? latestEvent.event_kind}
            </span>
          ) : null}
        </p>
        <p className={cn(!assessment && "hatch -mx-4 -mb-2 rounded-b-lg px-4 py-2 text-not-checked")}>
          {assessment?.disposition ? (
            <>
              Assessment{assessment.version ? ` v${assessment.version}` : null}:{" "}
              <span className="font-medium text-ink">
                {DISPOSITION_LABEL[assessment.disposition as Disposition] ?? assessment.disposition}
              </span>
            </>
          ) : (
            `Assessment pending · ${settled} of ${plural(rows.length, "claim")} settled`
          )}
        </p>
      </div>
    </Panel>
  );
}
