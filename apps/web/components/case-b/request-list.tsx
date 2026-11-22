import type { ClaimOut, RequestListOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { claimNumbers } from "./adapt";
import { Section, TextLink } from "./parts";

/**
 * What to ask the seller for, and why. Each document names the question it would answer
 * and the claim it would settle. Checks DealProof can run again on its own are listed
 * apart: they are the analyst's to retry, not the seller's to answer.
 */
export function RequestList({
  list,
  claims,
  caseId,
}: {
  list: RequestListOut;
  claims: ClaimOut[];
  caseId: string;
}) {
  return (
    <div className="flex flex-col gap-6">
      <Section
        title="Documents requested"
        meta={list.items.length}
        lead={`Built from assessment version ${list.assessment_version}.`}
      >
        {list.items.length === 0 ? (
          <p className="rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-secondary">
            No open claim needs a document from the seller.
          </p>
        ) : (
          <ol className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface text-dense">
            {list.items.map((item, index) => {
              const numbers = claimNumbers(item.claim_ids, claims);
              return (
                <li key={item.id} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 px-4 py-3">
                  <span className="font-mono text-xs leading-5 text-ink-muted">{index + 1}</span>
                  <div className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <span className="font-medium text-ink">{item.document}</span>
                      {numbers.length ? (
                        <span className="font-mono text-xs whitespace-nowrap text-ink-secondary">
                          <span aria-hidden>← </span>
                          <span className="sr-only">settles </span>
                          {numbers.map((n) => `claim ${n}`).join(", ")}
                        </span>
                      ) : null}
                    </div>
                    <dl className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1">
                      <dt className="text-xs leading-5 text-ink-muted">
                        {item.questions.length === 1 ? "Resolves" : "Resolve"}
                      </dt>
                      <dd className="text-ink">
                        {item.questions.length ? (
                          <ul className="flex flex-col gap-1">
                            {item.questions.map((question) => (
                              <li key={question}>{question}</li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-ink-secondary">No question recorded</span>
                        )}
                      </dd>
                      <dt className="text-xs leading-5 text-ink-muted">Why</dt>
                      <dd className="text-ink-secondary">{item.reason}</dd>
                    </dl>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </Section>

      {list.analyst_retries.length > 0 ? (
        <Section
          title="For you to retry"
          meta={list.analyst_retries.length}
          lead="These checks were not run. The seller cannot settle them; running them again can. They are not part of the email."
        >
          <ul className="hatch flex flex-col gap-2 rounded-lg border border-dashed border-not-checked-line p-2 text-dense">
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
          <p className="text-xs text-ink-secondary">
            Run a check from the{" "}
            <TextLink href={`/app/cases/${caseId}/claims?status=not_checked`}>claims ledger</TextLink>.
            Each run spends credits and says so first.
          </p>
        </Section>
      ) : null}
    </div>
  );
}
