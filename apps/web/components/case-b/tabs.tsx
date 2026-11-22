"use client";

/**
 * The Assessment, Request, Sources, Documents and Cost tabs. Each reads the case from the
 * shared loader (components/case/case-context.tsx) and never fetches the case itself.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getPolicy,
  isFixtureMode,
  listAssessments,
  type AssessmentVersionOut,
  type MessageOut,
  type PolicyOut,
} from "@/lib/api/client";
import { plural } from "@/lib/format";
import { identityResolved } from "@/components/case/adapt";
import { useCase, useCaseDetail } from "@/components/case/case-context";
import { BlockedByIdentity, EmptyState, TabHeading } from "@/components/case/parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { claimNumbers, usesBySource } from "./adapt";
import { AssessmentView } from "./assessment-view";
import { BuildRequestList } from "./build-request-list";
import { CostPanel } from "./cost-panel";
import { DocumentsPanel } from "./documents-panel";
import { Section, TextLink } from "./parts";
import { RequestApproval } from "./request-approval";
import { RequestList } from "./request-list";
import { SourcesTable } from "./sources-table";

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Button asChild size="sm">
      <Link href={href}>{children}</Link>
    </Button>
  );
}

/* ───────────────────────── Assessment ───────────────────────── */

export function AssessmentTab() {
  const detail = useCaseDetail();
  const { caseId, basePath } = useCase();
  const asked = Number(useSearchParams().get("v"));
  const latest = detail.assessment;
  const [history, setHistory] = useState<AssessmentVersionOut[] | null>(null);
  const [historyFailed, setHistoryFailed] = useState(false);
  const [policy, setPolicy] = useState<PolicyOut | null>(null);

  // The case carries the latest version. Earlier ones are read once, and again whenever
  // a new version arrives.
  useEffect(() => {
    let live = true;
    listAssessments(caseId).then(
      (versions) => {
        if (!live) return;
        setHistory(versions);
        setHistoryFailed(false);
      },
      () => live && setHistoryFailed(true),
    );
    return () => {
      live = false;
    };
  }, [caseId, latest?.version]);

  useEffect(() => {
    let live = true;
    getPolicy().then(
      (next) => live && setPolicy(next),
      () => {},
    );
    return () => {
      live = false;
    };
  }, []);

  if (!latest) {
    return identityResolved(detail) ? (
      <EmptyState
        title="Not assessed yet"
        actions={<LinkButton href={`${basePath}/claims`}>Go to claims</LinkButton>}
      >
        The five judgments appear here once verification has run on this case.
      </EmptyState>
    ) : (
      <BlockedByIdentity what="DealProof does not judge a company it has not identified." />
    );
  }

  // An earlier version was asked for and the history has not arrived. Showing the current
  // one in its place would be the wrong record, so wait.
  if (asked > 0 && asked !== latest.version && history === null && !historyFailed) {
    return (
      <p role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-secondary">
        Opening version {asked}
      </p>
    );
  }

  const versions = (history?.length ? [...history] : [latest]).sort((a, b) => a.version - b.version);
  // The case is the newer word when a version has just landed and the history is behind.
  if (!versions.some((item) => item.version === latest.version)) versions.push(latest);
  const viewing = versions.some((item) => item.version === asked) ? asked : latest.version;

  return (
    <div className="flex flex-col gap-4">
      {historyFailed ? (
        <p role="alert" className="rounded-md border border-line-strong bg-surface px-3 py-2 text-dense text-ink">
          Earlier versions could not be loaded. The current version is shown; the history below
          is incomplete until the page is reloaded.
        </p>
      ) : null}
      <AssessmentView
        basePath={`${basePath}/assessment`}
        versions={versions}
        claims={detail.claims}
        viewing={viewing}
        typeReason={detail.profile?.company_type_reason ?? null}
        policy={policy}
      />
    </div>
  );
}

/* ───────────────────────── Request and approval ───────────────────────── */

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

export function RequestTab() {
  const detail = useCaseDetail();
  const { caseId, basePath, mutate, reload } = useCase();
  const preview = useSearchParams().get("preview");
  const { request_list: list, claims, documents, assessment } = detail;

  if (!list) {
    if (!identityResolved(detail)) {
      return <BlockedByIdentity what="A request is built from an assessment." />;
    }
    return assessment ? (
      <EmptyState
        title="No request list yet"
        actions={<BuildRequestList caseId={caseId} onBuilt={reload} />}
      >
        DealProof can list the documents that would settle this case&apos;s open claims and draft
        the email to the seller. You review, edit and approve before anything is sent.
      </EmptyState>
    ) : (
      <EmptyState
        title="Nothing to request right now"
        actions={<LinkButton href={`${basePath}/claims`}>Go to claims</LinkButton>}
      >
        A request list is built from an assessment, and this case has not been assessed yet.
      </EmptyState>
    );
  }

  const previewState =
    isFixtureMode && PREVIEW_STATES.includes(preview as PreviewState)
      ? (preview as PreviewState)
      : null;
  const message = previewState ? previewMessage(detail.message, previewState) : detail.message;
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
      <TabHeading
        title="Request to seller"
        summary="The documents that would settle what is still open, and one email asking for them. A named person approves the exact wording, and it is sent once."
      >
        {previewState ? (
          <Badge variant="outline" className="border-dashed">
            Fixture preview · {previewState}
          </Badge>
        ) : null}
        {testMode ? <Badge variant="test-mode">Test mode</Badge> : null}
      </TabHeading>

      {list.items.length === 0 && list.analyst_retries.length === 0 ? (
        <EmptyState
          title="Nothing to request right now"
          actions={<LinkButton href={`${basePath}/claims`}>Go to claims</LinkButton>}
        >
          All checked claims are settled, or no open claim requires a document from the seller.
          You can still select a claim from the ledger to add a document request.
        </EmptyState>
      ) : (
        <div className="grid gap-8 2xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <RequestList list={list} claims={claims} basePath={basePath} />
          <RequestApproval
            key={previewState ?? "record"}
            caseId={caseId}
            list={list}
            documents={requested}
            initialMessage={message}
            testMode={testMode}
            // The case header and the tab row read the message from the shared case.
            onChange={previewState ? undefined : (next) => mutate((d) => ({ ...d, message: next }))}
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
                    <TextLink href={`${basePath}/assessment?v=${version}`}>
                      View v{version} diff
                    </TextLink>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-ink-secondary">
            Files and their deletion dates are on the{" "}
            <TextLink href={`${basePath}/documents`}>Documents tab</TextLink>.
          </p>
        </Section>
      ) : null}
    </div>
  );
}

/* ───────────────────────── Sources ───────────────────────── */

export function SourcesTab() {
  const detail = useCaseDetail();
  const { caseId } = useCase();

  if (detail.sources.length === 0) {
    return (
      <EmptyState title="No sources recorded yet">
        Sources appear here with their dates and retrieval times as soon as verification begins.
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <TabHeading
        title="Source record"
        summary="Everything DealProof read for this case: where it came from, the exact page or request, when it was retrieved and which facts rest on it. Enough to repeat the work and reach the same record."
      />
      <SourcesTable
        sources={detail.sources}
        uses={Object.fromEntries(usesBySource(detail))}
        exportName={caseId}
      />
    </div>
  );
}

/* ───────────────────────── Documents ───────────────────────── */

export function DocumentsTab() {
  const detail = useCaseDetail();
  const { basePath } = useCase();

  if (detail.documents.length === 0 && detail.deletions.length === 0) {
    return (
      <EmptyState
        title="No files on this case"
        actions={<LinkButton href={`${basePath}/claims`}>Go to claims</LinkButton>}
      >
        Seller documents you upload appear here with the date they will be deleted. They are
        used only for this case.
      </EmptyState>
    );
  }
  return (
    <DocumentsPanel
      basePath={basePath}
      documents={detail.documents}
      deletions={detail.deletions}
      requestList={detail.request_list}
      versions={detail.assessment ? [detail.assessment] : []}
    />
  );
}

/* ───────────────────────── Cost ───────────────────────── */

export function CostTab() {
  const { cost } = useCaseDetail();
  const { basePath } = useCase();

  const nothingYet =
    cost.by_step.length === 0 &&
    cost.crustdata_credits === 0 &&
    cost.llm_usd === 0 &&
    cost.unknown_cost_calls === 0 &&
    !cost.shared_discovery;

  if (nothingYet) {
    return (
      <EmptyState title="No usage recorded yet">
        Credits and model usage appear here once a search or verification step runs.
      </EmptyState>
    );
  }
  return <CostPanel cost={cost} basePath={basePath} />;
}
