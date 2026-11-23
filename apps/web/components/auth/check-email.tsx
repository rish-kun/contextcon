"use client";

import { useState } from "react";
import { Button } from "@/components/ui";
import { ApiError, resendVerification } from "@/lib/api/client";

type ResendState = { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; text: string };

function describe(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return "Too many links requested for this email. Wait an hour, then try again";
  }
  return "The new link was not sent. Check your connection and try again";
}

/** "Send a new link": the same answer for any email, rate limited by the API. */
export function ResendLink({ email, label = "Send a new link" }: { email: string; label?: string }) {
  const [state, setState] = useState<ResendState>({ kind: "idle" });

  async function resend() {
    setState({ kind: "sending" });
    try {
      await resendVerification(email);
      setState({ kind: "sent" });
    } catch (caught) {
      setState({ kind: "error", text: describe(caught) });
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button onClick={resend} disabled={state.kind === "sending"} className="self-start">
        {state.kind === "sending" ? "Sending" : label}
      </Button>
      <p role="status" className="text-dense text-ink-secondary">
        {state.kind === "sent"
          ? "Sent. The older link no longer works. Check your spam folder if it does not arrive in a few minutes"
          : state.kind === "error"
            ? state.text
            : null}
      </p>
    </div>
  );
}

/**
 * After sign-up: the account exists but is switched off until the email is confirmed.
 * Says so once, with where the link went and what to do if it does not arrive.
 */
export function CheckEmail({ email, onChangeEmail }: { email: string; onChangeEmail?: () => void }) {
  return (
    <div role="status" className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-medium text-ink">Check your email</h2>
        <p className="text-sm text-ink-secondary">
          We sent a link to confirm your email address. Open it to finish creating your account and
          log in.
        </p>
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 border-y border-line py-3 text-dense">
        <dt className="text-ink-muted">Sent to</dt>
        <dd className="font-mono text-xs break-all text-ink">{email}</dd>
        <dt className="text-ink-muted">The link</dt>
        <dd className="text-ink">Works once and expires after 24 hours</dd>
        <dt className="text-ink-muted">Already registered?</dt>
        <dd className="text-ink">The email tells you how to log in instead. Nothing was changed</dd>
      </dl>
      <ResendLink email={email} />
      {onChangeEmail ? (
        <Button variant="quiet" onClick={onChangeEmail} className="self-start">
          Use a different email
        </Button>
      ) : null}
    </div>
  );
}
