/**
 * What a requested document would do to the screening outcome, read off the DecisionFlip
 * analysis. Pure functions: nothing here re-derives an outcome, it only picks which of the
 * outcomes the rules already simulated belongs on a document's row.
 */
import type { RequestListOut } from "@/lib/api/client";
import type { Disposition } from "@/lib/types";
import type { DecisionFlip, FlipEffort, FlipItem } from "./decision-flip/types";

type RequestItem = RequestListOut["items"][number];

export interface Branch {
  to: Disposition;
  /** True when this branch only holds once the other decision blockers are settled too. */
  withOthers: boolean;
}

export type RequestEffect =
  /** The document can move the outcome and a bad answer leaves it where it is. */
  | { kind: "moves"; from: Disposition; to: Disposition; withOthers: boolean }
  /** Both answers matter, or the item is conditional: say each branch. */
  | { kind: "branches"; from: Disposition; holds: Branch; fails: Branch }
  /** Neither answer changes the outcome. */
  | { kind: "stays"; at: Disposition };

/** The analysis items a requested document settles, the most decision-relevant first. */
export function flipItemsFor(item: RequestItem, flip: DecisionFlip): FlipItem[] {
  const rank = (entry: FlipItem) => (entry.decision_blocker ? 0 : entry.disqualifier_risk ? 1 : 2);
  return flip.items
    .filter(
      (entry) =>
        (entry.claim_id != null && item.claim_ids.includes(entry.claim_id)) ||
        entry.settle_with.includes(item.document),
    )
    .sort((a, b) => rank(a) - rank(b));
}

/** The effect of one analysis item, as the rules simulated it. */
export function effectOf(lead: FlipItem, flip: DecisionFlip): RequestEffect {
  const from = flip.current;
  // A blocker that does not flip alone reaches the target only with the other blockers.
  const withOthers = lead.decision_blocker && !lead.flips_alone && flip.target != null;
  const holds: Branch = {
    to: withOthers && flip.target ? flip.target : (lead.if_supported?.disposition ?? from),
    withOthers,
  };
  const fails: Branch = { to: lead.if_contradicted?.disposition ?? from, withOthers: false };

  if (fails.to !== from || (lead.conditional_action && holds.to !== from)) {
    return { kind: "branches", from, holds, fails };
  }
  if (holds.to !== from) return { kind: "moves", from, to: holds.to, withOthers };
  return { kind: "stays", at: from };
}

export interface RequestRow {
  item: RequestItem;
  /** Null when the analysis has no item for this document. */
  effect: RequestEffect | null;
  /** The effort to obtain it; a tie-break only. */
  effort: FlipEffort | null;
  /** The both-branch sentence for criteria and financial items. */
  condition: string | null;
}

export function requestRow(item: RequestItem, flip: DecisionFlip | null): RequestRow {
  const lead = flip ? flipItemsFor(item, flip)[0] : undefined;
  if (!flip || !lead) return { item, effect: null, effort: null, condition: null };
  return {
    item,
    effect: effectOf(lead, flip),
    effort: lead.est_effort,
    condition: lead.conditional_action ?? null,
  };
}

export interface RequestSummary {
  total: number;
  /** Documents that can change the outcome. Null without an analysis. */
  critical: number | null;
  current: Disposition | null;
  /** The outcome with every open item supported. Null without an analysis. */
  ifAllClean: Disposition | null;
}

export function summarise(list: RequestListOut, flip: DecisionFlip | null): RequestSummary {
  const total = list.items.length;
  if (!flip) return { total, critical: null, current: null, ifAllClean: null };
  const clean = flip.ceiling ?? flip.minimum_evidence?.outcome ?? null;
  return {
    total,
    critical: list.items.filter((item) => item.group === "needed").length,
    current: flip.current,
    ifAllClean: clean?.disposition ?? null,
  };
}
