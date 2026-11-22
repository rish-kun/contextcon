"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

const controlBase =
  "w-full rounded-md border border-line-strong bg-surface-raised px-3 text-sm text-ink transition-[background-color,border-color] placeholder:text-ink-muted hover:border-ink-muted focus-visible:bg-surface disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-contradicted";

export function Input({ className, type = "text", ...props }: React.ComponentProps<"input">) {
  return <input type={type} className={cn(controlBase, "h-9", className)} {...props} />;
}

export function Textarea({ className, rows = 4, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      rows={rows}
      className={cn(controlBase, "min-h-20 resize-y py-2", className)}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium text-ink", className)} {...props} />;
}

interface FieldControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

/**
 * A label, a control and its hint or error, wired together for assistive technology.
 * The error is announced and is also marked with the word, not only the colour.
 *
 *   <Field label="Recipient" hint="Typed by you">
 *     {(control) => <Input {...control} />}
 *   </Field>
 */
export function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  children: (control: FieldControlProps) => React.ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
      })}
      {hint ? (
        <p id={hintId} className="text-xs text-ink-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-contradicted">
          Error: {error}
        </p>
      ) : null}
    </div>
  );
}
