"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { caseHref } from "@/components/app-shell/nav";
import { DispositionStamp, SourceChip } from "@/components/dealproof";
import {
  Button,
  Panel,
  PanelBody,
  PanelFooter,
  PanelGrid,
  PanelGridItem,
  PanelHeader,
  TextLink,
} from "@/components/ui";
import { ApiError, type SourceRef } from "@/lib/api/client";
import {
  getHome,
  verifyTarget,
  type Fact,
  type FundItem,
  type HomeCompany,
  type HomeFunds,
  type HomeOut,
  type HomeTargets,
  type TargetItem,
} from "@/lib/api/org";
import { formatCredits, formatDate, formatDateTime, plural } from "@/lib/format";
import type { Evidence } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

function toEvidence(source: SourceRef, fact: Pick<Fact, "as_of" | "value">): Evidence {
  const isUrl = /^https?:\/\//.test(source.url_or_endpoint);
  return {
    source: {
      id: source.source_id,
      provider: source.provider,
      label: source.label,
      url: isUrl ? source.url_or_endpoint : null,
      request: isUrl ? null : source.url_or_endpoint,
      retrieved_at: source.retrieved_at,
      as_of: fact.as_of ?? null,
      reliability: source.source_class,
    },
    value: fact.value === null ? null : String(fact.value),
  };
}

/** Where a value came from: the record's chip, or "Stated" with the date it was confirmed. */
function FactChip({ fact, compact = false }: { fact: Fact; compact?: boolean }) {
  if (fact.source) return <SourceChip evidence={toEvidence(fact.source, fact)} compact={compact} />;
  if (fact.origin === "stated") {
    return (
      <span className="text-xs text-ink-muted">
        Stated by you{fact.confirmed_at ? <span className="font-mono text-2xs"> · {formatDate(fact.confirmed_at)}</span> : null}
      </span>
    );
  }
  return null;
}

const figure = (fact: Fact) =>
  typeof fact.value === "number" ? `${fact.is_estimate ? "~" : ""}${fact.value.toLocaleString("en-US")}` : (fact.value ?? "–");

function CompanyCard({ company, home }: { company: HomeCompany; home: HomeOut }) {
  const research = home.research;
  return (
    <Panel aria-labelledby="home-company">
      <PanelHeader
        id="home-company"
        title="Your company"
        meta={company.domain ?? undefined}
        action={<FactChip fact={company.name} />}
      />
      <PanelBody className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-base font-medium text-ink">{company.name.value}</p>
          {company.one_line ? (
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-dense text-ink-secondary">
              {company.one_line.value}
              <FactChip fact={company.one_line} compact />
            </p>
          ) : null}
        </div>
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-3 xl:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,2fr)]">
          {company.kpis.map((kpi) => (
            <div key={kpi.key} className="flex min-w-0 flex-col gap-1 bg-surface px-4 py-3">
              <dt className="text-xs text-ink-muted">{kpi.label}</dt>
              <dd className="flex flex-col items-start gap-1">
                <span
                  className={cn(
                    "wrap-anywhere text-ink",
                    kpi.key === "looking_for" ? "text-dense" : "font-mono text-lg font-medium",
                    kpi.fact.is_estimate && "underline-estimate",
                  )}
                >
                  {figure(kpi.fact)}
                </span>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-secondary">
                  {kpi.fact.is_estimate ? "Estimate" : null}
                  {kpi.sub}
                  <FactChip fact={kpi.fact} compact />
                </span>
              </dd>
            </div>
          ))}
        </dl>
        {research?.angles.length ? (
          <p className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            Searched for
            {research.angles.map((angle) => (
              <span key={angle.key} className="rounded-xs border border-line bg-surface-raised px-2 py-0.5 text-ink-secondary">
                {angle.label}
              </span>
            ))}
          </p>
        ) : null}
      </PanelBody>
      {research?.finished_at ? (
        <PanelFooter>
          <span>
            Research <span className="font-mono">{formatDateTime(research.finished_at)}</span> ·{" "}
            <span className="font-mono">{formatCredits(research.cost.credits)}</span> of{" "}
            <span className="font-mono">{formatCredits(research.cost.budget_credits)}</span> credits ·{" "}
            <span className="font-mono">${research.cost.usd.toFixed(2)}</span> model usage, counted apart
          </span>
        </PanelFooter>
      ) : null}
    </Panel>
  );
}

/** Fit is solid ink; the assessable share is hatched. The two never read as one figure. */
function Strip({ value, hatched = false, label }: { value: number | null; hatched?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2">
      <span className="w-9 text-right font-mono text-xs font-medium text-ink">
        {value === null ? "–" : hatched ? `${Math.round(value)}%` : Math.round(value)}
      </span>
      <span role="img" aria-label={label} className="block h-2 w-20 overflow-hidden rounded-xs bg-surface-sunken">
        <span
          className={cn("block h-full rounded-xs", hatched ? "hatch-dense border-r border-not-checked-line" : "bg-ink")}
          style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }}
        />
      </span>
    </span>
  );
}

function TargetRow({ item, rank }: { item: TargetItem; rank: number }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setPending(true);
    setError(null);
    try {
      const created = await verifyTarget(item);
      router.push(caseHref(created.id));
    } catch {
      setError("The case was not opened. Nothing was changed");
      setPending(false);
    }
  }

  const chips = item.reasons.filter((reason) => reason.state === "supported").slice(0, 3);
  return (
    <li className="grid gap-x-4 gap-y-2 px-4 py-3 md:grid-cols-[1.5rem_minmax(0,1fr)_auto_auto] md:items-start">
      <span className="font-mono text-xs text-ink-muted max-md:hidden">{rank}</span>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-sm font-medium text-ink">{item.name}</p>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-secondary">
          {item.location?.value ?? "Location not on record"}
          {item.headcount ? <span className="underline-estimate">{figure(item.headcount)} people</span> : null}
          {item.location ? <FactChip fact={item.location} compact /> : null}
        </p>
        {item.headline ? <p className="text-dense text-ink">{item.headline}</p> : null}
        <p className="flex flex-wrap gap-1 text-xs">
          {chips.map((reason) => (
            <span key={reason.kind} className="rounded-xs border border-line bg-surface-raised px-2 py-0.5 text-ink-secondary">
              {reason.kind.replaceAll("_", " ")}
            </span>
          ))}
          {item.unknowns.length > 0 ? (
            <span className="rounded-xs border border-dashed border-not-checked-line px-2 py-0.5 text-ink-muted">
              Unknown: {item.unknowns.join(", ").toLowerCase()}
            </span>
          ) : null}
        </p>
        {error ? (
          <p role="alert" className="text-xs text-ink-secondary">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1">
        <Strip value={item.fit} label={item.fit === null ? "Fit unavailable" : `Fit ${item.fit} of 100`} />
        <Strip value={item.assessable_pct} hatched label={`${item.assessable_pct}% of criteria assessable`} />
      </div>
      <div className="flex flex-col items-start gap-1 md:items-end">
        {item.case ? (
          <>
            {item.case.disposition ? <DispositionStamp disposition={item.case.disposition} size="sm" /> : null}
            <Button asChild size="sm">
              <Link href={caseHref(item.case.id)}>Open case</Link>
            </Button>
          </>
        ) : (
          <Button size="sm" onClick={verify} disabled={pending}>
            {pending ? "Opening case" : "Verify"}
          </Button>
        )}
      </div>
    </li>
  );
}

function Targets({ targets }: { targets: HomeTargets }) {
  const largest = Math.max(1, ...targets.regions.map((region) => region.count));
  return (
    <PanelGrid id="fits">
      <PanelGridItem span={8}>
        <Panel aria-labelledby="home-fits">
          <PanelHeader id="home-fits" title="Best acquisition fits" meta={targets.total} />
          <PanelBody flush>
            <p className="flex flex-wrap gap-x-4 border-b border-line px-4 py-2 text-xs text-ink-muted">
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="h-2 w-4 rounded-xs bg-ink" /> Fit, 0 to 100
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="hatch-dense h-2 w-4 rounded-xs" /> Share of criteria assessable
              </span>
            </p>
            <ol className="divide-y divide-line">
              {targets.items.map((item, index) => (
                <TargetRow key={item.candidate_id} item={item} rank={index + 1} />
              ))}
            </ol>
          </PanelBody>
          <PanelFooter className="flex-wrap gap-x-4">
            <span>Fit is a match to your stated criteria, not a forecast</span>
            {targets.thesis_id ? (
              <TextLink href={`/app/discover/${encodeURIComponent(targets.thesis_id)}`}>View all {targets.total}</TextLink>
            ) : null}
          </PanelFooter>
        </Panel>
      </PanelGridItem>
      <PanelGridItem span={4}>
        <Panel aria-labelledby="home-regions">
          <PanelHeader id="home-regions" title="Where they are" meta={targets.regions.length} />
          <PanelBody flush>
            <ul className="py-1">
              {targets.regions.map((region) => (
                <li key={region.label} className="grid grid-cols-[minmax(0,1fr)_5rem_1.5rem] items-center gap-3 px-4 py-2 text-dense text-ink">
                  <span className="truncate">
                    {region.label}
                    {region.is_own ? <span className="text-xs text-ink-muted"> · you are here</span> : null}
                  </span>
                  <span aria-hidden className="h-2">
                    <span className="block h-full min-w-0.5 rounded-r-xs bg-ink-muted" style={{ width: `${(region.count / largest) * 100}%` }} />
                  </span>
                  <span className="text-right font-mono text-xs font-medium">{region.count}</span>
                </li>
              ))}
            </ul>
          </PanelBody>
          <PanelFooter>Headquarters on record. Not a map: the record holds a place name only</PanelFooter>
        </Panel>
      </PanelGridItem>
    </PanelGrid>
  );
}

function RoundTimeline({ fund, timeline }: { fund: FundItem; timeline: NonNullable<HomeFunds["timeline"]> }) {
  const from = Date.parse(timeline.from);
  const to = Date.parse(timeline.to);
  const years: number[] = [];
  for (let year = new Date(from).getUTCFullYear(); year <= new Date(to).getUTCFullYear(); year += 1) years.push(year);
  const at = (time: number) => `${Math.min(1, Math.max(0, (time - from) / (to - from || 1))) * 100}%`;
  return (
    <div aria-hidden className="flex flex-col gap-1">
      <div className="relative h-4">
        {years.map((year) => (
          <span key={year} className="absolute top-0 font-mono text-2xs text-ink-muted" style={{ left: at(Date.UTC(year, 0, 1)) }}>
            {year}
          </span>
        ))}
      </div>
      <div className="relative h-4">
        <span className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
        {years.map((year) => (
          <span key={year} className="absolute top-1 h-2 w-px bg-line-strong" style={{ left: at(Date.UTC(year, 0, 1)) }} />
        ))}
        <span className="absolute top-0 right-0 h-4 border-l border-dashed border-ink-muted" />
        {fund.comparable_rounds.map((round) => (
          <span
            key={`${round.company_id}-${round.date}`}
            className="absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink ring-2 ring-surface"
            style={{ left: at(Date.parse(round.date)) }}
          />
        ))}
      </div>
    </div>
  );
}

const roundWord = (value: string | null) =>
  value ? value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()).replace(/ ([a-z])$/, (_, c: string) => ` ${c.toUpperCase()}`) : "Round";
const usd = (amount: number | null) => (amount === null ? "–" : `$${(amount / 1_000_000).toFixed(1)}M`);

function Funds({ funds }: { funds: HomeFunds }) {
  const [selectedId, setSelectedId] = useState<string | null>(funds.items[0]?.entry_id ?? null);
  const selected = funds.items.find((item) => item.entry_id === selectedId) ?? funds.items[0];
  return (
    <PanelGrid id="funds">
      <PanelGridItem span={4}>
        <Panel aria-labelledby="home-funds">
          <PanelHeader id="home-funds" title="Funds to approach" meta={funds.total} />
          <PanelBody flush>
            <ol className="divide-y divide-line">
              {funds.items.map((fund) => (
                <li key={fund.entry_id}>
                  <button
                    type="button"
                    aria-pressed={fund.entry_id === selected?.entry_id}
                    onClick={() => setSelectedId(fund.entry_id)}
                    className={cn(
                      "focus-inset grid w-full grid-cols-[1.5rem_minmax(0,1fr)_auto] items-baseline gap-x-2 px-4 py-3 text-left transition-colors",
                      fund.entry_id === selected?.entry_id ? "selected-bar bg-accent-tint" : "hover:bg-surface-raised",
                    )}
                  >
                    <span className="font-mono text-xs text-ink-muted">{fund.rank}</span>
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="truncate text-sm font-medium text-ink">{fund.investor_name}</span>
                      <span className="text-xs text-ink-secondary">
                        {plural(fund.comparable_rounds.length, "comparable round")} ·{" "}
                        {plural(fund.stage_fit.in_window, "round")} at your stage
                      </span>
                    </span>
                    <span className="font-mono text-xs text-ink-secondary">{formatDate(fund.latest_comparable?.slice(0, 7)) ?? "undated"}</span>
                  </button>
                </li>
              ))}
            </ol>
          </PanelBody>
          <PanelFooter>
            Ranked by past investments in comparable companies. This describes what each fund has done. It
            does not predict whether they will invest
          </PanelFooter>
        </Panel>
      </PanelGridItem>
      <PanelGridItem span={8}>
        {selected ? (
          <Panel aria-labelledby="home-fund-detail" aria-live="polite">
            <PanelHeader id="home-fund-detail" title={selected.investor_name} meta={selected.headline ?? undefined} />
            <PanelBody className="flex flex-col gap-4">
              {funds.timeline ? <RoundTimeline fund={selected} timeline={funds.timeline} /> : null}
              <ul className="divide-y divide-line border-y border-line text-dense">
                {selected.comparable_rounds.map((round) => (
                  <li key={`${round.company_id}-${round.date}`} className="grid grid-cols-2 items-center gap-x-4 gap-y-1 py-2 sm:grid-cols-[minmax(0,1fr)_6rem_6.5rem_4rem_auto]">
                    <span className="truncate text-ink">{round.company_name}</span>
                    <span className="text-ink-secondary">{roundWord(round.round_type)}</span>
                    <span className="font-mono text-xs text-ink">{formatDate(round.date)}</span>
                    <span className="font-mono text-xs text-ink sm:text-right">{usd(round.amount_usd)}</span>
                    <SourceChip evidence={toEvidence(round.source, { as_of: round.date, value: roundWord(round.round_type) })} compact />
                  </li>
                ))}
              </ul>
              <dl className="grid gap-x-8 gap-y-3 text-dense sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-ink-muted">Stage fit</dt>
                  <dd className="text-ink">
                    {selected.stage_fit.in_window} of {selected.stage_fit.of} rounds within one stage of yours
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-muted">Median round</dt>
                  <dd className="text-ink">
                    {selected.cheque_fit.median_round_usd === null
                      ? "Unknown: fewer than 2 amounts are disclosed"
                      : `${usd(selected.cheque_fit.median_round_usd)} of ${selected.cheque_fit.disclosed} disclosed`}
                    <span className="block text-xs text-ink-secondary">{selected.cheque_fit.note}</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-muted">Unknown</dt>
                  <dd className="text-ink-secondary">{selected.unknowns.join(", ") || "Nothing flagged in the records read"}</dd>
                </div>
              </dl>
            </PanelBody>
            <PanelFooter>
              An approach is drafted for a named person to approve. DealProof sends nothing by itself and
              holds no investor contact details
            </PanelFooter>
          </Panel>
        ) : null}
      </PanelGridItem>
    </PanelGrid>
  );
}

function SignalsAndNext({ home }: { home: HomeOut }) {
  const { signals, next } = home;
  if (signals.items.length === 0 && next.length === 0) return null;
  return (
    <PanelGrid>
      <PanelGridItem span={8}>
        {signals.items.length > 0 ? (
          <Panel aria-labelledby="home-signals">
            <PanelHeader id="home-signals" title="Market signals" meta={signals.items.length} />
            <PanelBody flush>
              <ul className="divide-y divide-line">
                {signals.items.map((signal) => (
                  <li key={`${signal.company_name}-${signal.at}-${signal.text}`} className="grid gap-x-4 gap-y-1 px-4 py-2 text-dense sm:grid-cols-[6rem_minmax(0,12rem)_minmax(0,1fr)_auto] sm:items-center">
                    <span className="font-mono text-xs text-ink-secondary">{formatDate(signal.at) ?? "Undated"}</span>
                    <span className="truncate font-medium text-ink">{signal.company_name}</span>
                    <span className="text-ink">
                      {signal.text}
                      {signal.is_estimate ? <span className="text-xs text-ink-muted"> · Estimate</span> : null}
                    </span>
                    <SourceChip evidence={toEvidence(signal.source, { as_of: signal.at, value: signal.text })} compact />
                  </li>
                ))}
              </ul>
            </PanelBody>
            <PanelFooter>
              {[...signals.filter.sectors, ...signals.filter.countries].join(" · ")} · last {signals.filter.months} months
            </PanelFooter>
          </Panel>
        ) : null}
      </PanelGridItem>
      <PanelGridItem span={4}>
        {next.length > 0 ? (
          <Panel aria-labelledby="home-next">
            <PanelHeader id="home-next" title="Next" meta={next.length} />
            <PanelBody flush>
              <ul className="divide-y divide-line">
                {next.slice(0, 3).map((item) => (
                  <li key={item.kind} className="flex flex-col gap-0.5 px-4 py-3">
                    {item.href ? (
                      <Link href={item.href} className="rounded-xs text-dense font-medium text-ink transition-colors hover:text-accent">
                        {item.label}
                      </Link>
                    ) : (
                      <span className="text-dense font-medium text-ink">{item.label}</span>
                    )}
                    {item.sub ? <span className="text-xs text-ink-muted">{item.sub}</span> : null}
                  </li>
                ))}
              </ul>
            </PanelBody>
          </Panel>
        ) : null}
      </PanelGridItem>
    </PanelGrid>
  );
}

/**
 * The research region of Overview: the company, its best acquisition fits and the funds
 * to approach, with the source on every fact. It draws only what `GET /home` returns. A
 * deployment without that route, or a workspace without a profile, shows nothing here and
 * the book of work below is unchanged.
 */
export function ResearchHome() {
  const [state] = useLoad(
    "home",
    async () => {
      try {
        return await getHome();
      } catch (error) {
        if (error instanceof ApiError && (error.status === 404 || error.status === 405)) return null;
        throw error;
      }
    },
    "The research was not returned",
  );
  if (state.status !== "ready" || !state.data?.company) return null;
  const home = state.data;
  const company = home.company as HomeCompany;

  return (
    <div className="flex flex-col gap-4">
      <CompanyCard company={company} home={home} />
      {home.targets.status === "ready" && home.targets.items.length > 0 ? <Targets targets={home.targets} /> : null}
      {home.funds.status === "ready" && home.funds.items.length > 0 ? <Funds funds={home.funds} /> : null}
      <SignalsAndNext home={home} />
      <h2 className="border-t border-line pt-4 text-sm font-medium text-ink">Your work</h2>
    </div>
  );
}
