"use client";

import { useId, useState } from "react";
import { createThesis, type ThesisOut } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { errorText } from "./adapt";
import { ErrorNotice } from "./notice";

/** The PRD's example. Placeholder text only: the field always starts empty. */
const PLACEHOLDER =
  "Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion";

const EXAMPLES = [
  "Regional 3PL operators",
  "Cold chain technology",
  "Warehousing software in India",
] as const;

/**
 * Step 1: the thesis in plain words. Submitting turns it into criteria; nothing is
 * searched and nothing is spent until the criteria have been reviewed.
 */
export function ThesisForm({
  initialText = "",
  onExtracted,
}: {
  initialText?: string;
  onExtracted: (thesis: ThesisOut) => void;
}) {
  const id = useId();
  const [text, setText] = useState(initialText);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const trimmed = text.trim();
  const empty = touched && trimmed.length === 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (trimmed.length === 0 || pending) return;
    setPending(true);
    setError(null);
    try {
      onExtracted(await createThesis(trimmed));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-busy={pending}
      className="flex max-w-3xl flex-col gap-4 rounded-lg border border-line bg-surface p-4 shadow-xs sm:p-6"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-xl font-medium text-ink">
          Describe what you are looking for
        </label>
        <p id={`${id}-hint`} className="text-sm text-ink-secondary">
          Write it the way you would say it. DealProof separates the must-haves from the
          preferences, and you edit them before anything is searched.
        </p>
      </div>

      <Textarea
        id={id}
        rows={5}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={PLACEHOLDER}
        aria-describedby={empty ? `${id}-hint ${id}-error` : `${id}-hint`}
        aria-invalid={empty ? true : undefined}
        disabled={pending}
        className="min-h-32 text-base"
      />
      {empty ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-contradicted">
          Error: write a thesis before turning it into criteria
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-ink-muted">Examples</span>
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={pending}
            onClick={() => setText(example)}
            className="press inline-flex h-8 items-center rounded-md border border-line-strong bg-surface px-3 text-dense text-ink-secondary transition-[background-color,color,transform] hover:bg-surface-raised hover:text-ink disabled:pointer-events-none disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorNotice title="The thesis could not be turned into criteria">
          {error}. Your text is kept, so you can try again.
        </ErrorNotice>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line pt-4">
        <p className="text-xs text-ink-muted" role="status">
          {pending ? "Separating must-haves from preferences" : "Nothing is searched at this step"}
        </p>
        <Button type="submit" variant="primary" disabled={pending} className="w-full sm:w-auto">
          {pending ? "Reading the thesis" : "Turn into criteria"}
        </Button>
      </div>
    </form>
  );
}
