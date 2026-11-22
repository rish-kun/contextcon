import type { CaseCostOut } from "@/lib/api/client";
import { formatShortDateTime, plural } from "@/lib/format";
import { RUN_KIND_LABEL } from "@/lib/labels";
import { HatchedBlock } from "@/components/dealproof/blocks";
import { CostMeter } from "@/components/explainers/cost-meter";
import { meterFromCostOut } from "@/components/explainers/derive";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Section } from "./parts";

/** Credits come in fractions from the provider: `19.5`, `4`, `1,204`. */
export function credits(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

/** Model usage per step is a fraction of a cent, so this tab keeps four decimals throughout. */
export function usd(value: number): string {
  return `$${value.toFixed(4)}`;
}

function unknownCalls(count: number): string {
  return `${plural(count, "call")} of unknown cost`;
}

/**
 * What the case cost. Credits and model dollars are two currencies and are never added.
 * A call whose cost the provider did not report is shown as unknown, never as zero.
 * Reaching the budget is a stated limit, not an error, so nothing turns red.
 */
export function CostPanel({ cost, basePath }: { cost: CaseCostOut; basePath: string }) {
  const lines = [...cost.by_step].sort((a, b) => a.at.localeCompare(b.at));
  const claimsHref = `${basePath}/claims?status=not_checked`;

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3" aria-labelledby="cost-heading">
        <h2 id="cost-heading" className="text-sm font-medium text-ink">
          This case cost
        </h2>
        <CostMeter model={meterFromCostOut(cost)} usdDigits={4} notCheckedHref={claimsHref} />
        {cost.unknown_cost_calls > 0 ? (
          <p className="font-mono text-xs text-ink-secondary">
            + {unknownCalls(cost.unknown_cost_calls)}, not in the figures above
          </p>
        ) : null}
        <p className="max-w-2xl text-xs text-ink-secondary">
          Credits count Crustdata lookups against this case&apos;s budget. Model usage is
          language-model spend in US dollars. The two are never added together.
        </p>
      </section>

      {cost.unknown_cost_calls > 0 ? (
        <HatchedBlock role="note" innerClassName="flex flex-col gap-1 text-dense">
          <p className="font-medium">{unknownCalls(cost.unknown_cost_calls)}</p>
          <p>
            The provider&apos;s response carried no usage figure. The cost is recorded as unknown,
            not as zero, so the totals on this page are a lower bound.
          </p>
        </HatchedBlock>
      ) : null}

      <Section title="By run and step" meta={plural(lines.length, "step")}>
        {lines.length === 0 ? (
          <p className="rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-secondary">
            No step has recorded usage yet.
          </p>
        ) : (
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
              {lines.map((line) => (
                <TableRow key={`${line.run_id}:${line.step_key}`}>
                  <TableCell className="whitespace-nowrap text-ink-secondary">
                    {RUN_KIND_LABEL[line.run_kind]}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex flex-wrap items-center gap-2">
                      {line.step_label}
                      {line.cost.unknown_cost_calls > 0 ? (
                        <Badge variant="outline" className="border-dashed font-mono text-2xs">
                          + {unknownCalls(line.cost.unknown_cost_calls)}
                        </Badge>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell numeric>
                    {line.cached
                      ? "0 · cache"
                      : line.cost.crustdata_credits > 0
                        ? credits(line.cost.crustdata_credits)
                        : "–"}
                  </TableCell>
                  <TableCell numeric>{line.cost.llm_usd > 0 ? usd(line.cost.llm_usd) : "–"}</TableCell>
                  <TableCell numeric className="text-ink-secondary">
                    {formatShortDateTime(line.at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={2}>
                  Total
                  {cost.unknown_cost_calls > 0 ? (
                    <span className="font-normal text-ink-secondary">
                      {" "}
                      · excludes {unknownCalls(cost.unknown_cost_calls)}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell numeric>{credits(cost.crustdata_credits)}</TableCell>
                <TableCell numeric>{usd(cost.llm_usd)}</TableCell>
                <TableCell />
              </TableRow>
            </TableFooter>
          </Table>
        )}
      </Section>

      {cost.shared_discovery ? (
        <Section
          title="Discovery cost"
          meta="shared"
          lead="Spent once on the search that produced the shortlist this case was opened from. It is shown here once and is not added to this case's total, so it is not counted again for every case from that shortlist."
        >
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-dense sm:grid-cols-[auto_auto_auto_minmax(0,1fr)] sm:items-baseline">
            <dt className="text-ink-muted">Shared, from run</dt>
            <dd className="font-mono text-xs break-all text-ink">{cost.shared_discovery.run_id}</dd>
            <dt className="text-ink-muted sm:text-right">Cost of that run</dt>
            <dd className="font-mono text-ink sm:text-right">
              {credits(cost.shared_discovery.cost.crustdata_credits)} credits
              <span className="text-ink-muted"> · </span>
              {usd(cost.shared_discovery.cost.llm_usd)} model usage
              {cost.shared_discovery.cost.unknown_cost_calls > 0 ? (
                <>
                  <span className="text-ink-muted"> + </span>
                  {unknownCalls(cost.shared_discovery.cost.unknown_cost_calls)}
                </>
              ) : null}
            </dd>
          </dl>
        </Section>
      ) : null}
    </div>
  );
}
