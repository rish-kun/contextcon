"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Field, Input } from "@/components/ui";
import { ApiError, createCase } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { caseHref } from "./nav";

/** A calm sentence for a failed request. The API's own words are used when it gave any. */
export function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 502 || error.status === 503 || error.status === 504) {
      return "The DealProof API did not respond. Nothing was changed";
    }
    if (typeof error.detail === "string" && error.detail.trim()) return error.detail;
    return fallback;
  }
  return "The request did not reach DealProof. Check your connection and try again";
}

/**
 * Name and website for a company the analyst already has in mind. Posting opens a case
 * (`POST /cases`), which starts verification, and then goes to that case.
 */
export function VerifyCompanyForm({
  autoFocus = false,
  onCreated,
  className,
}: {
  autoFocus?: boolean;
  onCreated?: () => void;
  className?: string;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [nameError, setNameError] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setNameError("Enter the company name");
      return;
    }
    setNameError(undefined);
    setError(null);
    setPending(true);
    try {
      const created = await createCase({
        name: trimmedName,
        website: website.trim() || null,
      });
      onCreated?.();
      router.push(caseHref(created.id));
    } catch (caught) {
      setError(describeError(caught, "The case could not be opened"));
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className={cn("flex flex-col gap-4", className)}>
      <Field label="Company name" error={nameError}>
        {(control) => (
          <Input
            {...control}
            name="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Meridian Warehousing Pvt Ltd"
            autoComplete="off"
            autoFocus={autoFocus}
            required
          />
        )}
      </Field>
      <Field label="Website" hint="Used to match the company by its domain, not by its name">
        {(control) => (
          <Input
            {...control}
            name="website"
            type="url"
            inputMode="url"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
            placeholder="https://example.in"
            autoComplete="off"
          />
        )}
      </Field>
      {error ? (
        <p role="alert" className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button type="submit" variant="primary" disabled={pending}>
          {pending ? "Opening case" : "Start verification"}
        </Button>
        <p className="text-xs text-ink-muted">Lookups count against the case&rsquo;s credit budget</p>
      </div>
    </form>
  );
}
