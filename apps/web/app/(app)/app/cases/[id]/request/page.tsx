import type { Metadata } from "next";
import { getCase, isFixtureMode, type MessageOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { claimNumbers } from "@/components/case-b/adapt";
import { BuildRequestList } from "@/components/case-b/build-request-list";
import { load } from "@/components/case-b/load";
import { EmptyState, LoadError, Section, TabHeader, TextLink } from "@/components/case-b/parts";
import { RequestApproval } from "@/components/case-b/request-approval";
import { RequestList } from "@/components/case-b/request-list";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = { title: "Request and approval · DealProof" };

const PREVIEW_STATES = ["draft", "approved", "sending", "sent", "failed", "unknown"] as const;
type PreviewState = (typeof PREVIEW_STATES)[number];

/**
 * Fixture mode only: `?preview=<state>` shows the tab in a state the fixture case is not in,
 * so every state can be reviewed without a mail provider. Ignored against the real service.
 */
function previewMessage(message: MessageOut | null, state: PreviewState): MessageOut | null {
  if (state === "draft" || !message) return null;
  if (state === "approved") return { ...message, status: "approved", send: null };
  return {
    ...message,
    status: state,
    send: message.send
      ? {
          ...message.send,
          status: state,
          test_mode: false,
          error: state === "failed" ? "Mailbox unavailable (fixture)" : null,
        }
      : null,
  };
}

export default async function RequestPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ preview?: string }>;
}) {
  const [{ id }, { preview }] = await Promise.all([params, searchParams]);
  const detail = await load((init) => getCase(id, init));
  if (!detail.ok) return <LoadError what="the request" status={detail.status} />;

  const { request_list: list, claims, documents, assessment } = detail.data;

  if (!list) {
    return assessment ? (
      <div className="flex flex-col items-start gap-4">
        <EmptyState
          heading="No request list yet"
          body="DealProof can list the documents that would settle this case's open claims and draft the email to the seller. You review, edit and approve before anything is sent."
        />
        <BuildRequestList caseId={id} />
      </div>
    ) : (
      <EmptyState
        heading="Nothing to request right now"
        body="A request list is built from an assessment, and this case has not been assessed yet."
        action={{ href: `/app/cases/${id}/claims`, label: "Go to claims" }}
      />
    );
  }

  const previewState =
    isFixtureMode && PREVIEW_STATES.includes(preview as PreviewState)
      ? (preview as PreviewState)
      : null;
  const message = previewState
    ? previewMessage(detail.data.message, previewState)
    : detail.data.message;
  const liveSendPreview = previewState !== null && !["draft", "approved"].includes(previewState);
  const testMode = !list.email_send_enabled && !liveSendPreview;

  const requested = list.items.map((item) => ({
    id: item.id,
    name: item.document,
    claim_number: claimNumbers(item.claim_ids, claims)[0] ?? 0,
  }));
  const responses = documents.filter((doc) => doc.kind === "seller_response");

  return (
    <div className="flex flex-col gap-8">
      <TabHeader
        title="Request to seller"
        lead="The documents that would settle what is still open, and one email asking for them. A named person approves the exact wording, and it is sent once."
        action={
          <span className="flex flex-wrap items-center gap-2">
            {previewState ? (
              <Badge variant="outline" className="border-dashed">
                Fixture preview · {previewState}
              </Badge>
            ) : null}
            {testMode ? <Badge variant="test-mode">Test mode</Badge> : null}
          </span>
        }
      />

      {list.items.length === 0 && list.analyst_retries.length === 0 ? (
        <EmptyState
          heading="Nothing to request right now"
          body="All checked claims are settled, or no open claim requires a document from the seller. You can still select a claim from the ledger to add a document request."
          action={{ href: `/app/cases/${id}/claims`, label: "Go to claims" }}
        />
      ) : (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <RequestList list={list} claims={claims} caseId={id} />
          <RequestApproval
            key={previewState ?? "record"}
            caseId={id}
            list={list}
            documents={requested}
            initialMessage={message}
            testMode={testMode}
          />
        </div>
      )}

      {responses.length > 0 ? (
        <Section
          title="Seller documents"
          meta={responses.length}
          lead="Documents the seller sent back. DealProof rechecks the claims each one bears on and records a new assessment version."
        >
          <ul className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface text-dense">
            {responses.map((doc) => {
              const version =
                assessment && assessment.trigger.includes(doc.filename) ? assessment.version : null;
              return (
                <li key={doc.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3">
                  <span className="text-ink">{doc.filename}</span>
                  <span className="text-ink-secondary">
                    Affected {plural(doc.claims_extracted, "claim")}
                  </span>
                  {version ? (
                    <TextLink href={`/app/cases/${id}/assessment?v=${version}`}>
                      View v{version} diff
                    </TextLink>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-ink-secondary">
            Files and their deletion dates are on the{" "}
            <TextLink href={`/app/cases/${id}/documents`}>Documents tab</TextLink>.
          </p>
        </Section>
      ) : null}
    </div>
  );
}
