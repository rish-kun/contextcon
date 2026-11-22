"use client";

import { FileText, Lock, Upload, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button, Icon, Popover, PopoverContent, PopoverTrigger } from "@/components/ui";

/** The API takes PDF, PPTX and DOCX, at most 25 MB each. */
const ACCEPTED_EXTENSIONS = [".pdf", ".pptx", ".docx"];
export const MAX_UPLOAD_MB = 25;
/** Uploads are deleted this many days after upload unless the server says otherwise. */
export const RETENTION_DAYS = 30;

export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return `${file.name}: this file format is not supported. Upload a PDF, PPTX or DOCX file`;
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `${file.name}: this file exceeds the upload limit of ${MAX_UPLOAD_MB} MB`;
  }
  return null;
}

/** Split typed text into claims: one per line, blanks dropped. */
export function claimLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * The confidentiality line that sits beside every upload control. It always states when
 * the files are deleted: the date once the server has set one, the rule before that.
 */
export function ConfidentialityStrip({
  deleteAfter,
  className,
}: {
  /** The server's deletion timestamp for files already on the case. */
  deleteAfter?: string | null;
  className?: string;
}) {
  const date = formatDate(deleteAfter);
  const deletion = date ? `deleted on ${date}` : `deleted ${RETENTION_DAYS} days after upload`;
  return (
    <p className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-secondary", className)}>
      <Icon icon={Lock} size={14} className="shrink-0 text-ink-muted" />
      <span>
        Used only for this case · <span className="font-mono text-2xs">{deletion}</span>
      </span>
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            Confidentiality details
          </button>
        </PopoverTrigger>
        <PopoverContent className="flex flex-col gap-3 text-dense">
          <p className="text-sm font-medium text-ink">How uploaded documents are handled</p>
          <dl className="flex flex-col gap-2">
            {[
              ["Case-only use", "Files are read only to check claims and prepare the memo for this case."],
              ["Never used for training", "Your documents are never used to train AI models."],
              ["Not shared across customers", "Files and extracted claims stay in your workspace."],
              ["Personal details stripped", "Personal details that screening does not need are removed during processing."],
              ["Scheduled deletion", `Files on this case are ${deletion}, or earlier if you delete the case.`],
            ].map(([term, text]) => (
              <div key={term}>
                <dt className="font-medium text-ink">{term}</dt>
                <dd className="text-ink-secondary">{text}</dd>
              </div>
            ))}
          </dl>
        </PopoverContent>
      </Popover>
    </p>
  );
}

/**
 * Drop or choose seller documents. It only collects and checks files; the caller decides
 * what to do with the ones that pass.
 */
export function DocumentDropzone({
  onFiles,
  disabled = false,
  className,
}: {
  /** Called with the files that passed the format and size checks. */
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
}) {
  const inputId = useId();
  const errorId = `${inputId}-errors`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  function take(list: FileList | null) {
    if (!list || disabled) return;
    const good: File[] = [];
    const bad: string[] = [];
    for (const file of Array.from(list)) {
      const problem = validateFile(file);
      if (problem) bad.push(problem);
      else good.push(file);
    }
    setErrors(bad);
    if (good.length > 0) onFiles(good);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <label
        htmlFor={inputId}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          take(event.dataTransfer.files);
        }}
        className={cn(
          "flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed px-4 py-5 text-center transition-colors has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus",
          over ? "border-accent bg-accent-tint" : "border-line-strong bg-surface-raised hover:border-ink-muted",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <Icon icon={Upload} className="text-ink-muted" />
        <span className="text-sm text-ink">
          Drop seller presentation or documents here, or{" "}
          <span className="text-accent underline underline-offset-2">choose files</span>
        </span>
        <span className="font-mono text-2xs text-ink-secondary">
          PDF, PPTX or DOCX · up to {MAX_UPLOAD_MB} MB each
        </span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple
          disabled={disabled}
          accept={ACCEPTED_EXTENSIONS.join(",")}
          aria-describedby={errors.length > 0 ? errorId : undefined}
          onChange={(event) => take(event.target.files)}
          className="sr-only"
        />
      </label>
      {errors.length > 0 ? (
        <ul id={errorId} role="alert" className="flex flex-col gap-1 text-xs text-contradicted">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** A file waiting to be sent, with a way to take it back out. */
export function QueuedFile({ file, onRemove }: { file: File; onRemove?: () => void }) {
  return (
    <li className="flex items-center gap-2 text-dense text-ink">
      <Icon icon={FileText} className="shrink-0 text-ink-muted" />
      <span className="min-w-0 truncate">{file.name}</span>
      <span className="shrink-0 font-mono text-2xs text-ink-secondary">{formatBytes(file.size)}</span>
      {onRemove ? (
        <Button
          variant="quiet"
          size="icon"
          className="ml-auto size-8"
          aria-label={`Remove ${file.name}`}
          onClick={onRemove}
        >
          <Icon icon={X} />
        </Button>
      ) : null}
    </li>
  );
}
