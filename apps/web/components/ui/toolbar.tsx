import { cn } from "@/lib/utils";

/**
 * The row of search and filters above a table. It scopes everything under it, and its
 * right edge carries the count of what is shown.
 */
export function Toolbar({
  children,
  count,
  className,
}: {
  children: React.ReactNode;
  count?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-x-4 gap-y-2", className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">{children}</div>
      {count !== undefined ? <p className="font-mono text-xs text-ink-muted">{count}</p> : null}
    </div>
  );
}

/** A set of mutually exclusive filters shown as joined buttons, each with an optional mono count. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  /** Names the group: "Filter by state". */
  label: string;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn("inline-flex max-w-full flex-wrap rounded-md border border-line-strong bg-surface p-0.5", className)}
    >
      {options.map((option) => {
        const pressed = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={pressed}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-7 items-center gap-2 rounded-sm px-3 text-dense transition-colors",
              pressed ? "bg-accent-tint font-medium text-accent" : "text-ink-secondary hover:bg-surface-raised hover:text-ink",
            )}
          >
            {option.label}
            {option.count !== undefined ? <span className="font-mono text-2xs font-normal">{option.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
