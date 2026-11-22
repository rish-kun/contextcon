import { formatCredits, formatShortDateTime, formatUsd } from "@/lib/format";
import type { CaseCost } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CostMeter } from "@/components/explainers/cost-meter";
import { meterFromCaseCost } from "@/components/explainers/derive";
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
 * The credit figure and its bar are the cost meter (components/explainers/cost-meter):
 * one bar segmented by step, with the checks the budget left undone hatched past its
 * end. This component adds the heading and the table by run and step, which is the
 * bar's table view.
 *
 * variant="compact" is "86 cr · $0.42" with a 48px bar, for the case header and dashboard rows.
 */
export function CostReadout({
  cost,
  variant = "full",
  title = "This case cost",
  notCheckedHref,
  className,
}: {
  cost: CaseCost;
  variant?: "full" | "compact";
  /** Heading of the full readout, for costs that are not a case: "This search cost". */
  title?: string;
  /** Link to the Not checked claims, shown when the budget is reached. */
  notCheckedHref?: string;
  className?: string;
}) {
  const meter = meterFromCaseCost(cost);

  if (variant === "compact") {
    return <CostMeter model={meter} variant="compact" className={className} />;
  }

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-ink">{title}</h3>
        <CostMeter model={meter} notCheckedHref={notCheckedHref} />
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
