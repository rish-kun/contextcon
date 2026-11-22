"use client";

import Link from "next/link";
import { useState } from "react";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SourceLine } from "@/components/dealproof";
import {
  EventTimeline,
  formatAmountUsd,
  FundingRoundsTable,
  HeadcountTrend,
  KpiRow,
  PeopleRow,
  StatTile,
} from "@/components/insight";
import { eventNature, factEstimate, factEvidence, sourceEvidence, toEvidence } from "./adapt";
import { useCase } from "./case-context";

type Profile = NonNullable<CaseDetail["profile"]>;

const titleCase = (value: string) =>
  value
    .split("_")
    .map((word) => (word.length <= 1 ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1)))
    .join(" ");

const headcountPoints = (profile: Profile) =>
  (profile.headcount_series?.points ?? []).map((point) => ({
    date: point.date,
    value: point.employee_count,
  }));

/** "Chennai, India" from a long address: the last two real parts, without a trailing ISO code. */
export function shortPlace(address: string, country?: string | null): string {
  const parts = address
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part && !/^[A-Z]{2,3}$/.test(part));
  if (parts.length <= 2) return parts.join(", ") || address;
  const tail = parts.slice(-2);
  if (country && !tail.some((part) => part.toLowerCase() === country.toLowerCase())) {
    return `${parts[parts.length - 1]}, ${country}`;
  }
  return tail.join(", ");
}

/** One line under the company name: what it does and where, from the record. */
export function profileSummary(profile: Profile | null): string | null {
  if (!profile) return null;
  const parts = [
    ...(profile.industries?.value ?? []).slice(0, 2),
    profile.headquarters ? shortPlace(profile.headquarters.value, profile.country?.value) : profile.country?.value,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * The few figures a reader wants before opening a tab: when the company was formed, how
 * big it is estimated to be, and what it has raised. Each carries its source as a short
 * chip; the full source line is in the Overview tab. A figure the record does not hold is
 * said in words, never shown as zero.
 */
export function ProfileBand({ detail }: { detail: CaseDetail }) {
  const { profile } = detail;
  if (detail.identity.state !== "confirmed" || !profile) return null;

  const growth = profile.headcount_growth_yoy_pct;
  const founded = profile.incorporation_date ?? profile.year_founded;
  const rounds = profile.funding_rounds.length;
  const funding = profile.total_funding_usd;
  const hasFunding = Boolean(funding && funding.value > 0);

  return (
    <KpiRow label="Profile figures">
      {founded ? (
        <StatTile
          label={profile.incorporation_date ? "Incorporated" : "Founded"}
          value={
            profile.incorporation_date
              ? (formatDate(profile.incorporation_date.value) ?? profile.incorporation_date.value)
              : profile.year_founded?.value
          }
          evidence={factEvidence(founded)}
        />
      ) : (
        <StatTile label="Founded" missing="Not returned" />
      )}

      {profile.headcount ? (
        <StatTile
          label="Team size"
          value={profile.headcount.value.toLocaleString("en-US")}
          unit="people"
          estimate={factEstimate(profile.headcount)}
          note={
            growth
              ? `${growth.value > 0 ? "+" : growth.value < 0 ? "−" : ""}${Math.abs(growth.value)}% vs 12 months earlier`
              : undefined
          }
          evidence={factEvidence(profile.headcount)}
        />
      ) : (
        <StatTile label="Team size" missing="No estimate returned" />
      )}

      {funding && hasFunding ? (
        <StatTile
          label="Funding on record"
          value={formatAmountUsd(funding.value)}
          note={rounds > 0 ? plural(rounds, "dated round") : undefined}
          evidence={factEvidence(funding)}
        />
      ) : rounds > 0 ? (
        <StatTile label="Funding on record" value={plural(rounds, "round")} note="Amounts not recorded" />
      ) : (
        <StatTile
          label="Funding on record"
          missing="No rounds found"
          note={funding ? `Searched ${formatDate(funding.source.retrieved_at) ?? "at an unrecorded time"}` : undefined}
        />
      )}

      {profile.hiring?.openings ? (
        <StatTile
          label="Open roles"
          value={profile.hiring.openings.value}
          estimate={factEstimate(profile.hiring.openings)}
          evidence={factEvidence(profile.hiring.openings)}
        />
      ) : null}
    </KpiRow>
  );
}

/** The company's own description, two lines until asked for more, with where it came from. */
function About({ profile }: { profile: Profile }) {
  const [open, setOpen] = useState(false);
  const financialNote = profile.company_type
    ? `Judged as ${profile.company_type === "startup" ? "a startup" : "an established business"}`
    : null;
  if (!profile.description && !profile.headquarters) return null;
  const long = (profile.description?.value.length ?? 0) > 220;
  return (
    <div className="flex flex-col gap-2">
      <h3 className={sectionHead}>About</h3>
      <dl className="grid gap-x-8 gap-y-3 rounded-lg border border-line bg-surface p-4 text-dense lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {profile.description ? (
          <div className="flex min-w-0 flex-col items-start gap-1">
            <dt className="text-xs text-ink-muted">In the company&apos;s own words</dt>
            <dd className={cn("text-ink", !open && "line-clamp-2")}>{profile.description.value}</dd>
            {long ? (
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setOpen((value) => !value)}
                className="rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
              >
                {open ? "Show less" : "Show more"}
              </button>
            ) : null}
            <dd>
              <SourceLine evidence={factEvidence(profile.description)} max={1} />
            </dd>
          </div>
        ) : null}
        <div className="flex min-w-0 flex-col gap-3">
          {profile.headquarters ? (
            <div className="flex min-w-0 flex-col items-start gap-1">
              <dt className="text-xs text-ink-muted">Headquarters</dt>
              <dd className="text-ink">{profile.headquarters.value}</dd>
              <dd>
                <SourceLine evidence={factEvidence(profile.headquarters)} max={1} />
              </dd>
            </div>
          ) : null}
          {profile.industries && profile.industries.value.length > 0 ? (
            <div className="flex min-w-0 flex-col items-start gap-1">
              <dt className="text-xs text-ink-muted">Industry</dt>
              <dd className="text-ink">{profile.industries.value.join(", ")}</dd>
              <dd>
                <SourceLine evidence={factEvidence(profile.industries)} max={1} />
              </dd>
            </div>
          ) : null}
          {financialNote ? (
            <div className="flex min-w-0 flex-col items-start gap-1">
              <dt className="text-xs text-ink-muted">Company type</dt>
              <dd className="text-ink" title={profile.company_type_reason ?? undefined}>
                {financialNote}
              </dd>
            </div>
          ) : null}
        </div>
      </dl>
    </div>
  );
}

const sectionHead = "text-sm font-medium text-ink";

/**
 * The profile panels above the memo: who leads the company, how its estimated team size
 * has moved, what it has raised, and what has been announced or recorded lately. The
 * same facts are in the memo below in prose and tables; this is the scannable view.
 * Nothing here is printed, because the memo is the printed document.
 */
export function ProfilePanels({ detail }: { detail: CaseDetail }) {
  const { basePath } = useCase();
  const { profile } = detail;
  if (detail.identity.state !== "confirmed" || !profile) return null;

  const trend = headcountPoints(profile);
  const events = [...detail.events].sort((a, b) => b.event_date.localeCompare(a.event_date));
  const recent = events.slice(0, 4);

  return (
    <section aria-label="Profile at a glance" className="flex flex-col gap-6 print:hidden">
      <About profile={profile} />
      <div className="flex flex-col gap-2">
        <h3 className={sectionHead}>Founders and leadership</h3>
        <PeopleRow
          people={profile.people.map((person) => ({
            id: person.person_id ?? person.name,
            name: person.name,
            role: person.title
              ? { text: person.title.value, source: <SourceLine evidence={factEvidence(person.title)} max={1} /> }
              : null,
            history: person.history.map((role) => ({
              text: role.value,
              source: <SourceLine evidence={factEvidence(role)} max={1} />,
            })),
          }))}
        />
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex min-w-0 flex-col gap-2">
          <h3 className={sectionHead}>Operating signals</h3>
          <div className="rounded-lg border border-line bg-surface p-4">
            {profile.headcount_series ? (
              <HeadcountTrend
                points={trend}
                basis={profile.headcount_series.estimate_basis}
                evidence={sourceEvidence(profile.headcount_series.source, trend.at(-1)?.date ?? null)}
              />
            ) : (
              <HeadcountTrend points={[]} basis="" evidence={[]} />
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-2">
          <h3 className={sectionHead}>Funding rounds</h3>
          {profile.funding_rounds.length > 0 ? (
            <FundingRoundsTable
              caption={`Funding rounds on record for ${profile.name.value}`}
              rows={profile.funding_rounds.map((round, index) => ({
                id: round.evidence_id ?? `${round.date}-${index}`,
                round: round.round_type ? titleCase(round.round_type) : null,
                date: round.date,
                amountUsd: round.amount_usd,
                investors: round.investors,
                source: <SourceLine evidence={sourceEvidence(round.source, round.date)} max={1} />,
              }))}
            />
          ) : (
            <p className="rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-muted">
              No dated funding round returned by the sources searched
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className={sectionHead}>Recent events</h3>
          {events.length > 0 ? (
            <Link
              href={`${basePath}/events`}
              className="rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
            >
              All {plural(events.length, "dated event")}
            </Link>
          ) : null}
        </div>
        {recent.length > 0 ? (
          <EventTimeline
            items={recent.map((event) => ({
              id: event.id,
              date: event.event_date,
              title: event.title,
              kind: event.kind,
              nature: eventNature(event),
              source: <SourceLine evidence={[toEvidence(event.evidence)]} max={1} />,
            }))}
          />
        ) : (
          <p className="text-dense text-ink-muted">
            No dated public events were returned for this confirmed entity
          </p>
        )}
      </div>
    </section>
  );
}
