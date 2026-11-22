"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Field, Input, TextLink } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { signup } from "@/lib/api/org";

const MIN_PASSWORD = 10;

type Errors = Partial<Record<"name" | "email" | "password" | "organisation", string>>;

function validate(values: { name: string; email: string; password: string; organisation: string }): Errors {
  const errors: Errors = {};
  if (!values.name.trim()) errors.name = "Enter your name. Approvals are recorded against a named person";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) errors.email = "Enter a valid email address";
  if (values.password.length < MIN_PASSWORD) errors.password = `Use at least ${MIN_PASSWORD} characters`;
  if (values.organisation.trim().length < 2) errors.organisation = "Enter your organisation's name";
  return errors;
}

type Failure = { kind: "exists" } | { kind: "closed" } | { kind: "message"; text: string };

function describe(error: unknown): Failure {
  if (error instanceof ApiError) {
    if (error.status === 409) return { kind: "exists" };
    if (error.status === 403) return { kind: "closed" };
    if (error.status === 429) return { kind: "message", text: "Too many accounts created from this network. Try again later" };
    if (error.status === 503) return { kind: "message", text: "DealProof is busy. Try again in a moment" };
    return { kind: "message", text: "The account was not created. Nothing was saved. Try again" };
  }
  return { kind: "message", text: "The request did not reach DealProof. Check your connection and try again" };
}

/**
 * Test mode: the account exists, and it is switched on by a person. Said once, plainly,
 * with what happens next. No spinner, no countdown, nothing to refresh.
 */
function Registered({ email }: { email: string }) {
  return (
    <div role="status" className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-medium text-ink">You are registered</h2>
        <p className="text-sm text-ink-secondary">
          DealProof is in a test period, and accounts are switched on a few at a time. Yours will be
          enabled soon.
        </p>
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 border-y border-line py-3 text-dense">
        <dt className="text-ink-muted">Registered as</dt>
        <dd className="font-mono text-xs break-all text-ink">{email}</dd>
        <dt className="text-ink-muted">What happens next</dt>
        <dd className="text-ink">Log in with this email and your password once the account is on</dd>
        <dt className="text-ink-muted">Until then</dt>
        <dd className="text-ink">Nothing was looked up and nothing was spent</dd>
      </dl>
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link href="/showcase">See a worked case</Link>
        </Button>
        <Button asChild variant="quiet">
          <Link href="/">Back to the home page</Link>
        </Button>
      </div>
    </div>
  );
}

export function SignupForm() {
  const router = useRouter();
  const [values, setValues] = useState({ name: "", email: "", password: "", organisation: "" });
  const [honeypot, setHoneypot] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [pending, setPending] = useState(false);
  const [registered, setRegistered] = useState<string | null>(null);

  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));
  /** A field is checked when it is left, and only complains once it has been touched. */
  const check = (key: keyof Errors) => () =>
    setErrors((current) => ({ ...current, [key]: validate(values)[key] }));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setFailure(null);
    setPending(true);
    try {
      const email = values.email.trim().toLowerCase();
      const result = await signup({
        display_name: values.name.trim(),
        email,
        password: values.password,
        organisation: values.organisation.trim(),
        company_url: honeypot,
      });
      if (result.status === "pending") {
        setRegistered(email);
        return;
      }
      router.replace("/app");
    } catch (caught) {
      setFailure(describe(caught));
      setPending(false);
    }
  }

  if (registered) return <Registered email={registered} />;

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label="Your name" hint="Recorded on every request you approve" error={errors.name}>
        {(control) => (
          <Input {...control} name="name" autoComplete="name" value={values.name} onChange={set("name")} onBlur={check("name")} autoFocus />
        )}
      </Field>
      <Field label="Work email" error={errors.email}>
        {(control) => (
          <Input
            {...control}
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={values.email}
            onChange={set("email")}
            onBlur={check("email")}
          />
        )}
      </Field>
      <Field label="Password" hint={`At least ${MIN_PASSWORD} characters`} error={errors.password}>
        {(control) => (
          <div className="flex gap-2">
            <Input
              {...control}
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              value={values.password}
              onChange={set("password")}
              onBlur={check("password")}
            />
            <Button aria-pressed={showPassword} onClick={() => setShowPassword((shown) => !shown)}>
              {showPassword ? "Hide" : "Show"}
            </Button>
          </div>
        )}
      </Field>
      <Field label="Organisation" hint="This names your workspace" error={errors.organisation}>
        {(control) => (
          <Input
            {...control}
            name="organisation"
            autoComplete="organization"
            value={values.organisation}
            onChange={set("organisation")}
            onBlur={check("organisation")}
          />
        )}
      </Field>
      {/* Honeypot: off screen and out of the tab order. A person never fills it. */}
      <div aria-hidden className="absolute -left-[9999px] size-px overflow-hidden">
        <label>
          Company URL
          <input name="company_url" tabIndex={-1} autoComplete="off" value={honeypot} onChange={(event) => setHoneypot(event.target.value)} />
        </label>
      </div>

      {failure ? (
        <p role="alert" className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink">
          {failure.kind === "exists" ? (
            <>
              An account with this email already exists. <TextLink href="/login">Log in instead</TextLink>
            </>
          ) : failure.kind === "closed" ? (
            "Sign-up is closed on this deployment. Ask the person who runs DealProof for your team for an account"
          ) : (
            failure.text
          )}
        </p>
      ) : null}

      <Button type="submit" variant="primary" disabled={pending} className="mt-2 self-start">
        {pending ? "Creating account" : "Create account"}
      </Button>
    </form>
  );
}
