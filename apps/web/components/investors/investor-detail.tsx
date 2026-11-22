"use client";

import { Ban, Check, CircleHelp, type LucideIcon } from "lucide-react";
import type { InvestorEntryOut } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { FundingRoundsTable } from "@/components/insight";
import { Icon } from "@/components/ui/icon";
import {
  classifyCompatibility,
  COMPATIBILITY_LABEL,
  type Compatibility,
  compatibilityReason,
  fundingLabel,
  roundLabel,
  sentence,
} from "./format";
import { type RoundAxis, RoundAxisHeader, RoundStrip } from "./round-axis";
import { RoundSource } from "./round-source";

const COMPATIBILITY_ICON: Record<Compatibility, LucideIcon> = {
  compatible: Check,
  incompatible: Ban,
  unknown: CircleHelp,
};

/**
 * Compatible, incompatible or unknown, each with its own glyph and the word. It is not a
 * claim status, so it does not borrow the status colours: only "unknown" takes the slate
 * of things the record cannot settle.
 */
export function CompatibilityMark({ value, compact = false }: { value: Compatibility; compact?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-sm border px-2 text-xs font-medium",
        value === "unknown"
          ? "border-cannot-verify-line bg-cannot-verify-tint text-cannot-verify"
          : "border-line-strong bg-surface text-ink",
      )}
    >
      <Icon icon={COMPATIBILITY_ICON[value]} size={14} />
      {compact ? <span className="sr-only">Funding kind: </span> : null}
      {COMPATIBILITY_LABEL[value]}
    </span>
  );
}

/** The row in the ranked list: rank, name, the two facts the order counts, and the rounds on the shared axis. */
export function InvestorRow({ entry, axis }: { entry: InvestorEntryOut; axis: RoundAxis | null }) {
  const latest = formatDate(entry.latest_sector_investment_found);
  return (
    <span className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2">
      <span className="pt-0.5 font-mono text-xs text-ink-muted">
        <span className="sr-only">Rank </span>
        {entry.rank}
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-medium text-ink">{entry.investor_name}</span>
        <span className="text-xs text-ink-secondary">
          {plural(entry.comparable_rounds.length, "comparable investment")}
          <span aria-hidden className="text-ink-muted">
            {" · "}
          </span>
          latest found <span className="font-mono text-ink">{latest ?? "none"}</span>
        </span>
        {axis ? <RoundStrip axis={axis} entry={entry} className="mt-1 h-5" /> : null}
      </span>
    </span>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <dt className="text-xs text-ink-muted">{children}</dt>;
}

/**
 * Everything the record holds about one investor: the dated rounds that put it on the
 * list, as a table with amounts drawn to one scale and a source on every row, then what
 * the record does and does not say. There is no contact detail and no control that sends
 * anything. The position in the list counts past rounds; it is not a forecast.
 */
export function InvestorDetail({
  entry,
  axis,
  fundingSought,
  scope,
  duplicates,
  onSelect,
}: {
  entry: InvestorEntryOut;
  axis: RoundAxis | null;
  fundingSought: string;
  /** Search date and scope, always shown beside "latest sector investment found". */
  scope: string;
  /** Other entries that may be the same firm. Flagged, never merged. */
  duplicates: InvestorEntryOut[];
  onSelect: (id: string) => void;
}) {
  const latest = formatDate(entry.latest_sector_investment_found);
  const compatibility = classifyCompatibility(entry.funding_kind_compatibility);

  return (
    <article aria-labelledby={`${entry.id}-name`} className="flex min-w-0 flex-col gap-5 text-dense">
      <header className="flex flex-col gap-1">
        <p className="font-mono text-xs text-ink-muted">
          Rank {entry.rank} by comparable investments found, recent ones counting more
        </p>
        <h3 id={`${entry.id}-name`} className="text-xl font-medium text-ink">
          {entry.investor_name}
        </h3>
        <p className="text-ink-secondary">
          {plural(entry.comparable_rounds.length, "comparable investment")}
          <span aria-hidden className="text-ink-muted">
            {" · "}
          </span>
          latest sector investment found{" "}
          <span className="font-mono text-xs text-ink">{latest ?? "none"}</span>
        </p>
      </header>

      {axis ? (
        <div className="flex flex-col gap-1">
          <RoundAxisHeader axis={axis} />
          <RoundStrip axis={axis} entry={entry} />
        </div>
      ) : null}

      <section className="flex min-w-0 flex-col gap-2">
        <h4 className="text-xs font-medium text-ink-secondary">Comparable companies backed</h4>
        <FundingRoundsTable
          caption={`Dated funding rounds in comparable companies where ${entry.investor_name} is named`}
          showCompany
          showInvestors={false}
          rows={entry.comparable_rounds.map((round, index) => ({
            id: `${round.company_id}-${round.date}-${index}`,
            company: round.company_name,
            round: roundLabel(round.round_type),
            date: round.date,
            amountUsd: round.amount_usd,
            source: (
              <RoundSource
                source={round.source}
                asOf={round.date}
                company={round.company_name}
                companyId={round.company_id}
                evidenceId={round.evidence_id}
              />
            ),
          }))}
        />
        <p className="text-xs text-ink-secondary">
          Bars compare round sizes within this table. A round&apos;s size is the whole round, not
          this investor&apos;s share of it
        </p>
      </section>

      <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <Label>Funding kind · {fundingLabel(fundingSought)}</Label>
          <dd className="flex flex-col items-start gap-1 text-ink">
            <CompatibilityMark value={compatibility} />
            <span className="text-ink-secondary">
              {compatibilityReason(entry.funding_kind_compatibility, fundingSought)}
            </span>
          </dd>
        </div>
        <div className="flex flex-col gap-1">
          <Label>Why they fit</Label>
          <dd className="text-ink">{sentence(entry.why)}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <Label>Unknown</Label>
          <dd className="text-ink-secondary">
            {entry.unknowns.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {entry.unknowns.map((unknown) => (
                  <li key={unknown}>{sentence(unknown)}</li>
                ))}
              </ul>
            ) : (
              "Nothing flagged in the records read"
            )}
          </dd>
        </div>
        <div className="flex flex-col gap-1">
          <Label>Scope of this search</Label>
          <dd className="text-ink-secondary">
            {scope}. A later round outside that scope would not show here
          </dd>
        </div>
      </dl>

      {duplicates.length > 0 ? (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-dashed border-line-strong pt-3 text-ink-secondary">
          {duplicates.map((other) => (
            <button
              key={other.id}
              type="button"
              onClick={() => onSelect(other.id)}
              title="These investor names may refer to the same firm. DealProof keeps them separate unless confirmed"
              className="rounded-xs text-left underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink"
            >
              Possible duplicate of “{other.investor_name}” · not merged
            </button>
          ))}
        </p>
      ) : null}
    </article>
  );
}
