import { cn } from "@/lib/utils";

/**
 * A plain semantic table at 13px. Numbers go in `numeric` cells: right-aligned, mono,
 * tabular. Row states read apart: hover is a surface step, selected is accent tint with a
 * left bar (set data-state="selected" and aria-selected), the header is a sunken band.
 */
export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-line bg-surface">
      <table
        className={cn("w-full border-collapse text-left text-dense text-ink", className)}
        {...props}
      />
    </div>
  );
}

export function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("bg-surface-sunken", className)} {...props} />;
}

export function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("[&>tr:last-child]:border-b-0", className)} {...props} />;
}

export function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      className={cn("border-t border-line-strong font-medium [&>tr]:border-b-0", className)}
      {...props}
    />
  );
}

export function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn(
        "border-b border-line transition-colors hover:bg-surface-raised data-[state=selected]:selected-bar data-[state=selected]:bg-accent-tint",
        className,
      )}
      {...props}
    />
  );
}

export function TableHead({
  className,
  numeric = false,
  ...props
}: React.ComponentProps<"th"> & { numeric?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        "h-8 px-3 text-xs font-medium whitespace-nowrap text-ink-secondary",
        numeric && "text-right",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({
  className,
  numeric = false,
  ...props
}: React.ComponentProps<"td"> & { numeric?: boolean }) {
  return (
    <td
      className={cn(
        "h-9 px-3 py-2 align-middle",
        numeric && "text-right font-mono whitespace-nowrap",
        className,
      )}
      {...props}
    />
  );
}

export function TableCaption({ className, ...props }: React.ComponentProps<"caption">) {
  return (
    <caption
      className={cn("caption-bottom px-3 py-2 text-left text-xs text-ink-muted", className)}
      {...props}
    />
  );
}
