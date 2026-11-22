import { cn } from "@/lib/utils";

/**
 * Card: radius 12, a hairline, no shadow by default. Pass `raised` only for the card that
 * is the main object of a page. Panel: radius 16, for a group of related blocks.
 */
export function Card({
  className,
  raised = false,
  ...props
}: React.ComponentProps<"div"> & { raised?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-line bg-surface text-ink",
        raised && "shadow-xs",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1 p-5 pb-0", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return <h3 className={cn("text-xl font-medium text-ink", className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn("text-sm text-ink-secondary", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("p-5", className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("flex items-center gap-2 border-t border-line px-5 py-4", className)}
      {...props}
    />
  );
}

export function Panel({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      className={cn("rounded-lg border border-line bg-surface text-ink", className)}
      {...props}
    />
  );
}

/**
 * The head of a panel, 40px. Pass `title` for the standard form: the section heading at
 * 14px, a mono `meta` on its baseline (a count, a version, an as-of date) and one quiet
 * action on the right. Pass children instead for a custom head.
 */
export function PanelHeader({
  className,
  title,
  meta,
  action,
  id,
  children,
  ...props
}: Omit<React.ComponentProps<"header">, "title"> & {
  title?: string;
  meta?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <header
      className={cn(
        "flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-2",
        className,
      )}
      {...props}
    >
      {title ? (
        <>
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
            <h2 id={id} className="text-sm font-medium text-ink">
              {title}
            </h2>
            {meta ? <span className="font-mono text-xs text-ink-muted">{meta}</span> : null}
          </div>
          {action}
        </>
      ) : (
        children
      )}
    </header>
  );
}

/** The body of a panel. `flush` drops the padding so a table or list runs edge to edge. */
export function PanelBody({
  className,
  flush = false,
  lead,
  children,
  ...props
}: React.ComponentProps<"div"> & { flush?: boolean; lead?: React.ReactNode }) {
  return (
    <div className={cn(flush ? "overflow-hidden rounded-b-lg" : "p-4", className)} {...props}>
      {lead ? (
        <p className={cn("max-w-(--layout-prose-max) text-dense text-ink-secondary", flush ? "px-4 py-3" : "pb-3")}>
          {lead}
        </p>
      ) : null}
      {children}
    </div>
  );
}

export function PanelFooter({ className, ...props }: React.ComponentProps<"footer">) {
  return (
    <footer
      className={cn(
        "flex min-h-9 items-center border-t border-line px-4 py-2 text-xs text-ink-muted",
        className,
      )}
      {...props}
    />
  );
}

/** Panels on twelve columns with a 16px gutter. Items stack below 1024px. */
export function PanelGrid({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("grid grid-cols-12 items-start gap-4", className)} {...props} />;
}

const SPAN = {
  4: "lg:col-span-4",
  6: "lg:col-span-6",
  8: "lg:col-span-8",
  12: "lg:col-span-12",
} as const;

export function PanelGridItem({
  span,
  className,
  ...props
}: React.ComponentProps<"div"> & { span: keyof typeof SPAN }) {
  return <div className={cn("col-span-12 flex min-w-0 flex-col gap-4", SPAN[span], className)} {...props} />;
}
