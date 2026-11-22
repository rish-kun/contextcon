import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";

/**
 * A simulated outcome. It is hatched and dashed, it says Hypothetical in words, and it
 * never borrows a disposition stamp or a status colour, so it cannot be read as a result.
 */
export function HypotheticalCard({
  condition,
  outcome,
  children,
  className,
}: {
  /** "If both blockers are supported". */
  condition: string;
  /** "would be Prioritise", in plain ink. */
  outcome: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label="Hypothetical outcome"
      className={cn(
        "hatch-hypothetical flex min-w-0 flex-col gap-2 rounded-md border border-dashed border-ink-muted p-3",
        className,
      )}
    >
      <p className="self-start rounded-xs border border-dashed border-ink-muted bg-surface px-1.5 text-xs font-medium text-ink-secondary">
        Hypothetical
      </p>
      <div className="flex flex-col gap-1 rounded-xs bg-surface px-3 py-2">
        <p className="text-dense text-ink-secondary">{condition}</p>
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Icon icon={ArrowRight} className="shrink-0 text-ink-muted" />
          {outcome}
        </p>
        {children ? <div className="flex flex-col gap-1 text-dense text-ink-secondary">{children}</div> : null}
      </div>
    </section>
  );
}

const CHIP = "inline-flex h-5.5 shrink-0 items-center gap-1 rounded-xs border px-1.5 text-xs whitespace-nowrap";

/** An item's role in the decision. Outline only: a role is not a verification result. */
export function ClassChips({
  blocker,
  risk,
  className,
}: {
  blocker: boolean;
  risk: boolean;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {blocker ? <span className={cn(CHIP, "border-ink text-ink")}>Decision blocker</span> : null}
      {risk ? (
        <span className={cn(CHIP, "border-ink text-ink")}>
          <span aria-hidden className="font-mono font-semibold">
            !
          </span>
          Disqualifier risk
        </span>
      ) : null}
      {!blocker && !risk ? <span className={cn(CHIP, "border-line-strong text-ink-muted")}>Non-blocking</span> : null}
    </span>
  );
}
