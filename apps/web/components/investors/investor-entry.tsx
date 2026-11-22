"use client";

import { Ban, Check, CircleHelp, type LucideIcon } from "lucide-react";
import { useId, useState } from "react";
import type { InvestorEntryOut } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";
import { Tooltip } from "@/components/ui/tooltip";
import {
  classifyCompatibility,
  COMPATIBILITY_LABEL,
  type Compatibility,
  compatibilityReason,
  formatAmountUsd,
  fundingLabel,
  roundLabel,
  sentence,
} from "./format";
import { type RoundAxis, RoundStrip } from "./round-axis";
import { RoundSource } from "./round-source";

type Round = InvestorEntryOut["comparable_rounds"][number];

const VISIBLE_ROUNDS = 3;

/** Company, round, date and amount in fixed columns, so a list of rounds reads down. */
const ROUND_COLUMNS =
  "grid min-w-0 flex-1 grid-cols-3 gap-x-4 gap-y-1 sm:min-w-88 sm:grid-cols-[minmax(0,1fr)_5.5rem_6.5rem_4rem]";

function RoundRow({ round }: { round: Round }) {
  const type = roundLabel(round.round_type);
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
      <div className={ROUND_COLUMNS}>
        <span className="col-span-3 text-ink sm:col-span-1">{round.company_name}</span>
        <span className={type ? "text-ink-secondary" : "text-ink-muted"}>
          {type ?? "Not recorded"}
          {type ? null : <span className="sr-only"> round type</span>}
        </span>
        <span className="font-mono text-xs text-ink">{formatDate(round.date)}</span>
        <span
          className={cn(
            "font-mono text-xs sm:text-right",
            round.amount_usd == null ? "text-ink-muted" : "text-ink",
          )}
        >
          {round.amount_usd == null ? (
            <>
              <span aria-hidden>–</span>
              <span className="sr-only">Amount not recorded</span>
            </>
          ) : (
            formatAmountUsd(round.amount_usd)
          )}
        </span>
      </div>
      <RoundSource
        source={round.source}
        asOf={round.date}
        company={round.company_name}
        companyId={round.company_id}
        evidenceId={round.evidence_id}
        className="shrink-0"
      />
    </li>
  );
}

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
function CompatibilityMark({ value }: { value: Compatibility }) {
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
      {COMPATIBILITY_LABEL[value]}
    </span>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <dt className="text-xs text-ink-muted">{children}</dt>;
}

/**
 * One investor in the shortlist. A ledger row, not a card: the name and its two leading
 * facts, the dated rounds that put it on the list, and what the record does and does not
 * say. There is no contact detail and no control that sends anything.
 */
export function InvestorEntry({
  entry,
  axis,
  fundingSought,
  scope,
  duplicates,
  index,
}: {
  entry: InvestorEntryOut;
  axis: RoundAxis | null;
  fundingSought: string;
  /** Search date and scope, always shown beside "latest sector investment found". */
  scope: string;
  /** Other entries that may be the same firm. Flagged, never merged. */
  duplicates: InvestorEntryOut[];
  index: number;
}) {
  const [showAll, setShowAll] = useState(false);
  const roundsId = useId();
  const rounds = [...entry.comparable_rounds].sort((a, b) => b.date.localeCompare(a.date));
  const visible = showAll ? rounds : rounds.slice(0, VISIBLE_ROUNDS);
  const extra = rounds.length - VISIBLE_ROUNDS;
  const latest = formatDate(entry.latest_sector_investment_found);
  const compatibility = classifyCompatibility(entry.funding_kind_compatibility);

  return (
    <li
      id={entry.id}
      className="grid animate-row-in scroll-mt-24 grid-cols-[2rem_minmax(0,1fr)] gap-x-3 border-b border-line px-4 py-5 last:border-b-0 motion-reduce:animate-none sm:px-5"
      style={{ animationDelay: `${Math.min(index, 5) * 40}ms` }}
    >
      <span className="pt-1 font-mono text-sm text-ink-muted">
        <span className="sr-only">Rank </span>
        {entry.rank}
      </span>

      <div className="flex min-w-0 flex-col gap-4">
        <div className="grid items-start gap-x-6 gap-y-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex flex-col gap-1">
            <h3 className="text-lg font-medium text-ink">{entry.investor_name}</h3>
            <p className="text-dense text-ink-secondary">
              {plural(rounds.length, "comparable investment")}
              <span aria-hidden className="text-ink-muted">
                {" · "}
              </span>
              latest sector investment found{" "}
              <span className="font-mono text-xs text-ink">{latest ?? "none"}</span>
            </p>
          </div>
          {axis ? <RoundStrip axis={axis} entry={entry} className="hidden lg:block" /> : null}
        </div>

        <div className="grid gap-x-8 gap-y-4 text-dense xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <section className="flex min-w-0 flex-col gap-1">
            <h4 className="text-xs text-ink-muted">Comparable companies backed</h4>
            <ul id={roundsId} className="flex flex-col divide-y divide-line">
              {visible.map((round, i) => (
                <RoundRow key={`${round.company_id}-${round.date}-${i}`} round={round} />
              ))}
            </ul>
            {extra > 0 ? (
              <button
                type="button"
                onClick={() => setShowAll((value) => !value)}
                aria-expanded={showAll}
                aria-controls={roundsId}
                className="self-start rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
              >
                {showAll ? "Show fewer" : `+ ${extra} more`}
              </button>
            ) : null}
          </section>

          <dl className="flex min-w-0 flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Label>Latest sector investment found</Label>
              <dd className="text-ink">
                <span className="font-mono text-xs">{latest ?? "None in this search"}</span>
                <span className="block text-xs text-ink-secondary">
                  {scope}. A later round outside that scope would not show here.
                </span>
              </dd>
            </div>

            <div className="flex flex-col gap-1">
              <Label>Funding kind · {fundingLabel(fundingSought)}</Label>
              <dd className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ink">
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
          </dl>
        </div>

        {duplicates.length > 0 ? (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-dashed border-line-strong pt-3 text-dense text-ink-secondary">
            {duplicates.map((other) => (
              <Tooltip
                key={other.id}
                content="These investor names may refer to the same firm, but DealProof keeps them separate unless confirmed."
              >
                <a
                  href={`#${other.id}`}
                  className="rounded-xs underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink"
                >
                  Possible duplicate of “{other.investor_name}” · not merged
                </a>
              </Tooltip>
            ))}
          </p>
        ) : null}
      </div>
    </li>
  );
}
