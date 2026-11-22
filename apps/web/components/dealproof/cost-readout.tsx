import { formatCredits, formatShare, formatShortDateTime, formatUsd, plural } from "@/lib/format";
import type { CaseCost } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/**
 * What the case cost. Crustdata credits and model dollars are two currencies and are
 * never added together. Reaching the budget is a stated limit, not an error, so nothing
 * turns red.
 *
 * variant="compact" is "86 cr · $0.42" for the case header and dashboard rows.
 */
export function CostReadout({
  cost,
  variant = "full",
  notCheckedHref,
  className,
}: {
  cost: CaseCost;
  variant?: "full" | "compact";
  /** Link to the Not checked claims, shown when the budget is reached. */
  notCheckedHref?: string;
  className?: string;
}) {
  if (variant === "compact") {
    return (
      <span
        className={cn("font-mono text-xs whitespace-nowrap text-ink-secondary", className)}
        aria-label={`${formatCredits(cost.credits_used)} Crustdata credits and ${formatUsd(
          cost.model_usd,
        )} model usage`}
      >
        {formatCredits(cost.credits_used)} cr · {formatUsd(cost.model_usd)}
      </span>
    );
  }

  const share = cost.credit_budget > 0 ? Math.min(1, cost.credits_used / cost.credit_budget) : 0;
  const reached = cost.credit_budget > 0 && cost.credits_used >= cost.credit_budget;
  const notRun = cost.checks_not_run ?? 0;

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-ink">This case cost</h3>
        <p className="font-mono text-xl font-medium text-ink">
          {formatCredits(cost.credits_used)} of {formatCredits(cost.credit_budget)} credits
          <span className="text-ink-muted"> · </span>
          {formatUsd(cost.model_usd)} model usage
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <div
            role="meter"
            aria-label="Crustdata credits used against the budget"
            aria-valuemin={0}
            aria-valuemax={cost.credit_budget}
            aria-valuenow={cost.credits_used}
            aria-valuetext={`${formatCredits(cost.credits_used)} of ${formatCredits(
              cost.credit_budget,
            )} credits`}
            className="h-2 w-full max-w-md overflow-hidden rounded-xs border border-line-strong bg-surface-sunken"
          >
            <div className="h-full bg-ink" style={{ width: `${share * 100}%` }} />
          </div>
          <p className="text-xs text-ink-secondary">
            {reached ? (
              <>
                Budget reached
                {notRun > 0 ? (
                  <>
                    {" · "}
                    {notCheckedHref ? (
                      <a
                        href={notCheckedHref}
                        className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
                      >
                        {plural(notRun, "check")} not run
                      </a>
                    ) : (
                      `${plural(notRun, "check")} not run`
                    )}
                  </>
                ) : null}
              </>
            ) : (
              `${formatShare(share)} of the credit budget`
            )}
          </p>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Run</TableHead>
            <TableHead>Step</TableHead>
            <TableHead numeric>Credits</TableHead>
            <TableHead numeric>Model</TableHead>
            <TableHead numeric>When</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {cost.lines.map((line) => (
            <TableRow key={line.id}>
              <TableCell>{line.run_label}</TableCell>
              <TableCell>{line.step_label}</TableCell>
              <TableCell numeric>
                {line.from_cache ? "0 · cache" : line.credits != null ? formatCredits(line.credits) : "–"}
              </TableCell>
              <TableCell numeric>
                {line.model_usd != null ? formatUsd(line.model_usd) : "–"}
              </TableCell>
              <TableCell numeric className="text-ink-secondary">
                {formatShortDateTime(line.at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={2}>Total</TableCell>
            <TableCell numeric>{formatCredits(cost.credits_used)}</TableCell>
            <TableCell numeric>{formatUsd(cost.model_usd)}</TableCell>
            <TableCell />
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}
