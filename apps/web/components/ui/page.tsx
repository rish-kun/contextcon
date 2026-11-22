import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

/** The one page wrapper inside the shell: a column with the page gap, no width cap, no entrance. */
export function Page({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-6", className)} {...props} />;
}

export interface StatFigureProps {
  value: React.ReactNode;
  label: string;
  /** Links the figure to the list it counts. */
  href?: string;
  /** Marks the value as inferred: a tilde and a dotted underline. */
  estimate?: boolean;
}

/** A figure at the right edge of a page header: the number over its label. */
export function StatFigure({ value, label, href, estimate = false }: StatFigureProps) {
  const body = (
    <>
      <span className={cn("font-mono text-xl font-medium text-ink", estimate && "underline-estimate")}>
        {estimate ? "~" : null}
        {value}
      </span>
      <span className="text-xs text-ink-muted">{label}</span>
    </>
  );
  const shape = "flex flex-col items-start gap-0.5 lg:items-end";
  return href ? (
    <Link href={href} className={cn(shape, "rounded-xs transition-colors hover:[&>span:first-child]:text-accent")}>
      {body}
    </Link>
  ) : (
    <div className={shape}>{body}</div>
  );
}

/**
 * The page header: the name of the place or the object, one fact line, up to four
 * figures, and at most two actions. The title is the same word as the nav item and the
 * breadcrumb.
 */
export function PageHeader({
  title,
  meta,
  figures,
  actions,
  back,
  className,
}: {
  title: string;
  /** One line of facts. Counts and dates inside it are mono. */
  meta?: React.ReactNode;
  figures?: StatFigureProps[];
  actions?: React.ReactNode;
  /** Detail pages only: where this page was reached from. */
  back?: { label: string; href: string };
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-x-8 gap-y-4", className)}>
      <div className="flex min-w-0 flex-col gap-1">
        {back ? (
          <Link
            href={back.href}
            className="-ml-1 inline-flex items-center gap-1 self-start rounded-xs text-xs text-ink-secondary transition-colors hover:text-ink"
          >
            <Icon icon={ChevronLeft} size={14} />
            {back.label}
          </Link>
        ) : null}
        <h1 className="text-2xl font-medium text-ink">{title}</h1>
        {meta ? <p className="text-dense text-ink-secondary">{meta}</p> : null}
      </div>
      {figures?.length || actions ? (
        <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
          {figures?.slice(0, 4).map((figure) => <StatFigure key={figure.label} {...figure} />)}
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
    </header>
  );
}
