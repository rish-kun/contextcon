"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, TextLink } from "@/components/ui";
import { ApiError, verifyEmail } from "@/lib/api/client";

const APP_HOME = "/app";

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 400 || error.status === 422) {
      return "This link has expired or has already been used. Log in, or ask for a new link from the login page";
    }
    return "DealProof could not confirm your email just now. The link still works. Try again in a moment";
  }
  return "The request did not reach DealProof. Check your connection and try again";
}

export function VerifyForm({ token }: { token: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!token) {
    return (
      <p role="alert" className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink">
        This link is incomplete. Open the link from the email again, or copy the whole address into
        the browser
      </p>
    );
  }

  async function confirm() {
    setError(null);
    setPending(true);
    try {
      await verifyEmail(token);
      router.replace(APP_HOME);
    } catch (caught) {
      setError(describe(caught));
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div role="alert" className="flex flex-col gap-3 rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink">
          <p>{error}</p>
          <TextLink href="/login" className="self-start">
            Go to the login page
          </TextLink>
        </div>
      ) : null}
      <Button variant="primary" onClick={confirm} disabled={pending} className="self-start">
        {pending ? "Confirming" : "Confirm email and log in"}
      </Button>
    </div>
  );
}
