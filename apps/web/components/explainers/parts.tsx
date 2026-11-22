import { duration, ease } from "@/lib/transitions";
import { cn } from "@/lib/utils";

/** A line growing from its start: `scaleX` (or `scaleY`) from 0 to 1 over the slow duration. */
export const draw = { duration: duration.slow, ease } as const;

/**
 * A hairline arrow between two columns of an explainer. Solid when something was taken
 * from the left side; dashed when a search returned nothing.
 */
export function Connector({
  dashed = false,
  className,
}: {
  dashed?: boolean;
  className?: string;
}) {
  return (
    <svg
      width="24"
      height="9"
      viewBox="0 0 24 9"
      fill="none"
      aria-hidden
      focusable={false}
      className={cn("shrink-0", dashed ? "text-not-checked-line" : "text-ink-muted", className)}
    >
      <path d="M0 4.5h22" stroke="currentColor" strokeWidth="1" strokeDasharray={dashed ? "3 3" : undefined} />
      <path d="m19 1.5 3.5 3-3.5 3" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The quiet head above each column of an explainer. */
export function ColumnHead({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-xs text-ink-muted", className)}>{children}</p>;
}
