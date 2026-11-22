"use client";

import Link from "next/link";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { SourceLine } from "@/components/dealproof";
import {
  EventTimeline,
  formatAmountUsd,
  FundingRoundsTable,
  HeadcountTrend,
  KpiRow,
  PeopleRow,
  seriesSummary,
  Sparkline,
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

/**
 * What the company does, where, and how DealProof classed it. Each is a fact from a
 * record, so each ends in its source chip and as-of date; the class is DealProof's own
 * rule and says which rule.
 */
function ProfileFacts({ profile }: { profile: Profile }) {
  const items: { label: string; value: React.ReactNode; source: React.ReactNode }[] = [];
  if (profile.description) {
    items.push({
      label: "Business",
      value: profile.description.value,
      source: <SourceLine evidence={factEvidence(profile.description)} max={1} />,
    });
  }
  if (profile.industries && profile.industries.value.length > 0) {
    items.push({
      label: "Industry",
      value: (
        <span className="flex flex-wrap gap-1">
          {profile.industries.value.map((industry) => (
            <span key={industry} className="rounded-xs bg-surface-sunken px-2 py-0.5 text-xs text-ink-secondary">
              {industry}
            </span>
          ))}
        </span>
      ),
      source: <SourceLine evidence={factEvidence(profile.industries)} max={1} />,
    });
  }
  if (profile.headquarters) {
    const sameSource = profile.country?.source.source_id === profile.headquarters.source.source_id;
    items.push({
      label: "Headquarters",
      value: [profile.headquarters.value, sameSource ? profile.country?.value : null].filter(Boolean).join(", "),
      source: <SourceLine evidence={factEvidence(profile.headquarters)} max={1} />,
    });
  }
  if (profile.company_type) {
    items.push({
      label: "Judged as",
      value: profile.company_type === "startup" ? "A startup" : "An established business",
      source: (
        <span className="font-mono text-2xs text-ink-muted">
          DealProof rule · {profile.company_type_reason ?? "reason not recorded"}
        </span>
      ),
    });
  }
  if (items.length === 0) return null;
  return (
    <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 flex-col items-start gap-1">
          <dt className="text-xs text-ink-muted">{item.label}</dt>
          <dd className="text-dense text-ink">{item.value}</dd>
          <dd>{item.source}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The profile band in the case header: a description, tags, and a row of figures, each
 * with its source and as-of date. Team size and its change are estimates from
 * professional profiles and say so. Revenue, valuation and ownership have a tile only to
 * say they are not on record: the tile is hatched and names what would be needed.
 */
export function ProfileBand({ detail }: { detail: CaseDetail }) {
  const { profile } = detail;
  if (detail.identity.state !== "confirmed" || !profile) return null;

  const trend = headcountPoints(profile);
  const growth = profile.headcount_growth_yoy_pct;
  const founded = profile.incorporation_date ?? profile.year_founded;
  const financial = detail.assessment?.judgments.financial_assessment;
  const rounds = profile.funding_rounds.length;

  return (
    <section aria-label="Company profile" className="flex flex-col gap-3">
      <ProfileFacts profile={profile} />
      <KpiRow label="Profile figures">
        {founded ? (
          <StatTile
            label={profile.incorporation_date ? "Incorporated" : "Founded"}
            value={
              <span className="font-mono text-lg">
                {profile.incorporation_date
                  ? (formatDate(profile.incorporation_date.value) ?? profile.incorporation_date.value)
                  : profile.year_founded?.value}
              </span>
            }
            evidence={factEvidence(founded)}
          />
        ) : (
          <StatTile label="Incorporated" missing="Not returned" />
        )}

        {profile.headcount ? (
          <StatTile
            label="Team size"
            value={profile.headcount.value.toLocaleString("en-US")}
            unit="people"
            estimate={factEstimate(profile.headcount)}
            evidence={[
              ...factEvidence(profile.headcount),
              // The line beside the figure is the dated series, cited at its latest point.
              ...(profile.headcount_series && trend.length > 1
                ? sourceEvidence(profile.headcount_series.source, trend.at(-1)?.date ?? null)
                : []),
            ]}
            trend={
              trend.length > 1 ? (
                <Sparkline
                  points={trend}
                  estimate
                  label={`Estimated headcount, ${seriesSummary(trend, "people")}`}
                />
              ) : undefined
            }
          />
        ) : (
          <StatTile label="Team size" missing="No estimate returned" />
        )}

        {growth ? (
          <StatTile
            label="Headcount change"
            value={`${growth.value > 0 ? "+" : growth.value < 0 ? "−" : ""}${Math.abs(growth.value)}%`}
            estimate={factEstimate(growth)}
            note="vs 12 months earlier. Not evidence of revenue"
            evidence={factEvidence(growth)}
          />
        ) : null}

        {profile.total_funding_usd ? (
          <StatTile
            label="Funding on record"
            value={formatAmountUsd(profile.total_funding_usd.value)}
            note={rounds > 0 ? `${plural(rounds, "dated round")} on record` : undefined}
            evidence={factEvidence(profile.total_funding_usd)}
          />
        ) : (
          <StatTile label="Funding on record" missing="No funding record returned" />
        )}

        {profile.hiring?.openings ? (
          <StatTile
            label="Open roles"
            value={profile.hiring.openings.value}
            estimate={factEstimate(profile.hiring.openings)}
            evidence={factEvidence(profile.hiring.openings)}
          />
        ) : null}

        {financial?.assessed ? null : (
          <StatTile
            label="Revenue, valuation, ownership"
            missing="Not on record"
            note={
              financial?.would_need.length
                ? `Would need: ${financial.would_need.join(", ")}`
                : "Private company financials are not public. DealProof does not estimate them"
            }
          />
        )}
      </KpiRow>
    </section>
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
          <p className="text-xs text-ink-secondary">
            A headcount trend is a signal of operating scale. It is never treated as proof of
            revenue
          </p>
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
