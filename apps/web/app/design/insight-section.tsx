"use client";

import { useState } from "react";
import { SourceLine } from "@/components/dealproof";
import {
  CandidateBars,
  CountBars,
  EventTimeline,
  FundingRoundsTable,
  HeadcountTrend,
  KpiRow,
  PeopleRow,
  RankedDetail,
  seriesSummary,
  Sparkline,
  StatTile,
} from "@/components/insight";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  PanelBody,
  PanelFooter,
  PanelHeader,
  Segmented,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Toolbar,
} from "@/components/ui";
import { ev } from "./sample-data";

/** SAMPLE DATA. Every company, person, figure and date below is invented for this gallery. */
const BASIS = "from professional profiles, not a payroll count";
const headcount = [
  { date: "2025-04-01", value: 121 },
  { date: "2025-07-01", value: 128 },
  { date: "2025-10-01", value: 142 },
  { date: "2026-01-01", value: 151 },
  { date: "2026-04-01", value: 149 },
  { date: "2026-07-01", value: 166 },
  { date: "2026-10-01", value: 180 },
];
const NAMES = [
  ["Meridian Warehousing", 92, 100, 180, "Pune"],
  ["Cold Chain Logix", 88, 83, 240, "Pune"],
  ["Northline Freight", 84, 67, 60, "Bengaluru"],
  ["Fleetwise Systems", 80, 100, 95, "Bengaluru"],
  ["Deccan Stores", 77, 50, 410, "Hyderabad"],
  ["Sahyadri Logistics", 75, 83, null, "Pune"],
  ["Koyna Supply Tech", 71, 67, 35, "Mumbai"],
  ["Indus Dock Works", 70, 33, 130, "Mumbai"],
  ["Tapi Fulfilment", 66, 100, 72, "Surat"],
  ["Vaigai Cold Stores", 64, 50, 310, "Chennai"],
  ["Bhima Carriers", 61, 67, 44, "Pune"],
  ["Pennar Warehouse Co", 58, 83, 88, null],
  ["Narmada Hubs", 55, 50, 150, "Indore"],
  ["Godavari Freight Tech", null, 0, 22, "Hyderabad"],
] as const;

const source = (evidence: (typeof ev)[keyof typeof ev]) =>
  typeof evidence === "function" ? null : <SourceLine evidence={[evidence]} max={1} />;

const investors = [
  { id: "inv-1", name: "Northgate Ventures (sample)", rounds: 4, latest: "Aug 2026" },
  { id: "inv-2", name: "Banyan Seed Partners (sample)", rounds: 2, latest: "Mar 2025" },
  { id: "inv-3", name: "Konkan Growth (sample)", rounds: 1, latest: "Jan 2024" },
];

function Specimen({ label, note, children }: { label: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-xs text-ink-muted">
        <span className="font-medium text-ink-secondary">{label}</span>
        {note ? <span> · {note}</span> : null}
      </p>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** The insight components: dense presentations of sourced data, in every state they have. */
export function InsightSpecimens() {
  const [selected, setSelected] = useState<string | null>("inv-1");
  const cities = new Map<string, string[]>();
  const missing: string[] = [];
  for (const [name, , , , city] of NAMES) {
    if (city) cities.set(city, [...(cities.get(city) ?? []), name]);
    else missing.push(name);
  }

  return (
    <div className="flex flex-col gap-10">
      <Specimen label="KpiRow and StatTile" note="a sourced fact, an estimate with a sparkline, a computed figure, a missing one">
        <KpiRow label="Sample profile figures">
          <StatTile label="Incorporated" value={<span className="font-mono text-lg">12 Mar 2014</span>} evidence={[ev.registry]} />
          <StatTile
            label="Team size"
            value="180"
            unit="people"
            estimate={{ kind: "estimate", basis: BASIS }}
            evidence={[ev.profiles]}
            trend={<Sparkline points={headcount} estimate label={`Estimated headcount, ${seriesSummary(headcount, "people")}`} />}
          />
          <StatTile label="Median fit" value={74} note="Across 13 scored. Match to criteria, not returns" />
          <StatTile label="Open cases" value={14} href="#insight" note="A tile that counts a list links to it" />
          <StatTile label="Revenue, valuation, ownership" missing="Not on record" note="Would need: audited statements" />
        </KpiRow>
      </Specimen>

      <div className="grid items-start gap-8 xl:grid-cols-2">
        <Specimen label="HeadcountTrend" note="dashed because the series is an estimate; hover, arrow keys or the table">
          <Panel>
            <PanelBody>
              <HeadcountTrend points={headcount} basis={BASIS} evidence={[ev.profiles]} />
            </PanelBody>
          </Panel>
        </Specimen>
        <Specimen label="HeadcountTrend, no series" note="said in words, no empty axes">
          <Panel>
            <PanelBody className="flex flex-col gap-4">
              <HeadcountTrend points={[]} basis={BASIS} evidence={[ev.profiles]} />
              <HeadcountTrend points={headcount.slice(0, 1)} basis={BASIS} evidence={[ev.profiles]} title="One point only" />
            </PanelBody>
          </Panel>
        </Specimen>
      </div>

      <Specimen label="FundingRoundsTable" note="bars share one scale; a missing amount draws no bar">
        <FundingRoundsTable
          caption="Sample funding rounds"
          rows={[
            { id: "r1", round: "Series A", date: "2025-06-03", amountUsd: 6_000_000, investors: ["Northgate Ventures (sample)"], source: source(ev.fundingAnnouncement) },
            { id: "r2", round: "Seed", date: "2022-02-14", amountUsd: 750_000, investors: ["Banyan Seed Partners (sample)"], source: source(ev.news) },
            { id: "r3", round: null, date: "2020-09", amountUsd: null, investors: [], source: source(ev.newsLater) },
          ]}
        />
      </Specimen>

      <Specimen label="PeopleRow" note="roles and dates with sources; no judgment of the person">
        <PeopleRow
          people={[
            {
              id: "p1",
              name: "A. Kulkarni (sample)",
              role: { text: "Founder and chief executive", source: source(ev.profiles) },
              history: [
                { text: "Head of operations, national logistics firm, 2009 to 2014", source: source(ev.profiles) },
                { text: "Director since 12 Mar 2014", source: source(ev.registryDirectors) },
              ],
            },
            { id: "p2", name: "R. Deshmukh (sample)", role: null, history: [] },
          ]}
        />
      </Specimen>

      <div className="grid items-start gap-8 xl:grid-cols-2">
        <Specimen label="EventTimeline, single column" note="topic tag and how-it-is-known tag; filled node only when confirmed">
          <EventTimeline
            items={[
              { id: "e1", date: "2026-10-01", title: "Lease for the Chakan facility starts", kind: "facility", nature: "Recorded", source: source(ev.lease) },
              { id: "e2", date: "2026-09-09", title: "Announcement describes a planned facility", kind: "expansion", nature: "Announced", quote: "We plan to open a new facility in October", source: source(ev.announcement) },
              { id: "e3", date: "2025-06-05", title: "Series A reported", kind: "funding", nature: "Reported", source: source(ev.news) },
              { id: "e4", date: "2025-01-20", title: "Chief financial officer appointed", kind: "leadership", nature: "Announced", source: source(ev.announcement) },
            ]}
          />
        </Specimen>
        <Specimen label="EventTimeline, alternating" note="from 1024px; one column below">
          <EventTimeline
            layout="alternating"
            items={[
              { id: "a1", date: "2026-09-09", title: "Planned facility announced", kind: "expansion", nature: "Announced", source: source(ev.announcement) },
              { id: "a2", date: "2025-06-05", title: "Series A reported", kind: "funding", nature: "Reported", source: source(ev.news) },
              { id: "a3", date: "2014-03-12", title: "Company incorporated", kind: "registration", nature: "Recorded", source: source(ev.registry) },
            ]}
          />
        </Specimen>
      </div>

      <Specimen label="CandidateBars and CountBars" note="14 sample candidates: fit and coverage never merged, missing values hatched">
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <CandidateBars
            caption="Sample candidates by fit, assessable share and estimated size"
            rows={NAMES.map(([name, fit, assessablePct, people], index) => ({
              id: `c${index}`,
              rank: index + 1,
              name: `${name} (sample)`,
              fit,
              assessablePct,
              headcount: people,
            }))}
          />
          <CountBars
            caption="Sample candidates by headquarters city"
            unit="company"
            rows={[
              ...[...cities].map(([label, names]) => ({ label, count: names.length, names: names.map((n) => `${n} (sample)`) })),
              { label: "Location not returned", count: missing.length, names: missing.map((n) => `${n} (sample)`), missing: true },
            ]}
          />
        </div>
      </Specimen>

      <Specimen label="RankedDetail" note="list and detail side by side from 1024px; the detail opens under the row below that">
        <RankedDetail
          items={investors}
          getId={(item) => item.id}
          selectedId={selected}
          onSelect={setSelected}
          label="Sample investors, ranked by comparable investments found"
          listHeader={<p className="text-xs text-ink-muted">Investor · comparable investments found</p>}
          renderRow={(item) => (
            <span className="flex flex-col gap-1">
              <span className="text-sm font-medium text-ink">{item.name}</span>
              <span className="text-xs text-ink-secondary">
                <span className="font-mono">{item.rounds}</span> comparable {item.rounds === 1 ? "investment" : "investments"} · latest found{" "}
                <span className="font-mono">{item.latest}</span>
              </span>
            </span>
          )}
          renderDetail={(item) => (
            <div className="flex flex-col gap-2 text-dense">
              <h3 className="text-xl font-medium text-ink">{item.name}</h3>
              <p className="text-ink-secondary">
                The detail panel holds the rounds table, compatibility and the scope note. The order of the
                list counts past rounds; it is not a forecast.
              </p>
            </div>
          )}
        />
      </Specimen>
    </div>
  );
}

/** The page, panel, state and table primitives from the consistency spec. */
export function ShellSpecimens() {
  const [view, setView] = useState<"board" | "table">("board");
  return (
    <div className="flex flex-col gap-10">
      <Specimen label="PageHeader" note="title, one fact line, up to four figures, at most two actions">
        <PageHeader
          title="Companies"
          meta={
            <>
              <span className="font-mono">26</span> companies, <span className="font-mono">14</span> with a case
            </>
          }
          figures={[
            { label: "With a case", value: 14 },
            { label: "Median size", value: 150, estimate: true },
          ]}
          actions={<Button variant="primary">Verify a company</Button>}
        />
      </Specimen>

      <Specimen label="Toolbar and Segmented" note="one row above what it scopes, with the count on the right">
        <Toolbar count="14 shown">
          <Segmented
            label="View"
            value={view}
            onChange={setView}
            options={[
              { value: "board", label: "Board" },
              { value: "table", label: "Table", count: 14 },
            ]}
          />
        </Toolbar>
      </Specimen>

      <div className="grid items-start gap-8 xl:grid-cols-3">
        {(["compact", "default", "two-line"] as const).map((density) => (
          <Specimen key={density} label={`Panel with a ${density} table`} note={density === "compact" ? "32px" : density === "default" ? "40px" : "52px"}>
            <Panel>
              <PanelHeader title="Sources" meta="3" />
              <PanelBody flush>
                <Table density={density} flush>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Source</TableHead>
                      <TableHead numeric>Facts</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[
                      ["Registry mirror", "as of 12 Mar 2014", 4],
                      ["Crustdata profiles", "as of Oct 2026", 2],
                      ["Company announcement", "as of 9 Sep 2026", 1],
                    ].map(([name, meta, facts]) => (
                      <TableRow key={name}>
                        <TableCell>
                          <span className="font-medium">{name}</span>
                          {density === "two-line" ? <span className="block text-xs text-ink-muted">{meta}</span> : null}
                        </TableCell>
                        <TableCell numeric>{facts}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </PanelBody>
              <PanelFooter>Sample rows</PanelFooter>
            </Panel>
          </Specimen>
        ))}
      </div>

      <div className="grid items-start gap-8 xl:grid-cols-3">
        {(["page", "panel", "inline"] as const).map((size) => (
          <Specimen key={size} label={`States, ${size} size`} note="empty, loading, error">
            <div className="flex flex-col gap-4">
              <Panel>
                <EmptyState
                  size={size}
                  title="No cases yet"
                  actions={size === "inline" ? undefined : <Button size="sm">Verify a company</Button>}
                >
                  A case is one company under review. Start from a screening or a company you have in mind.
                </EmptyState>
              </Panel>
              <Panel>
                <LoadingState size={size} label="Loading sample rows" shape={size === "page" ? "tiles" : size === "panel" ? "rows" : "lines"} count={3} />
              </Panel>
              <Panel>
                <ErrorState size={size} what="Cases" reason="The DealProof API did not respond. Nothing was changed" status={503} onRetry={() => {}} />
              </Panel>
            </div>
          </Specimen>
        ))}
      </div>
    </div>
  );
}
