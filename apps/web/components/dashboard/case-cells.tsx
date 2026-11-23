import { BadgeCheck, CircleQuestionMark } from "lucide-react";
import {
  CostReadout,
  CriteriaStrip,
  DispositionStamp,
  StatusCounts,
} from "@/components/dealproof";
import { Icon } from "@/components/ui";
import type { CaseSummary } from "@/lib/api/client";
import { formatShare, plural } from "@/lib/format";
import { RUN_KIND_LABEL } from "@/lib/labels";
import type { FitResult } from "@/lib/types";
import { claimCounts, type CaseRecord } from "@/lib/workspace-state";

const VERDICT = { pass: "met", fail: "not_met", unknown: "unknown" } as const;

/** Identity state in words, with the glyph the case header uses for the same state. */
export function IdentityCue({ item, record }: { item: CaseSummary; record?: CaseRecord }) {
  if (item.identity_state === "confirmed") {
    return (
      <span className="inline-flex items-center gap-1 text-ink-secondary">
        <Icon icon={BadgeCheck} className="shrink-0" />
        Identity confirmed
      </span>
    );
  }
  const candidates = record?.identity_candidates ?? 0;
  return (
    <span className="inline-flex items-center gap-1 text-cannot-verify">
      <Icon icon={CircleQuestionMark} className="shrink-0" />
      Identity unresolved
      {candidates > 0 ? ` · ${plural(candidates, "candidate")}` : null}
    </span>
  );
}

/** What the case is doing or waiting for, stated in words. Null when there is nothing to say. */
export function waitingCue(item: CaseSummary, record?: CaseRecord): string | null {
  if (item.status === "verifying") {
    const run = record?.run;
    if (run && (run.state === "running" || run.state === "pending") && run.steps > 0) {
      const current = Math.min(run.steps_finished + 1, run.steps);
      return `${RUN_KIND_LABEL[run.kind]} running · step ${current} of ${run.steps}`;
    }
    return "Verify running";
  }
  if (item.status === "failed") return "Last run did not finish";
  if (record?.message?.status === "draft") return "Request awaiting approval";
  return null;
}

export function DispositionCell({ item }: { item: CaseSummary }) {
  if (!item.disposition) {
    return (
      <span className="text-ink-muted">
        <span aria-hidden>–</span>
        <span className="sr-only">No disposition yet</span>
      </span>
    );
  }
  return <DispositionStamp disposition={item.disposition} size="sm" />;
}

/**
 * Fit and its assessable share, never apart. With the case record loaded the strip shows
 * each criterion; before that, the two numbers from the list in the same words.
 */
export function FitCell({ item, record }: { item: CaseSummary; record?: CaseRecord }) {
  if (item.fit_state === "awaiting_strategy_criteria") {
    return <span className="text-ink-secondary">No criteria set for this case</span>;
  }
  if (item.fit_state === "identity_unresolved") {
    return <span className="text-ink-secondary">Waiting on identity</span>;
  }
  if (item.fit_state === null) {
    return (
      <span className="text-ink-muted">
        <span aria-hidden>–</span>
        <span className="sr-only">Not assessed yet</span>
      </span>
    );
  }

  const results = record?.opportunity.criterion_results ?? [];
  if (results.length > 0) {
    const fit: FitResult = {
      fit: item.fit_state === "scored" ? item.fit : null,
      assessable_share: (item.assessable_pct ?? 0) / 100,
      criteria: results.map((result) => ({
        id: result.criterion_id,
        label: result.label,
        kind: result.kind,
        weight: result.weight,
        verdict: VERDICT[result.state],
      })),
    };
    return <CriteriaStrip fit={fit} size="compact" />;
  }

  const share = formatShare((item.assessable_pct ?? 0) / 100);
  return (
    <span className="font-mono text-xs font-medium text-ink">
      {item.fit_state === "scored" && item.fit !== null ? `Fit ${Math.round(item.fit)}` : "Fit unavailable"}
      {" · "}
      {share} of criteria assessable
    </span>
  );
}

/** Counts by status once the case record is in; the plain total until then. */
export function ClaimsCell({ item, record }: { item: CaseSummary; record?: CaseRecord }) {
  if (item.claim_count === 0) return <span className="text-ink-muted">No claims yet</span>;
  const counts = claimCounts(record);
  if (!counts) {
    return (
      <span className="font-mono text-xs text-ink-secondary">{plural(item.claim_count, "claim")}</span>
    );
  }
  return <StatusCounts counts={counts} />;
}

export function CostCell({ item }: { item: CaseSummary }) {
  return (
    <CostReadout
      variant="compact"
      cost={{
        credits_used: item.cost.crustdata_credits,
        credit_budget: 0,
        model_usd: item.cost.llm_usd,
        lines: [],
      }}
    />
  );
}

/**
 * Fit and its assessable share on two short lines, for cards and tight table cells: the
 * words, then one bar whose hatched end is the share that could not be assessed.
 */
export function FitCompact({ item }: { item: CaseSummary }) {
  if (item.fit_state !== "scored" || item.fit === null) {
    return (
      <span className="text-xs text-ink-muted">
        {item.fit_state === "identity_unresolved"
          ? "Fit waits on identity"
          : item.fit_state === "awaiting_strategy_criteria"
            ? "No criteria set"
            : "Fit not scored"}
      </span>
    );
  }
  const pct = item.assessable_pct ?? 0;
  return (
    <span className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-xs font-medium whitespace-nowrap text-ink">
        Fit {Math.round(item.fit)} · {pct}% assessable
      </span>
      <span aria-hidden className="flex h-1.5 w-full max-w-40 gap-0.5">
        {pct > 0 ? <span className="h-full bg-ink" style={{ width: `${pct}%` }} /> : null}
        {pct < 100 ? (
          <span className="hatch-dense h-full flex-1 border border-dashed border-not-checked-line" />
        ) : null}
      </span>
    </span>
  );
}
