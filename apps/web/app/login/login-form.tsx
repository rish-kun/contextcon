"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button, Field, Input } from "@/components/ui";
import { ApiError, login } from "@/lib/api/client";

const APP_HOME = "/app";

/** Only same-site paths are followed after sign-in; anything else falls back to the app. */
function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return APP_HOME;
  }
  return value.startsWith("/login") ? APP_HOME : value;
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
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login({ email: email.trim(), password });
      router.replace(next);
    } catch (caught) {
      setError(describe(caught));
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
      <Button type="submit" variant="primary" disabled={pending} className="mt-2 self-start">
        {pending ? "Logging in" : "Log in"}
      </Button>
    </form>
  );
}
