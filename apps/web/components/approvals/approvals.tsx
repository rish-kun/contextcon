"use client";

import Link from "next/link";
import { caseHref, useSessionUser, useShell } from "@/components/app-shell";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  PanelFooter,
  PanelHeader,
  RowLink,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";
import type { CaseSummary, UserOut } from "@/lib/api/client";
import { formatShortDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { REQUEST_STATE_LABEL, requestState, type CaseRecord, type RequestState } from "@/lib/workspace-state";

interface Entry {
  item: CaseSummary;
  record: CaseRecord;
  state: RequestState;
  blockers: number;
  others: number;
  /** Document names, blockers first, as the request lists them. */
  documents: string[];
  /** Null while the draft is only DealProof's and no one has saved a revision. */
  revision: number | null;
  draftedBy: string;
  draftedAt: string;
  /** True when approving this request would let a real email leave. */
  live: boolean;
}

const requestHref = (id: string) => `${caseHref(id)}/request`;

/** The person who saved the revision, when this screen can name them. */
function nameOf(userId: string, record: CaseRecord, me: UserOut): string {
  if (userId === me.id) return me.display_name;
  if (userId === record.owner.user_id) return record.owner.display_name;
  if (userId === record.message?.approval?.approver_user_id) return record.message.approval.approver_display_name;
  return "A workspace member";
}

function entryOf(item: CaseSummary, record: CaseRecord | undefined, me: UserOut): Entry | null {
  if (!record) return null;
  const state = requestState(record);
  if (state === "none") return null;
  const items = [...(record.request_list?.items ?? [])].sort((a, b) => a.priority - b.priority);
  const needed = items.filter((entry) => entry.group === "needed");
  const revision = record.message?.current_revision ?? null;
  const send = record.message?.send ?? null;
  return {
    item,
    record,
    state,
    blockers: needed.length,
    others: items.length - needed.length,
    documents: [...needed, ...items.filter((entry) => entry.group !== "needed")].map((entry) => entry.document),
    revision: revision?.number ?? null,
    draftedBy: revision ? nameOf(revision.entered_by_user_id, record, me) : "DealProof",
    draftedAt: revision?.created_at ?? record.request_list?.created_at ?? item.updated_at,
    live: send ? !send.test_mode : Boolean(record.request_list?.email_send_enabled),
  };
}

function ModeTag({ live }: { live: boolean }) {
  return live ? (
    <Badge variant="outline">Live</Badge>
  ) : (
    <Badge variant="test-mode">Test mode</Badge>
  );
}

/** "5" over "2 blockers · 3 others", then the documents by name. */
function DocumentsCell({ entry }: { entry: Entry }) {
  const total = entry.blockers + entry.others;
  if (total === 0) return <span className="text-ink-muted">No documents listed</span>;
  return (
    <div className="flex min-w-0 flex-col">
      <span className="font-mono text-xs whitespace-nowrap text-ink">
        <span className="font-medium">{total}</span>
        <span className="text-ink-muted"> · </span>
        <span className={entry.blockers > 0 ? "font-medium" : "text-ink-muted"}>{plural(entry.blockers, "blocker")}</span>
        <span className="text-ink-muted"> · </span>
        <span className="text-ink-secondary">{plural(entry.others, "other")}</span>
      </span>
      <span className="max-w-96 truncate text-xs text-ink-muted" title={entry.documents.join(", ")}>
        {entry.documents.join(", ")}
      </span>
    </div>
  );
}

function CompanyCell({ entry }: { entry: Entry }) {
  const recipient = entry.record.message?.current_revision.recipient.trim();
  return (
    <>
      <RowLink stretch href={requestHref(entry.item.id)}>
        {entry.item.name}
      </RowLink>
      <span className="block max-w-64 truncate text-xs text-ink-muted">
        {recipient ? `To ${recipient}` : "No recipient entered"}
      </span>
    </>
  );
}

function Drafted({ entry }: { entry: Entry }) {
  return (
    <div className="flex flex-col whitespace-nowrap">
      <span>{entry.draftedBy}</span>
      <time dateTime={entry.draftedAt} className="font-mono text-xs text-ink-muted">
        {formatShortDateTime(entry.draftedAt)}
      </time>
    </div>
  );
}

function Revision({ entry }: { entry: Entry }) {
  return entry.revision === null ? (
    <span className="text-ink-muted">Not saved yet</span>
  ) : (
    <span className="font-mono text-xs whitespace-nowrap">Revision {entry.revision}</span>
  );
}

/** What a waiting request needs from a person, in the product's own words. */
const WAITING_STATE: Partial<Record<RequestState, string>> = {
  draft: "Draft · awaiting approval",
  approved: "Approved · not sent yet",
  failed: "Failed · not sent",
  unknown: "Send result unknown",
  sending: "Sending",
};

function Inbox({ entries }: { entries: Entry[] }) {
  return (
    <Table density="two-line" flush>
      <TableHeader>
        <TableRow>
          <TableHead>Company</TableHead>
          <TableHead>Documents requested</TableHead>
          <TableHead>Draft</TableHead>
          <TableHead>Drafted</TableHead>
          <TableHead>Mode</TableHead>
          <TableHead>State</TableHead>
          <TableHead>
            <span className="sr-only">Action</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry) => {
          const approval = entry.record.message?.approval;
          return (
            <TableRow key={entry.item.id} className="relative">
              <TableCell>
                <CompanyCell entry={entry} />
              </TableCell>
              <TableCell>
                <DocumentsCell entry={entry} />
              </TableCell>
              <TableCell>
                <Revision entry={entry} />
              </TableCell>
              <TableCell>
                <Drafted entry={entry} />
              </TableCell>
              <TableCell>
                <ModeTag live={entry.live} />
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                  <span>{WAITING_STATE[entry.state] ?? REQUEST_STATE_LABEL[entry.state]}</span>
                  {entry.state === "approved" && approval ? (
                    <span className="text-xs whitespace-nowrap text-ink-muted">
                      by {approval.approver_display_name},{" "}
                      <time dateTime={approval.approved_at} className="font-mono">
                        {formatShortDateTime(approval.approved_at)}
                      </time>
                    </span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="text-right">
                <span className="text-dense font-medium whitespace-nowrap text-accent">Review</span>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** One receipt per send: what happened to the approved revision, and who approved it. */
function Receipts({ entries }: { entries: Entry[] }) {
  return (
    <Table density="two-line" flush>
      <TableHeader>
        <TableRow>
          <TableHead>Company</TableHead>
          <TableHead>Receipt</TableHead>
          <TableHead>Documents requested</TableHead>
          <TableHead>Draft</TableHead>
          <TableHead>Approved by</TableHead>
          <TableHead numeric>Completed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry) => {
          const message = entry.record.message;
          const send = message?.send;
          const approval = message?.approval;
          const suppressed = entry.state === "suppressed";
          const at = send?.completed_at ?? send?.dispatched_at ?? send?.created_at ?? null;
          return (
            <TableRow key={entry.item.id} className="relative">
              <TableCell>
                <CompanyCell entry={entry} />
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-start gap-0.5">
                  <span
                    className={cn(
                      "rounded-xs px-1.5 py-0.5 text-xs whitespace-nowrap",
                      suppressed
                        ? "border border-dashed border-not-checked-line bg-not-checked-tint text-not-checked"
                        : "border border-line bg-surface-sunken text-ink",
                    )}
                  >
                    {REQUEST_STATE_LABEL[entry.state]}
                  </span>
                  <span className="max-w-64 truncate font-mono text-2xs text-ink-muted">
                    {suppressed
                      ? "No email left DealProof"
                      : send?.provider_message_id
                        ? `Provider id ${send.provider_message_id}`
                        : "No provider id on record"}
                    {send && send.attempts > 1 ? ` · ${plural(send.attempts, "attempt")}` : null}
                  </span>
                </div>
              </TableCell>
              <TableCell>
                <DocumentsCell entry={entry} />
              </TableCell>
              <TableCell>
                <Revision entry={entry} />
              </TableCell>
              <TableCell>
                {approval ? (
                  <div className="flex flex-col whitespace-nowrap">
                    <span>{approval.approver_display_name}</span>
                    <time dateTime={approval.approved_at} className="font-mono text-xs text-ink-muted">
                      {formatShortDateTime(approval.approved_at)}
                    </time>
                  </div>
                ) : (
                  <span className="text-ink-muted">Not recorded</span>
                )}
              </TableCell>
              <TableCell numeric muted={!at}>
                {at ? <time dateTime={at}>{formatShortDateTime(at)}</time> : "–"}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

const RECEIPT_STATES: RequestState[] = ["sent", "suppressed"];

/**
 * `/app/approvals`. Every seller request across cases: the ones waiting on a named person
 * first, then the receipts of what was sent or suppressed. Nothing is approved from here:
 * a row opens the case's Request tab, where one exact revision is approved.
 */
export function Approvals() {
  const { openVerify } = useShell();
  const me = useSessionUser();
  const [state, retry] = useWorkspace();

  if (state.status === "loading") {
    return (
      <Page>
        <PageHeader title="Approvals" />
        <Panel>
          <LoadingState label="Loading approvals" shape="rows" density="two-line" />
        </Panel>
      </Page>
    );
  }
  if (state.status === "error") {
    return (
      <Page>
        <PageHeader title="Approvals" />
        <ErrorState size="page" what="Approvals" reason={state.message} status={state.code} onRetry={retry} />
      </Page>
    );
  }

  const workspace = state.data;
  const entries = workspace.cases
    .map((item) => entryOf(item, workspace.records[item.id], me))
    .filter((entry): entry is Entry => entry !== null)
    .sort((a, b) => b.draftedAt.localeCompare(a.draftedAt));
  const waiting = entries.filter((entry) => !RECEIPT_STATES.includes(entry.state));
  const receipts = entries.filter((entry) => RECEIPT_STATES.includes(entry.state));
  const drafts = waiting.filter((entry) => entry.state === "draft").length;
  const sent = receipts.filter((entry) => entry.state === "sent").length;
  const anyLive = entries.some((entry) => entry.live);

  return (
    <Page>
      <PageHeader
        title="Approvals"
        meta={
          <>
            <span className="font-mono">{drafts}</span> awaiting approval ·{" "}
            <span className="font-mono">{entries.length}</span> {entries.length === 1 ? "request" : "requests"} in all
            {entries.length > 0 && !anyLive ? " · test mode, no email leaves DealProof" : null}
          </>
        }
        figures={
          entries.length > 0
            ? [
                { label: "Awaiting a person", value: waiting.length },
                { label: "Sent", value: sent },
                { label: "Suppressed", value: receipts.length - sent },
              ]
            : undefined
        }
      />

      {workspace.cases.length === 0 ? (
        <EmptyState
          size="page"
          title="No requests yet"
          actions={
            <>
              <Button asChild variant="primary" size="sm">
                <Link href="/app/discover/new">New screening</Link>
              </Button>
              <Button size="sm" onClick={openVerify}>
                Verify a company
              </Button>
            </>
          }
        >
          A request is drafted inside a case, from the claims a seller document would settle. Open
          a case first; its request then waits here for approval.
        </EmptyState>
      ) : (
        <>
          <Panel>
            <PanelHeader title="Awaiting a person" meta={waiting.length} />
            <PanelBody flush>
              {waiting.length === 0 ? (
                <EmptyState
                  title="Nothing is waiting for approval"
                  actions={
                    <Button asChild size="sm">
                      <Link href="/app/pipeline">Choose a case in Pipeline</Link>
                    </Button>
                  }
                >
                  Requests appear here when a case has open claims a seller document would settle.
                  Build one from the Request tab of an assessed case.
                </EmptyState>
              ) : (
                <Inbox entries={waiting} />
              )}
            </PanelBody>
            {waiting.length > 0 ? (
              <PanelFooter>
                Review opens the case&apos;s Request tab. Each approval is one named decision on one exact revision,
                so there is no bulk approve
              </PanelFooter>
            ) : null}
          </Panel>

          <Panel>
            <PanelHeader title="Sent / suppressed" meta={receipts.length} />
            <PanelBody flush>
              {receipts.length === 0 ? (
                <EmptyState title="No receipts yet">
                  Once an approved request is sent, its receipt is kept here. In test mode the
                  approval is recorded and the send is suppressed, and the receipt says so.
                </EmptyState>
              ) : (
                <Receipts entries={receipts} />
              )}
            </PanelBody>
          </Panel>
        </>
      )}
    </Page>
  );
}
