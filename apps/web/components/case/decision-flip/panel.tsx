"use client";

import { ChevronDown, FileCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { DISPOSITION_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { DispositionStamp } from "@/components/dealproof/disposition-stamp";
import { StatusMark } from "@/components/dealproof/status-mark";
import { EmptyState, Icon, TextLink } from "@/components/ui";
import { TabSection } from "../parts";
import {
  blockerLine,
  isClaimStatus,
  nameItem,
  outcomeWords,
  readDecisionFlip,
  requestPriority,
  stateLabel,
  stateLine,
} from "./adapt";
import { ClassChips, HypotheticalCard } from "./hypothetical-card";
import type { DecisionFlip, FlipItem } from "./types";

const EFFORT_LABEL = { low: "Low effort", medium: "Medium effort", high: "High effort" } as const;

const short = (hash: string) => (hash.length > 10 ? `${hash.slice(0, 4)}…${hash.slice(-2)}` : hash);

/**
 * The link from the analysis to the request it prioritised. It is shown only when a
 * request list exists for this version and carries at least one blocker document, and
 * its words follow the request's state. DecisionFlip never approves and never sends.
 */
export function RequestLink({
  flip,
  detail,
  basePath,
  className,
}: {
  flip: DecisionFlip;
  detail: CaseDetail;
  basePath: string;
  className?: string;
}) {
  const list = detail.request_list;
  const blockers =
    flip.request?.blocker_items ??
    (list && list.assessment_version === flip.assessment_version
      ? list.items.filter((item) => requestPriority(item) === "blocker").length
      : 0);
  if (!list || blockers === 0) return null;

  const status = detail.message?.status;
  const sentAt = detail.message?.send?.completed_at ?? detail.message?.send?.dispatched_at ?? null;
  const label =
    status === "sent"
      ? `Evidence request sent${sentAt ? ` ${formatDate(sentAt)}` : ""}`
      : status === "approved" || status === "sending"
        ? "Evidence request approved"
        : "Evidence request prepared for approval";
  return (
    <Link
      href={`${basePath}/request`}
      className={cn(
        "inline-flex min-h-11 items-center gap-2 rounded-md border border-line-strong bg-surface px-3 text-dense font-medium text-ink transition-colors hover:bg-surface-raised md:min-h-8",
        className,
      )}
    >
      <Icon icon={FileCheck} className="shrink-0 text-ink-muted" />
      {label}
    </Link>
  );
}

function ItemRow({
  item,
  flip,
  detail,
  basePath,
}: {
  item: FlipItem;
  flip: DecisionFlip;
  detail: CaseDetail;
  basePath: string;
}) {
  const [open, setOpen] = useState(false);
  const named = nameItem(item, detail);
  const role = item.decision_blocker || item.disqualifier_risk;
  const target = flip.target ? DISPOSITION_LABEL[flip.target] : null;

  return (
    <li className="flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-11 w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 text-left transition-colors hover:bg-surface-raised"
      >
        <span className="flex min-w-0 flex-1 basis-56 flex-col">
          <span className="text-dense font-medium text-ink">{named.label}</span>
          {named.text ? <span className="truncate text-dense text-ink-secondary">{named.text}</span> : null}
        </span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {isClaimStatus(item.current_state) ? (
            <StatusMark status={item.current_state} />
          ) : (
            <span className="text-dense text-ink-secondary">{stateLabel(item)}</span>
          )}
          <ClassChips blocker={item.decision_blocker} risk={item.disqualifier_risk} />
          <span className="font-mono text-xs text-ink-muted">{EFFORT_LABEL[item.est_effort]}</span>
        </span>
        <Icon
          icon={ChevronDown}
          className={cn("ml-auto shrink-0 text-ink-muted transition-transform", open && "rotate-180")}
        />
      </button>

      {role && (item.settle_with.length > 0 || item.conditional_action) ? (
        <div className="flex flex-col gap-1 px-4 pb-2 text-dense">
          {item.settle_with.length > 0 ? (
            <p className="text-ink">
              <span className="text-ink-muted">Settled by </span>
              {item.settle_with.join(", ")}
              {item.seller_resolvable ? null : <span className="text-ink-muted"> · for you, not the seller</span>}
            </p>
          ) : item.analyst_retry ? (
            <p className="text-ink-secondary">Re-run the check. No seller document is needed</p>
          ) : null}
          {item.conditional_action ? <p className="text-ink-secondary">{item.conditional_action}</p> : null}
        </div>
      ) : null}

      {open ? (
        <div className="flex flex-col gap-3 border-t border-line bg-surface-raised px-4 py-3">
          {!role && item.settle_with.length > 0 ? (
            <p className="text-dense text-ink">
              <span className="text-ink-muted">Settled by </span>
              {item.settle_with.join(", ")}
            </p>
          ) : null}
          {!role && item.conditional_action ? (
            <p className="text-dense text-ink-secondary">{item.conditional_action}</p>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            {item.if_supported ? (
              <HypotheticalCard
                condition={item.flips_alone ? "If supported" : "If supported, on its own"}
                outcome={outcomeWords(item.if_supported, flip.current)}
              >
                {item.decision_blocker && !item.flips_alone && target ? (
                  <p>With the other blockers supported, would be {target}</p>
                ) : null}
              </HypotheticalCard>
            ) : null}
            {item.if_contradicted ? (
              <HypotheticalCard
                condition="If contradicted"
                outcome={outcomeWords(item.if_contradicted, flip.current)}
              >
                {item.locks_target && target && item.if_contradicted.disposition === flip.current ? (
                  <p>{target} is out of reach while this stands</p>
                ) : null}
              </HypotheticalCard>
            ) : null}
          </div>
          {item.claim_id ? (
            <p className="text-dense">
              <TextLink href={`${basePath}/claims`}>
                {named.claimNumber ? `Open claim ${named.claimNumber}` : "Open claim"}
              </TextLink>
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function Group({
  title,
  items,
  ...rest
}: {
  title: string;
  items: FlipItem[];
  flip: DecisionFlip;
  detail: CaseDetail;
  basePath: string;
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col">
      <h3 className="flex items-baseline gap-2 border-b border-line bg-surface-sunken px-4 py-1.5 text-xs font-medium text-ink-secondary">
        {title}
        <span className="font-mono font-normal text-ink-muted">{items.length}</span>
      </h3>
      <ul className="divide-y divide-line">
        {items.map((item) => (
          <ItemRow key={item.id} item={item} {...rest} />
        ))}
      </ul>
    </div>
  );
}

/**
 * DecisionFlip in full, on the Assessment tab: the current disposition, every open item
 * with its role and effort, the two hypothetical outcomes, the minimum set of checks,
 * and the next best action. Every simulated outcome is marked Hypothetical.
 */
export function DecisionFlipPanel({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const [showRest, setShowRest] = useState(false);
  const flip = readDecisionFlip(detail);
  if (!detail.assessment) return null;

  if (!flip) {
    return (
      <TabSection title="DecisionFlip" id="decision-flip" flush>
        <EmptyState title="Blockers not worked out for this version">
          Re-run verification to work out which open items would change the disposition
        </EmptyState>
      </TabSection>
    );
  }

  const blockers = flip.items.filter((item) => item.decision_blocker);
  const risks = flip.items.filter((item) => item.disqualifier_risk && !item.decision_blocker);
  const rest = flip.items.filter((item) => !item.decision_blocker && !item.disqualifier_risk);
  const set = flip.minimum_evidence;
  const next = flip.next_best_action;
  // The conditions are also appended to the action's text; they are listed apart below.
  const nextText = next.conditions.reduce((text, condition) => text.replace(condition, ""), next.text).trim();
  const shared = { flip, detail, basePath };
  const nameOf = (id: string) => {
    const item = flip.items.find((entry) => entry.id === id);
    return item ? nameItem(item, detail).label : id;
  };

  return (
    <TabSection
      title="DecisionFlip"
      id="decision-flip"
      meta={`v${flip.assessment_version} · policy ${flip.policy_version} · ${short(flip.inputs_hash)}`}
      whyLabel="Method"
      why={
        <>
          <p>
            Each open item is set to supported, then to contradicted, and the scoring policy is run again. The
            disposition that comes out is a simulation of the rules, not a finding.
          </p>
          <p className="font-mono text-xs">
            {plural(flip.evaluations, "rule run")} · {flip.search} search · {flip.flip_version}
          </p>
        </>
      }
      footer={`Simulated under policy ${flip.policy_version}, one item changed at a time. Nothing here is evidence`}
      flush
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3">
        <span className="text-xs text-ink-muted">Now</span>
        <DispositionStamp disposition={flip.current} />
        <p className="text-sm font-medium text-ink">{stateLine(flip)}</p>
        {flip.state === "has_blockers" ? (
          <p className="font-mono text-xs text-ink-muted">{plural(flip.items.length, "open item")}</p>
        ) : null}
      </div>

      {flip.state !== "has_blockers" && next.text ? (
        <p className="px-4 py-3 text-dense text-ink-secondary">{next.text}</p>
      ) : null}

      <Group title="Decision blockers" items={blockers} {...shared} />
      <Group title="Disqualifier risks" items={risks} {...shared} />
      {rest.length > 0 ? (
        <div className="flex flex-col border-t border-line">
          <button
            type="button"
            aria-expanded={showRest}
            onClick={() => setShowRest((value) => !value)}
            className="flex min-h-11 items-center justify-between gap-3 px-4 text-left text-dense text-ink-secondary transition-colors hover:bg-surface-raised md:min-h-9"
          >
            <span>
              Non-blocking <span className="font-mono text-xs text-ink-muted">{rest.length}</span>
            </span>
            <span className="inline-flex items-center gap-1 text-xs">
              {showRest ? "Hide" : "Show"}
              <Icon icon={ChevronDown} size={14} className={cn("transition-transform", showRest && "rotate-180")} />
            </span>
          </button>
          {showRest ? (
            <ul className="divide-y divide-line border-t border-line">
              {rest.map((item) => (
                <ItemRow key={item.id} item={item} {...shared} />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {flip.state === "has_blockers" && set ? (
        <>
          <div className="grid gap-3 border-t border-line p-4 md:grid-cols-2">
            <HypotheticalCard
              condition={
                set.item_ids.length === 1
                  ? "If the blocker is supported"
                  : set.item_ids.length === 2
                    ? "If both blockers are supported"
                    : `If all ${set.item_ids.length} blockers are supported`
              }
              outcome={outcomeWords(set.outcome, flip.current)}
            >
              {flip.minimal_sets.length > 1 ? (
                <p>{plural(flip.minimal_sets.length - 1, "other set")} of checks would also reach it</p>
              ) : null}
            </HypotheticalCard>
            {flip.worst_if_contradicted ? (
              <HypotheticalCard
                condition="If a blocker is contradicted"
                outcome={outcomeWords(flip.worst_if_contradicted, flip.current)}
              >
                {flip.worst_if_contradicted.disposition === flip.current && flip.target ? (
                  <p>{DISPOSITION_LABEL[flip.target]} is out of reach while it stands</p>
                ) : null}
              </HypotheticalCard>
            ) : null}
          </div>

          <div className="flex flex-col gap-2 border-t border-line px-4 py-3">
            <h3 className="flex flex-wrap items-baseline gap-x-2 text-dense font-medium text-ink">
              {flip.greedy ? "A sufficient set of checks to change the screening outcome" : flip.selection_label}
              <span className="font-mono text-xs font-normal text-ink-muted">
                {plural(set.item_ids.length, "check")} · {plural(set.documents.length, "document")}
              </span>
            </h3>
            <ol className="flex flex-col gap-1 text-dense">
              {set.documents.map((doc, index) => (
                <li key={doc.document} className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-2">
                  <span className="font-mono text-xs leading-5 text-ink-muted">{index + 1}</span>
                  <span className="flex flex-wrap items-baseline gap-x-3">
                    <span className="text-ink">{doc.document}</span>
                    <span className="text-xs text-ink-muted">
                      settles {doc.item_ids.map(nameOf).join(", ")}
                      {doc.seller_resolvable ? null : " · for you, not the seller"}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </>
      ) : null}

      {flip.state === "has_blockers" ? (
        <div className="flex flex-col items-start gap-2 border-t border-line px-4 py-3">
          <h3 className="text-xs font-medium text-ink-secondary">Next best action</h3>
          <p className="text-dense text-ink">{nextText}</p>
          {next.conditions.length > 0 ? (
            <ul className="flex flex-col gap-1 text-dense text-ink-secondary">
              {next.conditions.map((condition) => (
                <li key={condition} className="border-l-2 border-dashed border-ink-muted pl-3">
                  {condition}
                </li>
              ))}
            </ul>
          ) : null}
          <RequestLink flip={flip} detail={detail} basePath={basePath} className="w-full justify-center sm:w-auto" />
        </div>
      ) : null}
    </TabSection>
  );
}

/**
 * DecisionFlip on the Overview: how many blockers stand before the next disposition and
 * the one thing to do next. The full analysis is on the Assessment tab.
 */
export function DecisionFlipCompact({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const flip = readDecisionFlip(detail);
  if (!flip) return null;
  const set = flip.minimum_evidence;
  const next = flip.next_best_action;
  const nextText = next.conditions.reduce((text, condition) => text.replace(condition, ""), next.text).trim();
  const names = (set?.item_ids ?? []).map((id) => {
    const item = flip.items.find((entry) => entry.id === id);
    return item ? nameItem(item, detail).label : id;
  });

  return (
    <TabSection
      title="DecisionFlip"
      className="print:hidden"
      action={<TextLink href={`${basePath}/assessment#decision-flip`}>Full analysis</TextLink>}
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <DispositionStamp disposition={flip.current} size="sm" />
          <p className="text-sm font-medium text-ink">{blockerLine(flip) ?? stateLine(flip)}</p>
          {names.length > 0 ? <p className="text-dense text-ink-secondary">{names.join(" · ")}</p> : null}
        </div>
        {flip.state === "has_blockers" && set ? (
          <p className="hatch-hypothetical flex flex-wrap items-center gap-x-2 gap-y-1 self-start rounded-md border border-dashed border-ink-muted px-2 py-1 text-dense text-ink">
            <span className="rounded-xs bg-surface px-1 text-xs font-medium text-ink-secondary">Hypothetical</span>
            <span className="rounded-xs bg-surface px-1">
              if {set.item_ids.length === 1 ? "it is" : set.item_ids.length === 2 ? "both are" : "all are"} supported,{" "}
              {outcomeWords(set.outcome, flip.current)}
            </span>
          </p>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p className="min-w-0 text-dense text-ink">
            <span className="text-ink-muted">Next </span>
            {nextText}
          </p>
          <RequestLink flip={flip} detail={detail} basePath={basePath} />
        </div>
      </div>
    </TabSection>
  );
}
