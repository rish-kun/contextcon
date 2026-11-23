"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ResendLink } from "@/components/auth/check-email";
import { Button, Field, Input } from "@/components/ui";
import { ApiError, isEmailNotVerified, login } from "@/lib/api/client";
import { isAuthPage } from "@/lib/api/proxy-rules";

const APP_HOME = "/app";

/** A placeholder origin: a `next` value that resolves anywhere else is not a same-site path. */
const BASE = "http://dealproof.invalid";

/**
 * Only same-site paths are followed after sign-in; anything else falls back to the app.
 * The value is resolved with the URL parser, which is what the browser would do, so
 * forms such as `/\t/host` or `/\\host` cannot slip past a prefix check.
 */
function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || /[\u0000-\u001f\u007f\\]/.test(value)) return APP_HOME;
  let url: URL;
  try {
    url = new URL(value, BASE);
  } catch {
    return APP_HOME;
  }
  if (url.origin !== BASE) return APP_HOME;
  const path = url.pathname + url.search + url.hash;
  return path.startsWith("//") || isAuthPage(url.pathname) ? APP_HOME : path;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return "That email and password do not match an account";
    }
    if (error.status === 422) return "Enter a valid email address and your password";
    if (error.status === 429) return "Too many attempts. Try again later";
    return "DealProof could not check your details just now. Nothing is wrong with your account. Try again in a moment";
  }
  return "The request did not reach DealProof. Check your connection and try again";
}

export function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  /** The email whose password matched but which is not confirmed yet. */
  const [unverified, setUnverified] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setUnverified(null);
    setPending(true);
    try {
      await login({ email: email.trim(), password });
      router.replace(next);
    } catch (caught) {
      if (isEmailNotVerified(caught)) setUnverified(email.trim());
      else setError(describe(caught));
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Email">
        {(control) => (
          <Input
            {...control}
            name="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoFocus
          />
        )}
      </Field>
      <Field label="Password">
        {(control) => (
          <Input
            {...control}
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        )}
      </Field>
      {error ? (
        <p
          role="alert"
          className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink"
        >
          {error}
        </p>
      ) : null}
      {unverified ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-md border border-line-strong bg-surface-raised px-3 py-3 text-dense text-ink"
        >
          <p>
            Confirm your email address before you log in. Open the link we sent to{" "}
            <span className="font-mono text-xs break-all">{unverified}</span> when you signed up.
          </p>
          <ResendLink email={unverified} label="Send a new link" />
        </div>
      ) : null}
      <Button type="submit" variant="primary" disabled={pending} className="mt-2 self-start">
        {pending ? "Logging in" : "Log in"}
      </Button>
    </form>
  );
}
