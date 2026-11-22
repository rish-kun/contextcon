"use client";

import { useEffect, useState } from "react";
import {
  approveMessage,
  createMessage,
  editMessage,
  getMessage,
  getSendSummary,
  isFixtureMode,
  reconcileMessage,
  sendMessage,
  type MessageOut,
  type RequestListOut,
  type SendOut,
  type SendSummaryOut,
} from "@/lib/api/client";
import { formatDateTime, plural } from "@/lib/format";
import { useSound } from "@/lib/sound";
import type { RequestedDocument, SellerRequest } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useSessionUser } from "@/components/app-shell";
import { ApprovalReceipt, ApprovalSteps, TestModeBanner } from "@/components/dealproof/approval-block";
import { HatchedBlock } from "@/components/dealproof/blocks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";

type Draft = { recipient: string; subject: string; body: string };
type Busy = "saving" | "approving" | "sending" | "reconciling" | null;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Fixture mode answers every write with a canned message. Keep what the reader typed on
 * top of it, so the flow reads the way it will against the real service.
 */
function withTyped(message: MessageOut, typed: Draft): MessageOut {
  if (!isFixtureMode) return message;
  const current = { ...message.current_revision, ...typed };
  return {
    ...message,
    current_revision: current,
    approval: message.approval ? { ...message.approval, revision_id: current.id } : null,
    revisions: message.revisions.map((revision) => (revision.id === current.id ? current : revision)),
  };
}

function revisionOf(message: MessageOut | null, list: RequestListOut): Draft {
  return message
    ? {
        recipient: message.current_revision.recipient,
        subject: message.current_revision.subject,
        body: message.current_revision.body,
      }
    : { recipient: "", subject: list.draft.subject, body: list.draft.body };
}

function SendSummary({ summary }: { summary: SendSummaryOut }) {
  const parts = [
    `${summary.sent} sent`,
    `${summary.suppressed_test_mode} suppressed in test mode`,
    `${summary.failed} failed`,
    summary.sending > 0 ? `${summary.sending} sending` : null,
    summary.unknown > 0 ? `${summary.unknown} unknown` : null,
  ].filter(Boolean);
  return (
    <p className="font-mono text-2xs text-ink-secondary">
      Sends from this case · {parts.join(" · ")}
    </p>
  );
}

/**
 * The seller email, from draft to receipt.
 *
 * Every edit is saved as a new, immutable revision. A named, signed-in person approves
 * one exact revision; editing after that clears the approval. Sending happens once, behind
 * the one confirmation dialog in the product, and the outcome is shown as what really
 * happened: sent, suppressed in test mode, failed, or not yet known.
 */
export function RequestApproval({
  caseId,
  list,
  documents,
  initialMessage,
  testMode,
}: {
  caseId: string;
  list: RequestListOut;
  /** The requested documents, each with the claim it would settle. */
  documents: RequestedDocument[];
  initialMessage: MessageOut | null;
  /** True while email sending is switched off. */
  testMode: boolean;
}) {
  const { playCue } = useSound();
  /** The named person an approval is recorded against. The shell renders only when signed in. */
  const user = useSessionUser();
  const [message, setMessage] = useState(initialMessage);
  const [draft, setDraft] = useState<Draft>(() => revisionOf(initialMessage, list));
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  /** After a failed send: the form opens again, and sending needs a new approval. */
  const [retrying, setRetrying] = useState(false);
  const [summary, setSummary] = useState<SendSummaryOut | null>(null);

  const sendStatus = message?.send?.status ?? null;
  const status = busy === "sending" ? "sending" : (sendStatus ?? message?.status ?? "draft");
  const composing = status === "draft" || status === "approved" || (status === "failed" && retrying);
  const approved = status === "approved" && Boolean(message?.approval);

  const saved = revisionOf(message, list);
  const dirty =
    !message ||
    draft.recipient.trim() !== saved.recipient ||
    draft.subject !== saved.subject ||
    draft.body !== saved.body;
  const recipient = draft.recipient.trim();
  const recipientError =
    recipient.length === 0
      ? "Enter the recipient's email address before approving."
      : EMAIL.test(recipient)
        ? null
        : "Enter a valid email address.";
  const revisionNumber = message?.current_revision.number ?? 0;

  useEffect(() => {
    let live = true;
    getSendSummary(caseId)
      .then((next) => live && setSummary(next))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [caseId, sendStatus]);

  const run = async (kind: Exclude<Busy, null>, action: () => Promise<void>, failure: string) => {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch {
      setError(failure);
    } finally {
      setBusy(null);
    }
  };

  const save = () =>
    run(
      "saving",
      async () => {
        const typed = { ...draft, recipient };
        const next = message
          ? await editMessage(caseId, message.id, {
              ...typed,
              base_revision_id: message.current_revision.id,
            })
          : await createMessage(caseId, typed);
        setMessage(withTyped(next, typed));
        setDraft(typed);
        setRetrying(false);
      },
      "The revision was not saved. Nothing changed. Try again.",
    );

  const approve = () =>
    run(
      "approving",
      async () => {
        if (!message) return;
        const next = await approveMessage(caseId, message.id, message.current_revision.id);
        setMessage(withTyped(next, saved));
      },
      "The approval was not recorded. Try again.",
    );

  const settle = (send: SendOut) => {
    setMessage((current) => (current ? { ...current, status: send.status, send } : current));
    // Sound is opt-in and never the only signal: the receipt below is the record.
    if (send.status === "sent") playCue("request_sent");
    else if (send.status === "suppressed_test_mode") playCue("run_finished");
    else if (send.status === "failed") playCue("error");
  };

  const send = async () => {
    if (!message) return;
    setConfirming(false);
    setBusy("sending");
    setError(null);
    try {
      settle(await sendMessage(caseId, message.id));
    } catch {
      // The request may have been accepted before the answer was lost. Ask what is on record.
      try {
        setMessage(await getMessage(caseId, message.id));
      } catch {
        setError(
          "The send result could not be confirmed. Nothing is sent again from here. Reload to see what is on record.",
        );
      }
    } finally {
      setBusy(null);
    }
  };

  const reconcile = () =>
    run(
      "reconciling",
      async () => {
        if (message) settle(await reconcileMessage(caseId, message.id));
      },
      "The mail provider could not be reached. The result is still unknown.",
    );

  const receipt: SellerRequest | null = message
    ? {
        id: message.id,
        status:
          status === "sent" || status === "suppressed_test_mode" || status === "failed"
            ? status
            : "approved",
        documents,
        recipient: message.current_revision.recipient || null,
        subject: message.current_revision.subject,
        body: message.current_revision.body,
        approver: message.approval ? { name: message.approval.approver_display_name } : null,
        approved_at: message.approval?.approved_at ?? null,
        sent_at: message.send?.completed_at ?? null,
        failure_reason: message.send?.error
          ? `The email provider returned an error: ${message.send.error}`
          : null,
      }
    : null;

  const blocked =
    !message || dirty
      ? "Save the revision first. An approval covers one exact revision."
      : recipientError;

  return (
    <section aria-label="Message to seller" className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h3 className="flex items-center gap-2 text-sm font-medium text-ink">
          Message
          {revisionNumber > 0 ? <Badge variant="mono">revision {revisionNumber}</Badge> : null}
        </h3>
        <ApprovalSteps
          status={
            composing
              ? approved && !dirty
                ? "approved"
                : "draft"
              : status === "sending" || status === "unknown"
                ? "sent"
                : (receipt?.status ?? "draft")
          }
          testMode={testMode}
          lastLabel={status === "sending" ? "Sending" : status === "unknown" ? "Unknown" : undefined}
        />
      </header>

      {testMode && composing ? <TestModeBanner /> : null}

      {composing ? (
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-5">
          {status === "failed" ? (
            <p className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink">
              The last send failed and nothing was retried. Save a new revision and approve it to
              send again.
            </p>
          ) : (
            <p className="text-xs text-ink-muted">Drafted by DealProof, edit before approving</p>
          )}

          <Field
            label="To"
            hint="Typed by you. DealProof does not suggest or collect personal contact details"
            error={recipient.length > 0 && recipientError ? recipientError : undefined}
          >
            {(control) => (
              <Input
                {...control}
                type="email"
                autoComplete="off"
                placeholder="Recipient email address, typed by you"
                value={draft.recipient}
                onChange={(event) => setDraft({ ...draft, recipient: event.target.value })}
              />
            )}
          </Field>
          <Field label="Subject">
            {(control) => (
              <Input
                {...control}
                value={draft.subject}
                onChange={(event) => setDraft({ ...draft, subject: event.target.value })}
              />
            )}
          </Field>
          <Field label="Message">
            {(control) => (
              <Textarea
                {...control}
                rows={14}
                value={draft.body}
                onChange={(event) => setDraft({ ...draft, body: event.target.value })}
              />
            )}
          </Field>

          {approved && dirty ? (
            <p
              role="status"
              className="rounded-md border border-partial-line bg-partial-tint px-3 py-2 text-dense text-partial"
            >
              <span className="font-medium">This edit needs a new approval. </span>
              The approval covers revision {revisionNumber} exactly as it was. Saving creates
              revision {revisionNumber + 1} and clears it.
            </p>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-ink-secondary">
              {!message
                ? "Not saved yet. Saving creates revision 1"
                : dirty
                  ? `Unsaved changes. Saving creates revision ${revisionNumber + 1}`
                  : `Revision ${revisionNumber} saved ${formatDateTime(message.current_revision.created_at) ?? ""}`}
            </p>
            <Button
              onClick={save}
              disabled={!dirty || busy !== null || !draft.subject.trim() || !draft.body.trim()}
            >
              {busy === "saving" ? "Saving" : message ? "Save as new revision" : "Save revision"}
            </Button>
          </div>

          <footer className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-col gap-1 text-dense">
              <p className="text-ink">
                <span className="text-ink-muted">Approver </span>
                {user.display_name} (signed in)
              </p>
              {approved && message?.approval ? (
                <p className={cn("text-ink", dirty && "text-ink-secondary line-through")}>
                  Approved by {message.approval.approver_display_name}
                  <span className="font-mono text-xs">
                    {" · "}
                    {formatDateTime(message.approval.approved_at)} · revision {revisionNumber}
                  </span>
                </p>
              ) : null}
              <p className="text-xs text-ink-secondary">
                {testMode
                  ? "Email sending is off. Sending records the outcome and nothing leaves"
                  : "This sends one email. It cannot be sent again from this case"}
              </p>
            </div>

            <div className="flex flex-col gap-1 sm:items-end">
              {approved ? (
                <Dialog open={confirming} onOpenChange={setConfirming}>
                  <DialogTrigger asChild>
                    <Button variant="primary" disabled={dirty || busy !== null}>
                      {testMode ? "Send (test mode, nothing is sent)" : "Send once"}
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>{testMode ? "Record the send in test mode" : "Send once"}</DialogTitle>
                      <DialogDescription>
                        {testMode
                          ? `Email sending is off. Confirming records the outcome for ${saved.recipient} (${plural(documents.length, "document")}), and no email will be sent.`
                          : `One email goes to ${saved.recipient} requesting ${plural(documents.length, "document")}. Once sent, this request cannot be sent again from this case.`}
                      </DialogDescription>
                    </DialogHeader>
                    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-dense">
                      <dt className="text-ink-muted">Recipient</dt>
                      <dd className="break-all text-ink">{saved.recipient}</dd>
                      <dt className="text-ink-muted">Documents</dt>
                      <dd className="text-ink">
                        <ul className="flex flex-col gap-1">
                          {documents.map((doc) => (
                            <li key={doc.id}>{doc.name}</li>
                          ))}
                        </ul>
                      </dd>
                      <dt className="text-ink-muted">Approver</dt>
                      <dd className="text-ink">
                        {message?.approval?.approver_display_name}
                        <span className="font-mono text-xs text-ink-secondary">
                          {" · revision "}
                          {revisionNumber}
                        </span>
                      </dd>
                    </dl>
                    <DialogFooter>
                      <DialogClose asChild>
                        <Button>Go back</Button>
                      </DialogClose>
                      <Button variant="primary" onClick={send}>
                        {testMode ? "Record, nothing is sent" : "Send once"}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              ) : (
                <Button
                  variant="primary"
                  onClick={approve}
                  disabled={Boolean(blocked) || busy !== null}
                >
                  {busy === "approving"
                    ? "Recording approval"
                    : revisionNumber > 0 && !dirty
                      ? `Approve revision ${revisionNumber}`
                      : "Approve"}
                </Button>
              )}
              {approved && dirty ? (
                <p className="text-xs text-ink-secondary">Save and approve again to send</p>
              ) : !approved && blocked ? (
                <p className="max-w-xs text-xs text-ink-secondary sm:text-right">{blocked}</p>
              ) : !approved ? (
                <p className="text-xs text-ink-secondary">Approving does not send anything</p>
              ) : null}
            </div>
          </footer>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {status === "sending" ? (
            <div
              role="status"
              className="flex flex-col gap-1 rounded-md border border-line-strong bg-surface px-4 py-3 text-dense"
            >
              <p className="text-sm font-medium text-ink">Sending · waiting for the mail provider</p>
              <p className="text-ink-secondary">
                Nothing is confirmed yet. This is not shown as sent until the provider accepts it.
              </p>
            </div>
          ) : status === "unknown" ? (
            <HatchedBlock role="status" innerClassName="flex flex-col items-start gap-1 text-dense">
              <p className="text-sm font-medium">Unknown · reconciling with the mail provider</p>
              <p className="text-ink">
                The provider&apos;s answer was lost, so DealProof does not know whether the email
                left. It is not sent again. Checking asks the provider what happened to this one
                send.
              </p>
              <Button size="sm" className="mt-2" onClick={reconcile} disabled={busy !== null}>
                {busy === "reconciling" ? "Checking" : "Check with the provider"}
              </Button>
            </HatchedBlock>
          ) : receipt ? (
            <ApprovalReceipt
              request={receipt}
              messageHref="#message"
              onStartNewApproval={status === "failed" ? () => setRetrying(true) : undefined}
              className="animate-fade-in motion-reduce:animate-none"
            />
          ) : null}

          {message ? (
            <div id="message" className="scroll-mt-24 rounded-xl border border-line bg-surface">
              <dl className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-line px-5 py-3 text-dense">
                <dt className="text-ink-muted">To</dt>
                <dd className="break-all text-ink">
                  {message.current_revision.recipient || "no recipient recorded"}
                </dd>
                <dt className="text-ink-muted">Subject</dt>
                <dd className="text-ink">{message.current_revision.subject}</dd>
              </dl>
              <p className="px-5 py-4 text-sm whitespace-pre-wrap text-ink">
                {message.current_revision.body}
              </p>
              <p className="border-t border-line px-5 py-2 font-mono text-2xs text-ink-secondary">
                Revision {revisionNumber} · read-only
                {status === "sent" ? " · sent once, cannot be sent again from this case" : null}
              </p>
            </div>
          ) : null}
        </div>
      )}

      {error ? (
        <p role="alert" className="text-dense text-contradicted">
          {error}
        </p>
      ) : null}

      {message && message.revisions.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-medium text-ink-secondary">Revisions</h4>
          <ol className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface text-dense">
            {message.revisions.map((revision) => (
              <li
                key={revision.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2"
              >
                <span className="font-mono text-xs text-ink">Revision {revision.number}</span>
                <span className="font-mono text-xs text-ink-secondary">
                  {formatDateTime(revision.created_at)}
                </span>
                <span className="min-w-0 truncate text-ink-secondary">
                  {revision.recipient ? `to ${revision.recipient}` : "no recipient yet"}
                </span>
                {revision.id === message.current_revision.id ? (
                  <Badge variant="mono">current</Badge>
                ) : null}
                {revision.id === message.approval?.revision_id ? (
                  <Badge variant="outline" className="font-mono text-2xs">
                    approved
                  </Badge>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {summary ? <SendSummary summary={summary} /> : null}
    </section>
  );
}
