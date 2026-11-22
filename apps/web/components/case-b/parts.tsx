import Link from "next/link";
import { cn } from "@/lib/utils";

/** A section inside a tab. */
export function Section({
  title,
  meta,
  lead,
  children,
  className,
  id,
}: {
  title: string;
  /** Mono meta beside the title: a count, a version. */
  meta?: React.ReactNode;
  lead?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("flex scroll-mt-24 flex-col gap-3", className)}>
      <div className="flex flex-col gap-1">
        <h3 className="flex flex-wrap items-baseline gap-x-2 text-sm font-medium text-ink">
          {title}
          {meta != null ? (
            <span className="font-mono text-xs font-normal text-ink-muted">{meta}</span>
          ) : null}
        </h3>
        {lead ? <p className="max-w-2xl text-dense text-ink-secondary">{lead}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** The read failed. Said plainly, so an unloaded tab is never mistaken for an empty case. */
export function LoadError({ what, status }: { what: string; status: number | null }) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-1 rounded-lg border border-line-strong bg-surface px-5 py-4"
    >
      <h2 className="text-sm font-medium text-ink">Could not load {what}</h2>
      <p className="text-dense text-ink-secondary">
        {status === 401
          ? "Your session has ended. Sign in again to read this case."
          : "The service did not answer. Nothing is shown, because a partial record would look complete. Reload to try again."}
        {status && status !== 401 ? <span className="font-mono text-xs"> · {status}</span> : null}
      </p>
    </div>
  );
}

/** An in-text link in accent ink. */
export function TextLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover",
        className,
      )}
    >
      {children}
    </Link>
  );
}
