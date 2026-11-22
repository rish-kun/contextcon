"use client";

/**
 * The Assessment, Request, Sources, Documents and Cost tabs. Each reads the case from the
 * shared loader (components/case/case-context.tsx) and never fetches the case itself.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  getPolicy,
  isFixtureMode,
  listAssessments,
  type AssessmentVersionOut,
  type MessageOut,
  type PolicyOut,
} from "@/lib/api/client";
import { plural } from "@/lib/format";
import { CoverageMap, type CoverageSelection } from "@/components/explainers/coverage-map";
import { coverageFromClaims } from "@/components/explainers/derive";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TextLink } from "@/components/ui/link";
import { claimNumbers, identityResolved, toClaim, usesBySource } from "./adapt";
import { AssessmentView } from "./assessment-view";
import { BuildRequestList } from "./build-request-list";
import { useCase, useCaseDetail } from "./case-context";
import { CostPanel } from "./cost-panel";
import { readDecisionFlip } from "./decision-flip/adapt";
import { DecisionFlipPanel } from "./decision-flip/panel";
import { DocumentsPanel } from "./documents-panel";
import { AssessmentPending, BlockedByIdentity, TabEmpty, TabSection, TabStack } from "./parts";
import { RequestApproval } from "./request-approval";
import { RequestList } from "./request-list";
import { SourcesTable } from "./sources-table";

/* ───────────────────────── Assessment history ───────────────────────── */

/**
 * Every assessment version of the case. The case carries only the latest; earlier ones
 * are read once, and again whenever a new version arrives.
 */
function useAssessmentHistory(caseId: string, latestVersion: number | undefined) {
  const [history, setHistory] = useState<AssessmentVersionOut[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (latestVersion === undefined) return;
    let live = true;
    listAssessments(caseId).then(
      (versions) => {
        if (!live) return;
        setHistory(versions);
        setFailed(false);
      },
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [caseId, latestVersion]);

  return { history, failed };
}

/**
 * The versions to link documents against: the whole history once it has loaded, and the
 * latest version until then. An upload links to the version whose `trigger_document_ids`
 * names it, by document id.
 */
function linkableVersions(
  history: AssessmentVersionOut[] | null,
  latest: AssessmentVersionOut | null,
): AssessmentVersionOut[] {
  if (history?.length) {
    return latest && !history.some((item) => item.version === latest.version)
      ? [...history, latest]
      : history;
  }
  return latest ? [latest] : [];
}

/* ───────────────────────── Assessment ───────────────────────── */

export function AssessmentTab() {
  const detail = useCaseDetail();
  const { caseId, basePath } = useCase();
  const asked = Number(useSearchParams().get("v"));
  const latest = detail.assessment;
  const { history, failed: historyFailed } = useAssessmentHistory(caseId, latest?.version);
  const [policy, setPolicy] = useState<PolicyOut | null>(null);

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
      <AssessmentPending what="The five judgments" />
    ) : (
      <BlockedByIdentity what="A company is judged only once it is identified" />
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
    <TabStack>
      {historyFailed ? (
        <p role="alert" className="rounded-md border border-line-strong bg-surface px-3 py-2 text-dense text-ink">
          Earlier versions did not load. Reload to see the full history
        </p>
      ) : null}
      <AssessmentView
        basePath={`${basePath}/assessment`}
        versions={versions}
        claims={detail.claims}
        documents={detail.documents}
        viewing={viewing}
        typeReason={detail.profile?.company_type_reason ?? null}
        policy={policy}
        decisionFlip={<DecisionFlipPanel detail={detail} basePath={basePath} />}
      />
    </TabStack>
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
  const { history } = useAssessmentHistory(caseId, assessment?.version);
  const versions = linkableVersions(history, assessment);

  if (!list) {
    if (!identityResolved(detail)) {
      return <BlockedByIdentity what="A request is built from an assessment" />;
    }
    return assessment ? (
      <TabEmpty title="No request list yet" actions={<BuildRequestList caseId={caseId} onBuilt={reload} />}>
        Lists the documents that would settle the open claims and drafts the email
      </TabEmpty>
    ) : (
      <AssessmentPending what="A request list is built from the assessment, and" />
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
    <TabStack>
      {previewState || testMode ? (
        <p className="flex flex-wrap items-center gap-2">
          {previewState ? (
            <Badge variant="outline" className="border-dashed">
              Fixture preview · {previewState}
            </Badge>
          ) : null}
          {testMode ? <Badge variant="test-mode">Test mode</Badge> : null}
        </p>
      ) : null}

      {list.items.length === 0 && list.analyst_retries.length === 0 ? (
        <TabEmpty
          title="Nothing to request"
          actions={
            <Button asChild size="sm">
              <Link href={`${basePath}/claims`}>Open claims</Link>
            </Button>
          }
        >
          No open claim needs a document from the seller
        </TabEmpty>
      ) : (
        <div className="grid items-start gap-4 2xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <RequestList list={list} claims={claims} basePath={basePath} flip={readDecisionFlip(detail)} />
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
        <TabSection
          title="Seller documents"
          meta={responses.length}
          why={<p>Each document the seller sends back is rechecked against the claims it bears on, and a new assessment version is recorded.</p>}
          action={<TextLink href={`${basePath}/documents`}>All files</TextLink>}
          flush
        >
          <ul className="flex flex-col divide-y divide-line text-dense">
            {responses.map((doc) => {
              // The version this upload caused, matched by document id.
              const version =
                versions.find((item) => item.trigger_document_ids.includes(doc.id))?.version ?? null;
              return (
                <li key={doc.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-2">
                  <span className="text-ink">{doc.filename}</span>
                  <span className="text-ink-secondary">{plural(doc.claims_extracted, "claim")} affected</span>
                  {version ? (
                    <TextLink href={`${basePath}/assessment?v=${version}`}>v{version} diff</TextLink>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </TabSection>
      ) : null}
    </TabStack>
  );
}

/* ───────────────────────── Sources ───────────────────────── */

export function SourcesTab() {
  const detail = useCaseDetail();
  const { caseId } = useCase();
  const [selection, setSelection] = useState<CoverageSelection | null>(null);
  const identityOpen = !identityResolved(detail);
  const coverage = useMemo(
    () => coverageFromClaims(detail.claims.map(toClaim), { identityOpen }),
    [detail.claims, identityOpen],
  );

  if (detail.sources.length === 0) {
    return <TabEmpty title="No sources yet">Sources are recorded as soon as verification reads one</TabEmpty>;
  }
  return (
    <TabStack>
      <TabSection
        title="Coverage"
        meta={plural(coverage.rows.length, "kind of claim", "kinds of claim")}
        why={<p>Each kind of claim against each class of source. Pick a cell or a column head to narrow the table below to those sources.</p>}
        whyLabel="How to read"
      >
        <CoverageMap model={coverage} selection={selection} onSelect={setSelection} />
      </TabSection>
      <SourcesTable
        sources={detail.sources}
        uses={Object.fromEntries(usesBySource(detail))}
        exportName={caseId}
        filter={
          selection
            ? {
                sourceClass: selection.reliability,
                category: selection.category,
                // A cell narrows to the sources its facts came from; a column head to the class.
                sourceIds:
                  selection.category === null
                    ? null
                    : (coverage.rows
                        .find((row) => row.category === selection.category)
                        ?.cells.find((cell) => cell.reliability === selection.reliability)
                        ?.source_ids ?? []),
              }
            : null
        }
        onClearFilter={() => setSelection(null)}
      />
    </TabStack>
  );
}

/* ───────────────────────── Documents ───────────────────────── */

export function DocumentsTab() {
  const detail = useCaseDetail();
  const { caseId, basePath } = useCase();
  const { history } = useAssessmentHistory(caseId, detail.assessment?.version);

  if (detail.documents.length === 0 && detail.deletions.length === 0) {
    return (
      <TabEmpty
        title="No files yet"
        actions={
          <Button asChild size="sm">
            <Link href={`${basePath}/claims#add-to-ledger`}>Upload a document</Link>
          </Button>
        }
      >
        Uploads are used only for this case and carry their deletion date
      </TabEmpty>
    );
  }
  return (
    <DocumentsPanel
      basePath={basePath}
      documents={detail.documents}
      deletions={detail.deletions}
      requestList={detail.request_list}
      versions={linkableVersions(history, detail.assessment)}
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
    return <TabEmpty title="No usage yet">Credits and model usage appear once a step runs</TabEmpty>;
  }
  return <CostPanel cost={cost} basePath={basePath} />;
}
