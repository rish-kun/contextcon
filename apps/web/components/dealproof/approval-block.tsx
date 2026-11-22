"use client";

import { Check, MailX, OctagonX } from "lucide-react";
import { useState } from "react";
import { formatDateTime, plural } from "@/lib/format";
import { REQUEST_STATUS_LABEL } from "@/lib/labels";
import type { NamedUser, RequestStatus, SellerRequest } from "@/lib/types";
import { cn } from "@/lib/utils";
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
import { Icon } from "@/components/ui/icon";
import { Field, Input, Textarea } from "@/components/ui/input";
import { HatchedBlock } from "./blocks";

/** What the approver typed or edited before approving. */
export interface ApprovalDraft {
  recipient: string;
  subject: string;
  body: string;
}

/**
 * Shown at the top of the Request tab while EMAIL_SEND_ENABLED is false. Hatched and
 * dashed, so it reads as "not live" without relying on its colour.
 */
export function TestModeBanner({ className }: { className?: string }) {
  return (
    <HatchedBlock
      role="note"
      className={cn("border-test-mode", className)}
      innerClassName="bg-test-mode-tint text-test-mode text-dense"
    >
      <span className="font-medium">Test mode. </span>
      Email sending is off. Approving records the approval. Nothing will leave.
    </HatchedBlock>
  );
}

/** Draft → Approved → Sent. The last step is named for what really happened. */
export function ApprovalSteps({
  status,
  testMode,
  className,
}: {
  status: RequestStatus;
  testMode: boolean;
  className?: string;
}) {
  const last =
    status === "failed"
      ? "Failed"
      : status === "suppressed_test_mode" || (testMode && status !== "sent")
        ? "Suppressed"
        : "Sent";
  const reached = status === "draft" ? 0 : status === "approved" ? 1 : 2;
  const steps = ["Draft", "Approved", last];

  return (
    <ol className={cn("flex flex-wrap items-center gap-2 text-xs", className)} aria-label="Request progress">
      {steps.map((step, index) => (
        <li key={step} className="inline-flex items-center gap-2">
          {index > 0 ? (
            <span aria-hidden className="text-ink-muted">
              →
            </span>
          ) : null}
          <span
            aria-current={index === reached ? "step" : undefined}
            className={cn(
              "inline-flex items-center gap-1",
              index === reached
                ? "font-medium text-ink underline decoration-2 underline-offset-4"
                : index < reached
                  ? "text-ink-secondary"
                  : "text-ink-muted",
            )}
          >
            {index < reached ? <Icon icon={Check} size={14} /> : null}
            {step}
            {index < reached ? <span className="sr-only"> (done)</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * The permanent, read-only record of what happened to a request.
 * Sent once: a plain receipt. Suppressed in test mode: hatched and dashed, a struck
 * envelope, never a check mark, never green, never the word "Sent" on its own.
 * Failed: says so, gives the provider's reason, and does not retry.
 */
export function ApprovalReceipt({
  request,
  messageHref,
  onStartNewApproval,
  className,
}: {
  request: SellerRequest;
  /** Link to the message as it was approved. */
  messageHref?: string;
  /** For a failed send. Retrying is a new, explicit approval. */
  onStartNewApproval?: () => void;
  className?: string;
}) {
  const approvedBy = request.approver ? (
    <>
      Approved by {request.approver.name}
      {request.approved_at ? (
        <span className="font-mono text-xs"> · {formatDateTime(request.approved_at)}</span>
      ) : null}
    </>
  ) : (
    "Approver not recorded"
  );
  const details = (
    <p className="text-ink-secondary">
      To {request.recipient ?? "no recipient recorded"} ·{" "}
      {plural(request.documents.length, "document")} requested
      {messageHref ? (
        <>
          {" · "}
          <a
            href={messageHref}
            className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            View message
          </a>
        </>
      ) : null}
    </p>
  );

  if (request.status === "suppressed_test_mode") {
    return (
      <HatchedBlock
        role="status"
        className={className}
        innerClassName="flex flex-col gap-1 text-dense"
      >
        <p className="flex items-center gap-2 text-sm font-medium text-not-checked">
          <Icon icon={MailX} />
          {REQUEST_STATUS_LABEL.suppressed_test_mode}
        </p>
        <p className="text-ink">{approvedBy}</p>
        {details}
      </HatchedBlock>
    );
  }

  if (request.status === "failed") {
    return (
      <div
        role="alert"
        className={cn(
          "flex flex-col items-start gap-1 rounded-md border border-contradicted bg-contradicted-tint px-4 py-3 text-dense",
          className,
        )}
      >
        <p className="flex items-center gap-2 text-sm font-medium text-contradicted">
          <Icon icon={OctagonX} />
          {REQUEST_STATUS_LABEL.failed}
        </p>
        <p className="text-ink">
          {request.failure_reason ?? "The mail provider gave no reason"}
        </p>
        <p className="text-ink">{approvedBy}</p>
        <p className="text-ink-secondary">
          Nothing was retried. Sending again needs a new approval.
        </p>
        {onStartNewApproval ? (
          <Button size="sm" className="mt-2" onClick={onStartNewApproval}>
            Start a new approval
          </Button>
        ) : null}
      </div>
    );
  }

  if (request.status === "sent") {
    return (
      <div
        role="status"
        className={cn(
          "flex flex-col gap-1 rounded-md border border-line-strong bg-surface px-4 py-3 text-dense",
          className,
        )}
      >
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Icon icon={Check} />
          {REQUEST_STATUS_LABEL.sent}
        </p>
        <p className="text-ink">{approvedBy}</p>
        {details}
      </div>
    );
  }

  // Approved and waiting on the mail provider. Nothing has been confirmed yet.
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col gap-1 rounded-md border border-line-strong bg-surface px-4 py-3 text-dense",
        className,
      )}
    >
      <p className="text-sm font-medium text-ink">Approved · waiting for the send result</p>
      <p className="text-ink">{approvedBy}</p>
      {details}
    </div>
  );
}

/**
 * The request to the seller, from draft to receipt.
 *
 * Draft: the documents, each tied to the claim it would settle, and an editable message.
 * The recipient is empty until a person types it. Approve: enabled only for a signed-in,
 * named user with a recipient entered; it opens the one dialog in the product, which
 * restates the recipient, the documents and the approver. After: the button is removed,
 * not disabled, and a receipt takes its place.
 */
export function ApprovalBlock({
  request,
  testMode,
  signedInUser,
  onApprove,
  onStartNewApproval,
  messageHref,
  className,
}: {
  request: SellerRequest;
  /** True while EMAIL_SEND_ENABLED is false. */
  testMode: boolean;
  /** The named person who would approve. Null when nobody is signed in. */
  signedInUser: NamedUser | null;
  onApprove?: (draft: ApprovalDraft) => void;
  onStartNewApproval?: () => void;
  messageHref?: string;
  className?: string;
}) {
  const [recipient, setRecipient] = useState(request.recipient ?? "");
  const [subject, setSubject] = useState(request.subject);
  const [body, setBody] = useState(request.body);
  const [open, setOpen] = useState(false);

  const isDraft = request.status === "draft";
  const hasRecipient = recipient.trim().length > 0;
  const canApprove = Boolean(signedInUser) && hasRecipient;
  const blockedBecause = !signedInUser
    ? "Sign in to approve. An approval needs a named person"
    : !hasRecipient
      ? "Enter the seller's address to approve"
      : null;
  const documentCount = plural(request.documents.length, "document");

  return (
    <section
      aria-label="Request to seller"
      className={cn("flex flex-col gap-4 rounded-xl border border-line bg-surface p-5", className)}
    >
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h3 className="flex items-center gap-2 text-xl font-medium text-ink">
          Request to seller
          {testMode ? <Badge variant="test-mode">Test mode</Badge> : null}
        </h3>
        <ApprovalSteps status={request.status} testMode={testMode} />
      </header>

      {testMode && isDraft ? <TestModeBanner /> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex flex-col gap-2">
          <h4 className="text-sm font-medium text-ink">
            Documents requested{" "}
            <span className="font-mono text-xs font-normal text-ink-muted">
              {request.documents.length}
            </span>
          </h4>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line text-dense">
            {request.documents.map((doc) => (
              <li key={doc.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="text-ink">{doc.name}</span>
                <span className="shrink-0 font-mono text-xs text-ink-secondary">
                  settles claim {doc.claim_number}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {isDraft ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h4 className="text-sm font-medium text-ink">Message</h4>
              <p className="text-xs text-ink-muted">Drafted by DealProof, edit before approving</p>
            </div>
            <Field label="To" hint="Typed by you. DealProof does not suggest an address">
              {(control) => (
                <Input
                  {...control}
                  type="email"
                  autoComplete="off"
                  value={recipient}
                  onChange={(event) => setRecipient(event.target.value)}
                />
              )}
            </Field>
            <Field label="Subject">
              {(control) => (
                <Input
                  {...control}
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                />
              )}
            </Field>
            <Field label="Message">
              {(control) => (
                <Textarea
                  {...control}
                  rows={6}
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                />
              )}
            </Field>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-medium text-ink">Outcome</h4>
            <ApprovalReceipt
              request={request}
              messageHref={messageHref}
              onStartNewApproval={onStartNewApproval}
              className="animate-fade-in motion-reduce:animate-none"
            />
          </div>
        )}
      </div>

      {isDraft ? (
        <footer className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1 text-dense">
            <p className="text-ink">
              <span className="text-ink-muted">Approver </span>
              {signedInUser ? `${signedInUser.name} (signed in)` : "nobody is signed in"}
            </p>
            <p className="text-xs text-ink-secondary">
              {testMode
                ? "This records the approval. No email leaves while test mode is on"
                : "This sends one email. It cannot be sent again from this case"}
            </p>
          </div>
          <div className="flex flex-col gap-1 sm:items-end">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button variant="primary" disabled={!canApprove}>
                  {testMode ? "Approve (test mode, nothing is sent)" : "Approve and send once"}
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>
                    {testMode ? "Record this approval" : "Send this request once"}
                  </DialogTitle>
                  <DialogDescription>
                    {testMode
                      ? "Test mode is on. The approval is recorded and no email leaves."
                      : "One email goes to the seller. It cannot be sent again from this case."}
                  </DialogDescription>
                </DialogHeader>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-dense">
                  <dt className="text-ink-muted">To</dt>
                  <dd className="break-all text-ink">{recipient}</dd>
                  <dt className="text-ink-muted">Requesting</dt>
                  <dd className="text-ink">
                    <ul className="flex flex-col gap-1">
                      {request.documents.map((doc) => (
                        <li key={doc.id}>{doc.name}</li>
                      ))}
                    </ul>
                  </dd>
                  <dt className="text-ink-muted">Approver</dt>
                  <dd className="text-ink">{signedInUser?.name}</dd>
                </dl>
                <DialogFooter>
                  <DialogClose asChild>
                    <Button>Go back</Button>
                  </DialogClose>
                  <Button
                    variant="primary"
                    onClick={() => {
                      setOpen(false);
                      onApprove?.({ recipient: recipient.trim(), subject, body });
                    }}
                  >
                    {testMode ? "Record approval" : "Send once"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            {blockedBecause ? (
              <p className="text-xs text-ink-secondary">{blockedBecause}</p>
            ) : (
              <p className="text-xs text-ink-secondary">Requests {documentCount}</p>
            )}
          </div>
        </footer>
      ) : null}
    </section>
  );
}
