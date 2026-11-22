import type { ClaimOut, RequestListOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { TextLink } from "@/components/ui/link";
import { claimNumbers } from "./adapt";
import { PRIORITY_REASON, isNeeded, requestPriority } from "./decision-flip/adapt";
import type { DecisionFlip } from "./decision-flip/types";
import { TabSection, TabStack } from "./parts";

type Item = RequestListOut["items"][number];

function Documents({
  items,
  claims,
  flip,
  start,
}: {
  items: Item[];
  claims: ClaimOut[];
  flip: DecisionFlip | null;
  /** The number of the first item, so the two groups count on as one list. */
  start: number;
}) {
  return (
    <ol start={start} className="flex flex-col divide-y divide-line text-dense">
      {items.map((item, index) => {
        const numbers = claimNumbers(item.claim_ids, claims);
        const reason =
          (item as { priority_reason?: string | null }).priority_reason ??
          (flip ? PRIORITY_REASON[requestPriority(item, flip)] : null);
        return (
          <li key={item.id} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 px-4 py-3">
            <span className="font-mono text-xs leading-5 text-ink-muted">{start + index}</span>
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="font-medium text-ink">{item.document}</span>
                {numbers.length ? (
                  <span className="font-mono text-xs whitespace-nowrap text-ink-secondary">
                    <span className="sr-only">settles </span>
                    {numbers.map((n) => `claim ${n}`).join(", ")}
                  </span>
                ) : null}
              </div>
              {item.questions.map((question) => (
                <p key={question} className="text-ink">
                  {question}
                </p>
              ))}
              <p className="text-xs text-ink-secondary">
                {item.reason}
                {reason ? <span className="text-ink-muted"> · {reason}</span> : null}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const groupHead = "flex items-baseline gap-2 border-b border-line bg-surface-sunken px-4 py-1.5 text-xs font-medium text-ink-secondary";

/**
 * What to ask the seller for, and why. With a DecisionFlip analysis the documents fall in
 * two groups: the ones the screening cannot be completed without, and the rest. Checks
 * DealProof can run again on its own are listed apart: they are the analyst's to retry,
 * not the seller's to answer.
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
  const analysed = flip && flip.assessment_version === list.assessment_version ? flip : null;
  const needed = list.items.filter((item) => isNeeded(requestPriority(item, analysed)));
  const helpful = list.items.filter((item) => !isNeeded(requestPriority(item, analysed)));
  const grouped = needed.length > 0;

  return (
    <TabStack>
      <TabSection title="Documents requested" meta={`${list.items.length} · from v${list.assessment_version}`} flush>
        {list.items.length === 0 ? (
          <p className="px-4 py-3 text-dense text-ink-secondary">No open claim needs a document from the seller</p>
        ) : grouped ? (
          <>
            <h3 className={groupHead}>
              Needed to complete our screening
              <span className="font-mono font-normal text-ink-muted">{needed.length}</span>
            </h3>
            <Documents items={needed} claims={claims} flip={analysed} start={1} />
            {helpful.length > 0 ? (
              <>
                <h3 className={`${groupHead} border-t`}>
                  Also helpful
                  <span className="font-mono font-normal text-ink-muted">{helpful.length}</span>
                </h3>
                <Documents items={helpful} claims={claims} flip={analysed} start={needed.length + 1} />
              </>
            ) : null}
          </>
        ) : (
          <Documents items={list.items} claims={claims} flip={null} start={1} />
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
