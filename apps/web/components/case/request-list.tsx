"use client";

import { ArrowRight, ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import type { ClaimOut, RequestListOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { DISPOSITION_LABEL } from "@/lib/labels";
import type { Disposition } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";
import { TextLink } from "@/components/ui/link";
import { claimNumbers } from "./adapt";
import { PRIORITY_REASON } from "./decision-flip/adapt";
import type { DecisionFlip } from "./decision-flip/types";
import { TabSection, TabStack } from "./parts";
import { type Branch, type RequestRow, requestRow, summarise } from "./request-effect";

const EFFORT_LABEL = { low: "Low effort", medium: "Medium effort", high: "High effort" } as const;

/** Old outcome, arrow, new outcome. Plain ink: a simulated outcome never wears a stamp. */
function Move({ from, to }: { from: Disposition; to: Disposition }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5">
      <span className="sr-only">would change from </span>
      <span className="text-ink-secondary">{DISPOSITION_LABEL[from]}</span>
      <Icon icon={ArrowRight} size={14} className="shrink-0 text-ink-muted" />
      <span className="sr-only"> to </span>
      <span className="font-medium text-ink">{DISPOSITION_LABEL[to]}</span>
    </span>
  );
}

const WITH_OTHERS = "with the rest of this group";

function branchWords(branch: Branch, from: Disposition) {
  if (branch.to === from) return `Stays ${DISPOSITION_LABEL[from]}`;
  return `${DISPOSITION_LABEL[branch.to]}${branch.withOthers ? `, ${WITH_OTHERS}` : ""}`;
}

/** The effect on the decision: one before and after, or the two branches. */
function Effect({ row, critical }: { row: RequestRow; critical: boolean }) {
  const { effect, item } = row;
  // Dashed, as every simulated outcome in the product is.
  const frame = "border-l border-dashed border-ink-muted pl-2";

  if (!effect) {
    return (
      <p className={cn(frame, "text-ink-secondary")}>
        {critical ? "Needed before the outcome can change" : PRIORITY_REASON[item.priority_reason]}
      </p>
    );
  }
  if (effect.kind === "stays") {
    return <p className={cn(frame, "text-ink-secondary")}>Stays {DISPOSITION_LABEL[effect.at]} either way</p>;
  }
  if (effect.kind === "moves") {
    return (
      <p className={cn(frame, "flex flex-wrap items-center gap-x-1.5")}>
        <Move from={effect.from} to={effect.to} />
        {effect.withOthers ? <span className="text-ink-secondary">{WITH_OTHERS}</span> : null}
      </p>
    );
  }
  return (
    <dl className={cn(frame, "grid grid-cols-[auto_minmax(0,1fr)] gap-x-3")}>
      <dt className="text-ink-secondary">If it holds</dt>
      <dd className="text-ink">{branchWords(effect.holds, effect.from)}</dd>
      <dt className="text-ink-secondary">If not</dt>
      <dd className="text-ink">{branchWords(effect.fails, effect.from)}</dd>
    </dl>
  );
}

function DocumentRow({
  row,
  number,
  claims,
  claimsHref,
  critical,
}: {
  row: RequestRow;
  number: number;
  claims: ClaimOut[];
  claimsHref: string;
  /** True in the group that can change the outcome. */
  critical: boolean;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const { item, effort, condition } = row;
  const numbers = claimNumbers(item.claim_ids, claims);

  return (
    <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 px-4 py-3">
      <span className="font-mono text-xs leading-5 text-ink-muted">{number}</span>
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          <span className="font-medium text-ink">{item.document}</span>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((value) => !value)}
            className="-my-3 -mr-3 inline-flex h-11 shrink-0 items-center gap-1 rounded-xs px-3 text-xs text-ink-muted transition-colors hover:text-ink md:-my-1 md:-mr-2 md:h-7 md:px-2"
          >
            Details
            <span className="sr-only"> for {item.document}</span>
            <Icon icon={ChevronDown} size={14} className={cn("transition-transform", open && "rotate-180")} />
          </button>
        </div>

        {numbers.length || effort ? (
        <p className="flex flex-wrap items-baseline gap-x-2 text-xs text-ink-secondary">
          {numbers.length ? (
            <span>
              Settles{" "}
              {numbers.map((n, index) => (
                <span key={n}>
                  {index > 0 ? ", " : null}
                  <TextLink href={claimsHref}>claim {n}</TextLink>
                </span>
              ))}
            </span>
          ) : null}
          {numbers.length && effort ? <span aria-hidden className="text-ink-muted">·</span> : null}
          {effort ? <span className="text-ink-muted">{EFFORT_LABEL[effort]}</span> : null}
        </p>
        ) : null}

        <Effect row={row} critical={critical} />

        {open ? (
          <dl
            id={panelId}
            className="mt-2 grid gap-x-4 gap-y-2 rounded-md bg-surface-raised px-3 py-2 sm:grid-cols-[7rem_minmax(0,1fr)]"
          >
            {item.questions.length ? (
              <>
                <dt className="text-ink-secondary">Asks the seller</dt>
                <dd className="flex flex-col gap-1 text-ink">
                  {item.questions.map((question) => (
                    <span key={question}>{question}</span>
                  ))}
                </dd>
              </>
            ) : null}
            <dt className="text-ink-secondary">Why it is open</dt>
            <dd className="text-ink">{item.reason}</dd>
            {condition ? (
              <>
                <dt className="text-ink-secondary">Condition</dt>
                <dd className="text-ink">{condition}</dd>
              </>
            ) : null}
            {numbers.map((n) => {
              const claim = claims.find((entry) => entry.number === n);
              return claim ? (
                <div key={n} className="contents">
                  <dt className="text-ink-secondary">Claim {n}</dt>
                  <dd className="text-ink">{claim.original_text}</dd>
                </div>
              ) : null;
            })}
          </dl>
        ) : null}
      </div>
    </li>
  );
}

function Figure({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("flex flex-col gap-1 px-4 py-3", className)}>
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  );
}

const figure = "font-mono text-xl font-medium tabular-nums";
const groupHead = "flex items-baseline gap-2 border-y border-line bg-surface-sunken px-4 py-1.5 text-xs font-medium text-ink-secondary";

/**
 * What to ask the seller for, and what each answer would do to the decision. The summary
 * comes first: how many documents, how many can change the outcome, and where the case
 * lands if they all come back clean. With a DecisionFlip analysis the documents fall in
 * two groups, the decision-critical ones first. Each row states its effect; the question,
 * the reason and the claim's wording open on request. Checks DealProof can run again on
 * its own are listed apart: they are the analyst's to retry, not the seller's to answer.
 */
export function RequestList({
  list,
  claims,
  basePath,
  flip = null,
}: {
  list: RequestListOut;
  claims: ClaimOut[];
  /** `/app/cases/{id}` */
  basePath: string;
  /** The analysis for the version the list was built on, if there is one. */
  flip?: DecisionFlip | null;
}) {
  const rows = list.items.map((item) => requestRow(item, flip));
  const critical = rows.filter((row) => row.item.group === "needed");
  const supporting = rows.filter((row) => row.item.group !== "needed");
  // Without an analysis every document is "also helpful" and the split says nothing.
  const grouped = critical.length > 0 && Boolean(flip);
  const summary = summarise(list, flip);
  const claimsHref = `${basePath}/claims`;

  const group = (items: RequestRow[], start: number, isCritical: boolean) => (
    <ol className="flex flex-col divide-y divide-line text-dense">
      {items.map((row, index) => (
        <DocumentRow
          key={row.item.id}
          row={row}
          number={start + index}
          claims={claims}
          claimsHref={claimsHref}
          critical={isCritical}
        />
      ))}
    </ol>
  );

  return (
    <TabStack>
      <TabSection
        title="Documents requested"
        meta={`from v${list.assessment_version}`}
        why={
          flip ? (
            <>
              <p>
                Decision-critical documents are the {flip.selection_label.replace(/^./, (c) => c.toLowerCase())}. The
                email lists them as “Needed to complete our screening” and the rest as “Also helpful”.
              </p>
              <p>
                Every outcome here is simulated by the screening rules, not a result. Effort is how hard a document is
                to obtain and only breaks ties in the order.
              </p>
            </>
          ) : undefined
        }
        whyLabel="How this is ordered"
        flush
      >
        {list.items.length === 0 ? (
          <p className="px-4 py-3 text-dense text-ink-secondary">No open claim needs a document from the seller</p>
        ) : (
          <>
            <dl className="grid grid-cols-2 text-dense sm:grid-cols-[auto_auto_minmax(0,1fr)]">
              <Figure label="Documents">
                <span className={figure}>{summary.total}</span>
              </Figure>
              <Figure label="Can change the outcome" className="border-l border-line">
                {summary.critical != null ? (
                  <span className={figure}>{summary.critical}</span>
                ) : (
                  <span className="text-ink-secondary">Not analysed</span>
                )}
              </Figure>
              {summary.current && summary.ifAllClean ? (
                <>
                  <Figure
                    label="If all come back clean"
                    className="col-span-2 border-t border-line sm:col-span-1 sm:border-t-0 sm:border-l"
                  >
                    <span className="flex min-h-7 flex-wrap items-center gap-x-2 text-sm">
                      {summary.ifAllClean === summary.current ? (
                        <span className="font-medium">Stays {DISPOSITION_LABEL[summary.current]}</span>
                      ) : (
                        <Move from={summary.current} to={summary.ifAllClean} />
                      )}
                      <span className="rounded-xs border border-dashed border-ink-muted px-1.5 text-xs text-ink-secondary">
                        Hypothetical
                      </span>
                    </span>
                  </Figure>
                </>
              ) : null}
            </dl>
            {flip && flip.assessment_version !== list.assessment_version ? (
              <p className="border-t border-line px-4 py-2 text-xs text-ink-secondary">
                Effects are from the v{flip.assessment_version} analysis. This list was built on v
                {list.assessment_version}
              </p>
            ) : null}

            {grouped ? (
              <>
                <h3 className={groupHead}>
                  Decision-critical
                  <span className="font-mono font-normal text-ink-muted">{critical.length}</span>
                </h3>
                {group(critical, 1, true)}
                {supporting.length > 0 ? (
                  <>
                    <h3 className={groupHead}>
                      Supporting
                      <span className="font-mono font-normal text-ink-muted">{supporting.length}</span>
                    </h3>
                    {group(supporting, critical.length + 1, false)}
                  </>
                ) : null}
              </>
            ) : (
              <div className="border-t border-line">{group(rows, 1, false)}</div>
            )}
          </>
        )}
      </TabSection>

      {list.analyst_retries.length > 0 ? (
        <TabSection
          title="For you to retry"
          meta={list.analyst_retries.length}
          why={<p>These checks did not run. The seller cannot settle them; running them again can. They are not part of the email, and each run states its credits first.</p>}
          action={<TextLink href={`${basePath}/claims?status=not_checked`}>Run from the ledger</TextLink>}
        >
          <ul className="hatch flex flex-col gap-2 rounded-md border border-dashed border-not-checked-line p-2 text-dense">
            {list.analyst_retries.map((retry) => {
              const number = retry.claim_id ? claimNumbers([retry.claim_id], claims)[0] : undefined;
              return (
                <li
                  key={`${retry.claim_id}:${retry.label}`}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xs bg-not-checked-tint px-3 py-2"
                >
                  <span className="flex flex-col gap-1">
                    <span className="text-ink">{retry.label}</span>
                    <span className="text-xs text-not-checked">
                      Not checked · {retry.reason.replace(/^./, (c) => c.toLowerCase())}
                      {number ? ` · claim ${number}` : null}
                    </span>
                  </span>
                  <span className="font-mono text-xs whitespace-nowrap text-ink-secondary">
                    {retry.estimated_credits != null
                      ? `about ${plural(retry.estimated_credits, "credit")}`
                      : "cost not estimated"}
                  </span>
                </li>
              );
            })}
          </ul>
        </TabSection>
      ) : null}
    </TabStack>
  );
}
