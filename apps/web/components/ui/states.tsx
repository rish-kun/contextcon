"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Load } from "@/lib/use-load";
import { cn } from "@/lib/utils";
import { Button } from "./button";
import { Skeleton } from "./skeleton";

export type StateSize = "page" | "panel" | "inline";

const FRAME: Record<StateSize, string> = {
  page: "flex flex-col items-start gap-2 pt-2",
  panel: "flex flex-col items-start gap-2 p-4",
  inline: "flex flex-wrap items-center gap-x-2 gap-y-1",
};

/**
 * Something that does not exist yet: what is absent, what it is and how it comes to
 * exist, and at most two actions. Left-aligned at the top of its area, never centred.
 */
export function EmptyState({
  title,
  children,
  actions,
  size = "panel",
  className,
}: {
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  size?: StateSize;
  className?: string;
}) {
  if (size === "inline") {
    return (
      <p className={cn(FRAME.inline, "text-dense text-ink-secondary", className)}>
        {title}
        {actions}
      </p>
    );
  }
  return (
    <div className={cn(FRAME[size], className)}>
      <h2 className="text-sm font-medium text-ink">{title}</h2>
      {children ? (
        <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">{children}</p>
      ) : null}
      {actions ? <div className="flex flex-wrap gap-2 pt-2">{actions}</div> : null}
    </div>
  );
}

/**
 * A read that failed. Neutral, because red means one thing in this product: a claim was
 * Contradicted. It names what did not load, gives the reason, and offers one retry.
 */
export function ErrorState({
  what,
  reason,
  status,
  onRetry,
  size = "panel",
  className,
}: {
  /** The thing, capitalised: "Cases", "This screening". */
  what: string;
  reason?: string;
  status?: number | null;
  onRetry?: () => void;
  size?: StateSize;
  className?: string;
}) {
  const signedOut = status === 401;
  const action = signedOut ? (
    <Button asChild size="sm">
      <Link href="/login">Log in</Link>
    </Button>
  ) : onRetry ? (
    <Button size="sm" onClick={onRetry}>
      Try again
    </Button>
  ) : null;

  if (size === "inline") {
    return (
      <p role="alert" className={cn(FRAME.inline, "text-dense text-ink-secondary", className)}>
        {what} did not load
        {action}
      </p>
    );
  }
  return (
    <div
      role="alert"
      className={cn(
        FRAME[size],
        size === "page" && "rounded-lg border border-line-strong bg-surface p-4",
        className,
      )}
    >
      <h2 className="text-sm font-medium text-ink">{what} did not load</h2>
      <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">
        {reason ?? "Nothing was changed"}
        {status && !signedOut ? <span className="pl-2 font-mono text-xs text-ink-muted">{status}</span> : null}
      </p>
      {action ? <div className="pt-2">{action}</div> : null}
    </div>
  );
}

const ROW = { compact: "h-8", default: "h-10", "two-line": "h-13" } as const;

/**
 * Loading, drawn in the shape of what is coming: table rows, text lines or the stat row.
 * It announces itself once, and after two seconds says it is still working instead of
 * fading for ever.
 */
export function LoadingState({
  label,
  shape,
  count = 4,
  density = "default",
  size = "panel",
  className,
}: {
  /** Read out once: "Loading cases". */
  label: string;
  shape: "rows" | "lines" | "tiles";
  count?: number;
  density?: keyof typeof ROW;
  size?: StateSize;
  className?: string;
}) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setSlow(true), 2000);
    return () => clearTimeout(id);
  }, []);

  const items = Array.from({ length: count }, (_, index) => index);
  return (
    <div role="status" aria-label={label} className={cn("flex flex-col", size === "panel" && shape !== "rows" && "p-4", className)}>
      {shape === "rows" ? (
        <>
          <div className="h-8 bg-surface-sunken" />
          {items.map((index) => (
            <div key={index} className={cn("flex items-center gap-4 border-b border-line px-4 last:border-b-0", ROW[density])}>
              <Skeleton className="w-1/4" />
              <Skeleton className="w-1/6" />
              <Skeleton className="ml-auto w-16" />
            </div>
          ))}
        </>
      ) : shape === "tiles" ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {items.map((index) => (
            <div key={index} className="flex flex-col gap-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-7 w-12" />
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((index) => (
            <Skeleton key={index} className={index === count - 1 ? "w-2/3" : "w-full"} />
          ))}
        </div>
      )}
      {slow ? (
        <p className={cn("text-dense text-ink-secondary", shape === "rows" ? "px-4 py-2" : "pt-3")}>Still working</p>
      ) : null}
    </div>
  );
}

/** The common case: one `Load<T>` drawn as loading, error, empty or its content. */
export function Loadable<T>({
  state,
  what,
  loading,
  onRetry,
  empty,
  isEmpty,
  size = "panel",
  children,
}: {
  state: Load<T>;
  what: string;
  loading: Omit<React.ComponentProps<typeof LoadingState>, "size">;
  onRetry?: () => void;
  empty?: React.ReactNode;
  isEmpty?: (data: T) => boolean;
  size?: StateSize;
  children: (data: T) => React.ReactNode;
}) {
  if (state.status === "loading") return <LoadingState {...loading} size={size} />;
  if (state.status === "error") {
    return <ErrorState what={what} reason={state.message} status={state.code} onRetry={onRetry} size={size} />;
  }
  if (empty && isEmpty?.(state.data)) return <>{empty}</>;
  return <>{children(state.data)}</>;
}
