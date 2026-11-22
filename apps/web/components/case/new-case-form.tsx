"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  type CompanyCandidate,
  type ThesisSummary,
  addClaim,
  createCase,
  listTheses,
  lookupCompanies,
  uploadDocument,
} from "@/lib/api/client";
import { plural } from "@/lib/format";
import {
  Badge,
  Button,
  Field,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@/components/ui";
import { ConfidentialityStrip, DocumentDropzone, QueuedFile, claimLines } from "./intake";

const NO_THESIS = "none";
const caseHref = (id: string) => `/app/cases/${encodeURIComponent(id)}`;

function describe(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    if (cause.status >= 502 && cause.status <= 504) {
      return "The DealProof API did not respond. Nothing was changed";
    }
    if (typeof cause.detail === "string" && cause.detail.trim()) return cause.detail;
    return fallback;
  }
  return "The request did not reach DealProof. Check your connection and try again";
}

/**
 * Verify a company directly: name and website, and optionally what the seller has
 * already said, typed or as documents. It opens the case, attaches the claims and files
 * to it, and goes to the case, where verification is already running.
 */
export function NewCaseForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [thesis, setThesis] = useState(NO_THESIS);
  const [theses, setTheses] = useState<ThesisSummary[]>([]);
  const [claims, setClaims] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [nameError, setNameError] = useState<string | undefined>();
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; caseId?: string } | null>(null);
  // Without a website, the company is picked from a lookup first.
  const [knowsWebsite, setKnowsWebsite] = useState(false);
  const [candidates, setCandidates] = useState<CompanyCandidate[] | null>(null);
  const [looking, setLooking] = useState(false);

  async function findCompanies() {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError("Enter the company name");
      return;
    }
    setNameError(undefined);
    setError(null);
    setLooking(true);
    setCandidates(null);
    try {
      setCandidates((await lookupCompanies(trimmed)).candidates);
    } catch (cause) {
      setError({ message: describe(cause, "The lookup did not finish") });
    } finally {
      setLooking(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    // The thesis is optional, so a failed list simply leaves the field out.
    listTheses()
      .then((list) => (cancelled ? null : setTheses(list)))
      .catch(() => null);
    return () => {
      cancelled = true;
    };
  }, []);

  const lines = claimLines(claims);
  const busy = progress !== null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!knowsWebsite) {
      await findCompanies();
      return;
    }
    await open(null);
  }

  async function open(picked: CompanyCandidate | null) {
    const trimmed = picked?.name ?? name.trim();
    if (!trimmed) {
      setNameError("Enter the company name");
      return;
    }
    setNameError(undefined);
    setError(null);
    setProgress("Opening the case");

    let caseId: string | undefined;
    try {
      const created = await createCase({
        name: trimmed,
        website: picked ? picked.domain : website.trim() || null,
        crustdata_id: picked?.crustdata_id ?? null,
        thesis_id: thesis === NO_THESIS ? null : thesis,
      });
      caseId = created.id;
      for (const [index, line] of lines.entries()) {
        setProgress(`Adding claim ${index + 1} of ${lines.length}`);
        await addClaim(created.id, line);
      }
      for (const file of files) {
        setProgress(`Uploading ${file.name}`);
        await uploadDocument(created.id, file, "seller_deck");
      }
      router.push(caseHref(created.id));
    } catch (cause) {
      setProgress(null);
      setError({
        message: caseId
          ? `The case was opened, but a later step did not finish: ${describe(cause, "the request failed")}`
          : describe(cause, "The case could not be opened"),
        caseId,
      });
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-8">
      <fieldset disabled={busy} className="flex flex-col gap-4">
        <legend className="pb-4 text-sm font-medium text-ink">The company</legend>
        <Field label="Company name" error={nameError}>
          {(control) => (
            <Input
              {...control}
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Meridian Warehousing Pvt Ltd"
              autoComplete="off"
              autoFocus
              required
            />
          )}
        </Field>
        {knowsWebsite ? (
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
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          {knowsWebsite ? null : (
            <Button type="button" variant="primary" onClick={findCompanies} disabled={looking}>
              {looking ? "Finding companies" : "Find companies"}
            </Button>
          )}
          <Button
            type="button"
            variant="quiet"
            onClick={() => {
              setKnowsWebsite((v) => !v);
              setCandidates(null);
            }}
          >
            {knowsWebsite ? "Find the company by name instead" : "I know the website"}
          </Button>
        </div>
        {!knowsWebsite && candidates !== null ? (
          <CandidateList
            candidates={candidates}
            onPick={(c) => void open(c)}
            onNone={() => {
              setKnowsWebsite(true);
              setCandidates(null);
            }}
          />
        ) : null}
        {theses.length > 0 ? (
          <Field
            label="Thesis (optional)"
            hint="With a thesis, fit is scored against its criteria. Without one, fit is not scored"
          >
            {(control) => (
              <Select value={thesis} onValueChange={setThesis}>
                <SelectTrigger {...control}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_THESIS}>No thesis</SelectItem>
                  {theses.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.text.length > 72 ? `${item.text.slice(0, 72)}…` : item.text}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
        ) : null}
      </fieldset>

      <fieldset disabled={busy} className="flex flex-col gap-4 border-t border-line pt-6">
        <legend className="sr-only">What the seller said</legend>
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium text-ink">What the seller said, if you have it</p>
          <p className="text-xs text-ink-secondary">
            Both are optional. Without them the case still confirms identity and builds the
            public profile, and you can add claims later
          </p>
        </div>
        <Field
          label="Individual claims (optional)"
          hint={
            lines.length > 0
              ? `${plural(lines.length, "claim")}, recorded as typed by you`
              : "One claim per line, in the seller's words"
          }
        >
          {(control) => (
            <Textarea
              {...control}
              name="claims"
              rows={4}
              value={claims}
              onChange={(event) => setClaims(event.target.value)}
              placeholder="Type one claim per line"
            />
          )}
        </Field>
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-ink">Seller documents (optional)</p>
          <DocumentDropzone
            disabled={busy}
            onFiles={(added) =>
              setFiles((current) => [
                ...current,
                ...added.filter((file) => !current.some((c) => c.name === file.name && c.size === file.size)),
              ])
            }
          />
          {files.length > 0 ? (
            <ul className="flex flex-col gap-1" aria-label="Files to upload">
              {files.map((file) => (
                <QueuedFile
                  key={`${file.name}-${file.size}`}
                  file={file}
                  onRemove={busy ? undefined : () => setFiles((current) => current.filter((c) => c !== file))}
                />
              ))}
            </ul>
          ) : null}
          <ConfidentialityStrip />
        </div>
      </fieldset>

      {error ? (
        <p role="alert" className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-dense text-ink">
          {error.message}
          {error.caseId ? (
            <>
              {" · "}
              <Link href={caseHref(error.caseId)} className="text-accent underline underline-offset-2">
                Open the case
              </Link>
            </>
          ) : null}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line pt-6">
        {knowsWebsite || busy ? (
          <Button type="submit" variant="primary" className="h-11 md:h-9" disabled={busy}>
            {busy ? progress : "Start verification"}
          </Button>
        ) : null}
        <Button asChild variant="quiet">
          <Link href="/app">Cancel</Link>
        </Button>
        <p className="text-xs text-ink-muted">Lookups count against the case&rsquo;s credit budget</p>
      </div>
      <p role="status" className="sr-only">
        {progress}
      </p>
    </form>
  );
}

function CandidateList({
  candidates,
  onPick,
  onNone,
}: {
  candidates: CompanyCandidate[];
  onPick: (candidate: CompanyCandidate) => void;
  onNone: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {candidates.length === 0 ? (
        <p className="text-dense text-ink-secondary">No companies match that name</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Matching companies">
          {candidates.map((c) => {
            const hq = [c.hq_city, c.hq_country].filter(Boolean).join(", ");
            const facts = [
              hq,
              c.founded_year ? `Founded ${c.founded_year}` : null,
              c.headcount ? `${c.headcount.toLocaleString()} people` : null,
              c.industry,
            ].filter(Boolean);
            return (
              <li
                key={c.crustdata_id}
                className="flex flex-col gap-2 rounded-md border border-line px-3 py-3 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
                    {c.name}
                    {c.domain ? <span className="text-xs font-normal text-ink-muted">{c.domain}</span> : null}
                    {c.listed ? <Badge>Listed</Badge> : null}
                  </p>
                  {c.description ? <p className="text-dense text-ink-secondary">{c.description}</p> : null}
                  {facts.length > 0 ? <p className="text-xs text-ink-muted">{facts.join(" · ")}</p> : null}
                </div>
                <Button type="button" variant="secondary" className="shrink-0" onClick={() => onPick(c)}>
                  Verify this company
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <Button type="button" variant="quiet" className="self-start" onClick={onNone}>
        None of these — enter website instead
      </Button>
    </div>
  );
}
