"use client";

import { CircleQuestionMark } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button, Icon } from "@/components/ui";
import { useCase } from "./case-context";

/** The title of a case tab with its one-line summary and, on the right, its actions. */
export function TabHeading({
  title,
  summary,
  children,
  className,
}: {
  title: string;
  summary?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="flex min-w-0 flex-col gap-1">
        <h2 className="text-xl font-medium text-ink">{title}</h2>
        {summary ? <p className="text-dense text-ink-secondary">{summary}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

/**
 * Stands in for the content of an identity-dependent tab until the legal entity is
 * chosen. Nothing is attached to a company on a matching name alone.
 */
export function BlockedByIdentity({ what, className }: { what?: string; className?: string }) {
  const { basePath } = useCase();
  return (
    <section
      aria-label="Waiting on identity"
      className={cn(
        "flex flex-col items-start gap-3 rounded-lg border border-cannot-verify bg-cannot-verify-tint p-5",
        className,
      )}
    >
      <h3 className="flex items-center gap-2 text-sm font-medium text-cannot-verify">
        <Icon icon={CircleQuestionMark} />
        Waiting on identity
      </h3>
      <p className="max-w-(--layout-prose-max) text-dense text-ink">
        {what ? `${what} ` : null}
        Confirm which legal entity this case refers to before records are attached. Until
        identity is confirmed, the disposition remains Cannot assess.
      </p>
      <Button asChild variant="primary" size="sm">
        <Link href={`${basePath}/identity`}>Resolve identity</Link>
      </Button>
    </section>
  );
}

/** A plain empty state: what is missing, why, and at most two actions. */
export function EmptyState({
  title,
  children,
  actions,
  className,
}: {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-2 rounded-lg border border-line bg-surface px-5 py-8",
        className,
      )}
    >
      <h3 className="text-sm font-medium text-ink">{title}</h3>
      <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">{children}</p>
      {actions ? <div className="flex flex-wrap gap-2 pt-2">{actions}</div> : null}
    </div>
  );
}
