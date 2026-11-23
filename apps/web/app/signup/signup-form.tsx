"use client";

import { useState } from "react";
import { CheckEmail } from "@/components/auth/check-email";
import { Button, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { signup } from "@/lib/api/org";

const MIN_PASSWORD = 10;

type Errors = Partial<Record<"name" | "email" | "password" | "organisation", string>>;

function validate(values: { name: string; email: string; password: string; organisation: string }): Errors {
  const errors: Errors = {};
  if (!values.name.trim()) errors.name = "Enter your name. Approvals are recorded against a named person";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) errors.email = "Enter a valid email address";
  if (values.password.length < MIN_PASSWORD) errors.password = `Use at least ${MIN_PASSWORD} characters`;
  if (values.organisation.trim().length > 200) errors.organisation = "Use at most 200 characters";
  return errors;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Sign-up is closed on this deployment. Ask the person who runs DealProof for your team for an account";
    }
    if (error.status === 422 && typeof error.detail === "string") return error.detail;
    if (error.status === 429) return "Too many sign-ups from this network. Try again in an hour";
    if (error.status === 503) return "DealProof is busy. Try again in a moment";
    return "The account was not created. Nothing was saved. Try again";
  }
  return "The request did not reach DealProof. Check your connection and try again";
}

export function SignupForm() {
  const [values, setValues] = useState({ name: "", email: "", password: "", organisation: "" });
  const [honeypot, setHoneypot] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

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
      const result = await signup({
        display_name: values.name.trim(),
        email: values.email.trim().toLowerCase(),
        password: values.password,
        organisation: values.organisation.trim(),
        company_url: honeypot,
      });
      setSentTo(result.email);
    } catch (caught) {
      setFailure(describe(caught));
    } finally {
      setPending(false);
    }
  }

  if (sentTo) {
    return (
      <CheckEmail
        email={sentTo}
        onChangeEmail={() => {
          setSentTo(null);
          setValues((current) => ({ ...current, password: "" }));
        }}
      />
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label="Your name" hint="Recorded on every request you approve" error={errors.name}>
        {(control) => (
          <Input {...control} name="name" autoComplete="name" value={values.name} onChange={set("name")} onBlur={check("name")} autoFocus />
        )}
      </Field>
      <Field label="Work email" hint="We send a link to confirm it" error={errors.email}>
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
      <Field label="Organisation" hint="Optional. Names your workspace" error={errors.organisation}>
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
          {failure}
        </p>
      ) : null}

      <Button type="submit" variant="primary" disabled={pending} className="mt-2 self-start">
        {pending ? "Creating account" : "Create account"}
      </Button>
    </form>
  );
}
