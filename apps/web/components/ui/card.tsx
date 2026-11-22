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
      className={cn("rounded-xl border border-line bg-surface text-ink", className)}
      {...props}
    />
  );
}

/** The mono meta line at the top of a panel: "Assessment · version 2 · policy 1.0". */
export function PanelHeader({ className, ...props }: React.ComponentProps<"header">) {
  return (
    <header
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-5 py-3",
        className,
      )}
      {...props}
    />
  );
}

export function PanelBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("p-5", className)} {...props} />;
}
