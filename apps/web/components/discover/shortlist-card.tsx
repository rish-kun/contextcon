"use client";

import { ArrowRight } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createCase, type ShortlistItemOut } from "@/lib/api/client";
import { formatDate, formatDateTime, plural } from "@/lib/format";
import { rise, staggerDelay, transition } from "@/lib/transitions";
import type { Evidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { CriteriaStrip, Fact, SourceLine } from "@/components/dealproof";
import { seriesSummary, Sparkline } from "@/components/insight";
import {
  errorText,
  evidenceIndex,
  factEstimate,
  factEvidence,
  formatAmountUsd,
  roundLabel,
  toFit,
  toSource,
} from "./adapt";

/** How many job postings and funding rounds a card lists before "+N more". */
const LIST_LIMIT = 3;

/** Echoes the strip's cells, so a list reads the same way the strip does. */
export function Marker({ kind }: { kind: "met" | "not_met" | "unknown" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-1.5 size-2 shrink-0 border",
        kind === "met" && "border-ink bg-ink",
        kind === "not_met" && "border-ink bg-surface",
        kind === "unknown" && "hatch-dense border-dashed border-not-checked-line",
      )}
    />
  );
}

/** A field the sources did not return. Said in words, never left blank. */
function Missing({ children = "Not returned by the sources searched" }: { children?: string }) {
  return <span className="text-ink-muted">{children}</span>;
}

/** Marks a link in the chain that has no excerpt behind it. */
export function NoExcerpt() {
  return (
    <span className="rounded-xs border border-dashed border-not-checked-line px-1 font-mono text-2xs text-not-checked">
      no evidence excerpt attached
    </span>
  );
}

function FactRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-[7rem_minmax(0,1fr)]">
      <dt className="text-dense text-ink-muted">{label}</dt>
      <dd className="flex min-w-0 flex-col items-start gap-1 text-dense text-ink">{children}</dd>
    </div>
  );
}

/** "18.5% more people…" in words, so an estimate's tilde reads cleanly before the figure. */
function HeadcountChange({ value }: { value: number }) {
  const rounded = Math.round(Math.abs(value) * 10) / 10;
  if (rounded === 0) return <>Headcount unchanged from 12 months earlier</>;
  return (
    <>
      <span className="font-mono">{rounded}%</span> {value > 0 ? "more" : "fewer"} people than 12
      months earlier
    </>
  );
}

function Profile({ item }: { item: ShortlistItemOut }) {
  const { card } = item;
  const rounds = card.funding_rounds.slice(0, LIST_LIMIT);
  const moreRounds = card.funding_rounds.length - rounds.length;

  return (
    <dl className="flex flex-col gap-3">
      <FactRow label="Business">
        {card.business ? (
          <Fact evidence={factEvidence(card.business)} estimate={factEstimate(card.business)}>
            {card.business.value}
          </Fact>
        ) : (
          <Missing />
        )}
      </FactRow>
      <FactRow label="Location">
        {card.location ? (
          <Fact evidence={factEvidence(card.location)} estimate={factEstimate(card.location)}>
            {card.location.value}
          </Fact>
        ) : (
          <Missing />
        )}
      </FactRow>
      <FactRow label="Funding history">
        {card.total_funding_usd ? (
          <Fact
            evidence={factEvidence(card.total_funding_usd)}
            estimate={factEstimate(card.total_funding_usd)}
          >
            <span className="font-mono">{formatAmountUsd(card.total_funding_usd.value)}</span>{" "}
            raised in total
          </Fact>
        ) : null}
        {rounds.map((round, index) => (
          <Fact
            key={round.evidence_id ?? index}
            evidence={[{ id: round.evidence_id ?? undefined, source: toSource(round.source, round.date) }]}
          >
            {roundLabel(round.round_type)}
            <span className="font-mono text-xs text-ink-secondary">
              {" · "}
              {formatDate(round.date) ?? "date unknown"}
              {round.amount_usd !== null ? ` · ${formatAmountUsd(round.amount_usd)}` : " · amount not recorded"}
            </span>
            {round.investors.length > 0 ? (
              <span className="text-ink-secondary"> · {round.investors.join(", ")}</span>
            ) : null}
          </Fact>
        ))}
        {moreRounds > 0 ? (
          <span className="font-mono text-2xs text-ink-muted">+{moreRounds} more on record</span>
        ) : null}
        {!card.total_funding_usd && rounds.length === 0 ? (
          <Missing>No funding record returned</Missing>
        ) : null}
      </FactRow>
    </dl>
  );
}

/** Headcount and hiring sit under "Operating signals": they never stand in for revenue. */
function OperatingSignals({ item }: { item: ShortlistItemOut }) {
  const { card } = item;
  const hiring = card.hiring;
  const postings = hiring?.postings.slice(0, LIST_LIMIT) ?? [];
  const morePostings = (hiring?.postings.length ?? 0) - postings.length;
  const hasHiring = Boolean(hiring && (hiring.openings || hiring.recent_titles || postings.length));
  const trend = (card.headcount_series?.points ?? []).map((point) => ({
    date: point.date,
    value: point.employee_count,
  }));

  return (
    <dl className="flex flex-col gap-3">
      <FactRow label="Size">
        {card.headcount ? (
          <span className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1">
            <Fact evidence={factEvidence(card.headcount)} estimate={factEstimate(card.headcount)}>
              <span className="font-mono">{card.headcount.value.toLocaleString("en-US")}</span> people
            </Fact>
            {trend.length > 1 && card.headcount_series ? (
              <span className="flex flex-wrap items-center gap-2">
                <Sparkline
                  points={trend}
                  estimate
                  label={`Estimated headcount, ${seriesSummary(trend, "people")}`}
                />
                {/* The series has its own source, cited at its latest dated point. */}
                <SourceLine
                  max={1}
                  evidence={[
                    {
                      source: toSource(card.headcount_series.source, trend[trend.length - 1].date),
                      field_path: "headcount.timeseries",
                      value: `${trend.length} dated points`,
                    },
                  ]}
                />
              </span>
            ) : null}
          </span>
        ) : (
          <Missing />
        )}
      </FactRow>
      <FactRow label="Growth">
        {card.headcount_growth_yoy_pct ? (
          <Fact
            evidence={factEvidence(card.headcount_growth_yoy_pct)}
            estimate={factEstimate(card.headcount_growth_yoy_pct)}
          >
            <HeadcountChange value={card.headcount_growth_yoy_pct.value} />
          </Fact>
        ) : (
          <Missing>No headcount history returned</Missing>
        )}
      </FactRow>
      <FactRow label="Hiring activity">
        {hiring?.openings ? (
          <Fact evidence={factEvidence(hiring.openings)} estimate={factEstimate(hiring.openings)}>
            <span className="font-mono">{hiring.openings.value}</span>{" "}
            {hiring.openings.value === 1 ? "open role" : "open roles"}
          </Fact>
        ) : null}
        {hiring?.recent_titles && hiring.recent_titles.value.length > 0 ? (
          <Fact
            evidence={factEvidence(hiring.recent_titles)}
            estimate={factEstimate(hiring.recent_titles)}
          >
            Recent titles: {hiring.recent_titles.value.join(", ")}
          </Fact>
        ) : null}
        {postings.map((posting, index) => (
          <Fact
            key={`${posting.title}-${index}`}
            evidence={[{ source: toSource(posting.source, posting.date_added) }]}
          >
            {posting.title}
            {posting.location ? (
              <span className="text-ink-secondary"> · {posting.location}</span>
            ) : null}
          </Fact>
        ))}
        {morePostings > 0 ? (
          <span className="font-mono text-2xs text-ink-muted">+{morePostings} more postings</span>
        ) : null}
        {!hasHiring ? <Missing>No hiring data returned</Missing> : null}
      </FactRow>
    </dl>
  );
}

function Reasons({ item }: { item: ShortlistItemOut }) {
  const index = evidenceIndex(item);
  const results = new Map(item.criterion_results.map((result) => [result.criterion_id, result]));

  if (item.card.reasons.length === 0) {
    return <p className="text-dense text-ink-muted">No criterion is recorded as met</p>;
  }

  return (
    <ul className="flex flex-col gap-3">
      {item.card.reasons.map((reason, position) => {
        const evidence = reason.evidence_ids
          .map((id) => index.get(id))
          .filter((entry): entry is Evidence => entry !== undefined);
        const result = reason.criterion_id ? results.get(reason.criterion_id) : undefined;
        return (
          <li key={`${reason.text}-${position}`} className="flex gap-2">
            <Marker kind="met" />
            <div className="flex min-w-0 flex-col items-start gap-1 text-dense">
              <p className="text-ink">
                {reason.text}
                {result?.kind === "must" ? (
                  <span className="pl-2 font-mono text-2xs text-ink-muted">must-have</span>
                ) : null}
              </p>
              {evidence.length > 0 ? (
                <SourceLine evidence={evidence} />
              ) : (
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-secondary">
                  {result ? result.reason : null}
                  <NoExcerpt />
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Unknowns({ item }: { item: ShortlistItemOut }) {
  if (item.card.unknowns.length === 0) {
    return <p className="text-dense text-ink-muted">Nothing listed as unknown</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {item.card.unknowns.map((unknown) => (
        <li key={unknown} className="flex gap-2 text-dense text-ink">
          <Marker kind="unknown" />
          {unknown}
        </li>
      ))}
    </ul>
  );
}

/**
 * "Verify this company" opens a case from the shortlist item and goes to it. A company
 * that already has a case links to that case instead of opening a second one.
 */
function VerifyAction({ item, thesisId }: { item: ShortlistItemOut; thesisId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (item.case_id) {
    return (
      <div className="flex flex-col items-start gap-1 sm:items-end">
        <Button asChild>
          <Link href={`/app/cases/${encodeURIComponent(item.case_id)}`}>
            Open case
            <Icon icon={ArrowRight} />
          </Link>
        </Button>
        <p className="text-xs text-ink-muted">A case is already open for this company</p>
      </div>
    );
  }

  async function verify() {
    setPending(true);
    setError(null);
    try {
      const created = await createCase({ shortlist_item_id: item.id, thesis_id: thesisId });
      router.push(`/app/cases/${encodeURIComponent(created.id)}`);
    } catch (caught) {
      setError(errorText(caught));
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <Button onClick={verify} disabled={pending} aria-label={`Verify ${item.name}`}>
        {pending ? "Opening the case" : "Verify this company"}
        <Icon icon={ArrowRight} />
      </Button>
      {error ? (
        <p role="alert" className="max-w-xs text-xs text-contradicted sm:text-right">
          The case could not be opened: {error}
        </p>
      ) : null}
    </div>
  );
}

const sectionHead = "text-xs font-medium text-ink-secondary";

/**
 * One company on the shortlist. The fit strip leads, because it is the one thing that
 * must not be misread; every fact under it ends in its source and as-of date.
 */
export function ShortlistCard({
  item,
  thesisId,
  index,
}: {
  item: ShortlistItemOut;
  thesisId: string;
  /** Position in the list, for the entrance stagger. */
  index: number;
}) {
  const headingId = `shortlist-${item.id}`;
  const unknownMusts = item.criterion_results.filter(
    (result) => result.kind === "must" && result.state === "unknown",
  );
  const updated = formatDateTime(item.card.last_updated);

  return (
    <motion.article
      id={`company-${item.id}`}
      aria-labelledby={headingId}
      initial={{ opacity: 0, y: rise }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...transition.slow, delay: staggerDelay(index) }}
      className="scroll-mt-24 rounded-lg border border-line bg-surface"
    >
      <header className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6 sm:p-5">
        <div className="flex min-w-0 gap-3">
          {item.rank !== null ? (
            <span
              className="pt-1 font-mono text-sm text-ink-muted"
              aria-label={`Rank ${item.rank}`}
            >
              {String(item.rank).padStart(2, "0")}
            </span>
          ) : null}
          <div className="flex min-w-0 flex-col">
            <h3 id={headingId} className="text-xl font-medium text-ink">
              {item.name}
            </h3>
            {item.domain ? (
              <p className="font-mono text-xs break-all text-ink-muted">{item.domain}</p>
            ) : null}
          </div>
        </div>
        <VerifyAction item={item} thesisId={thesisId} />
      </header>

      <div className="flex flex-col gap-2 px-4 pb-4 sm:px-5 sm:pb-5">
        <CriteriaStrip fit={toFit(item)} legend={false} className="max-w-2xl" />
        {item.fit === null && item.fit_unavailable_reason ? (
          <p className="text-xs text-not-checked">{item.fit_unavailable_reason}</p>
        ) : null}
        {unknownMusts.length > 0 ? (
          <p className="flex max-w-2xl gap-2 text-xs text-ink-secondary">
            <Marker kind="unknown" />
            <span>
              {plural(unknownMusts.length, "must-have")} could not be assessed:{" "}
              {unknownMusts.map((result) => result.label).join("; ")}. An unknown
              must-have does not remove a company; it stays here until evidence settles it.
            </span>
          </p>
        ) : null}
      </div>

      <div className="grid border-t border-line lg:grid-cols-2 lg:divide-x lg:divide-line">
        <div className="flex flex-col gap-5 p-4 sm:p-5">
          <section className="flex flex-col gap-3">
            <h4 className={sectionHead}>Company</h4>
            <Profile item={item} />
          </section>
          <section className="flex flex-col gap-3">
            <h4 className={sectionHead}>Operating signals</h4>
            <OperatingSignals item={item} />
          </section>
        </div>
        <div className="flex flex-col gap-5 border-t border-line p-4 sm:p-5 lg:border-t-0">
          <section className="flex flex-col gap-3">
            <h4 className={sectionHead}>Why it is here</h4>
            <Reasons item={item} />
          </section>
          <section className="flex flex-col gap-3">
            <h4 className={sectionHead}>Unknown</h4>
            <Unknowns item={item} />
          </section>
        </div>
      </div>

      <footer className="border-t border-line px-4 py-2 font-mono text-2xs text-ink-muted sm:px-5">
        Last updated {updated ?? "at an unrecorded time"}
      </footer>
    </motion.article>
  );
}
