import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * A quiet tag for categories, counts and meta. It is not a status: claim statuses use
 * StatusMark and dispositions use DispositionStamp, which carry a glyph as well.
 */
export const badgeVariants = cva(
  "inline-flex h-6 shrink-0 items-center gap-1 rounded-xs border px-2 text-xs whitespace-nowrap",
  {
    variants: {
      variant: {
        neutral: "border-line bg-surface-raised text-ink-secondary",
        outline: "border-line-strong bg-transparent text-ink-secondary",
        accent: "border-accent-line bg-accent-tint text-accent",
        /** Mono figures: counts, versions, credits */
        mono: "border-line bg-surface-raised font-mono text-2xs text-ink-secondary",
        /** Test mode: dashed, so it reads as "not live" without its colour */
        "test-mode": "border-dashed border-test-mode bg-test-mode-tint text-test-mode",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/** A keyboard key, for shortcuts such as ⌘K. */
export function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-xs border border-line-strong bg-surface px-1 font-mono text-2xs text-ink-secondary",
        className,
      )}
      {...props}
    />
  );
}
