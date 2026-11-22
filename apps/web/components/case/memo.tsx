"use client";

import Link from "next/link";
import { createContext, useContext, useMemo } from "react";
import { type CaseDetail, type ClaimOut, type Schemas, isFixtureMode } from "@/lib/api/client";
import {
  formatCredits,
  formatDate,
  formatDateTime,
  formatUsd,
  plural,
} from "@/lib/format";
import { CLAIM_STATUS_LABEL, NOT_CHECKED_REASON_LABEL } from "@/lib/labels";
import { CLAIM_STATUSES, type EstimateMeta, type Evidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  CriteriaStrip,
  DispositionStamp,
  EstimateLabel,
  HatchedBlock,
  SourceLine,
  StatusDistribution,
  StatusMark,
  VersionDiff,
} from "@/components/dealproof";
import {
  type AnyFact,
  CATEGORY_LABEL,
  SOURCE_CLASS_LABEL,
  eventNature,
  factEstimate,
  factEvidence,
  sourceEvidence,
  statusCounts,
  toDiff,
  toEvidence,
  toFit,
} from "./adapt";
import { useCase } from "./case-context";
import { ComparisonBasis } from "./comparables-tab";
import { NatureTag } from "./events-tab";
import "./memo-print.css";

type CriterionResult = Schemas["CriterionResultOut"];

/* ───────────────────────── Citations ───────────────────────── */

/** Source id → its number in the source record at the end of the memo. */
const CiteContext = createContext<Map<string, number>>(new Map());

/** Every evidence reference in the case, so each source's fact dates can be listed. */
function collectAsOf(detail: CaseDetail): Map<string, Set<string>> {
  const dates = new Map<string, Set<string>>();
  const add = (sourceId: string, asOf: string | null) => {
    if (!asOf) return;
    const set = dates.get(sourceId) ?? new Set<string>();
    set.add(asOf);
    dates.set(sourceId, set);
  };
  const addFact = (fact: AnyFact | null | undefined) => {
    if (fact) add(fact.source.source_id, fact.as_of);
  };
  for (const claim of detail.claims) {
    for (const e of claim.evidence) add(e.source.source_id, e.as_of);
  }
  for (const event of detail.events) add(event.evidence.source.source_id, event.evidence.as_of);
  for (const key of detail.identity.keys) {
    for (const e of key.evidence) add(e.source.source_id, e.as_of);
  }
  for (const result of detail.opportunity.criterion_results) {
    for (const e of result.evidence) add(e.source.source_id, e.as_of);
  }
  for (const peer of detail.comparables.companies) addFact(peer.observation);
  const p = detail.profile;
  if (p) {
    for (const fact of [
      p.legal_name,
      p.domain,
      p.description,
      p.industries,
      p.headquarters,
      p.country,
      p.year_founded,
      p.incorporation_date,
      p.registry_id,
      p.headcount,
      p.headcount_growth_yoy_pct,
      p.total_funding_usd,
      p.hiring?.openings,
    ]) {
      addFact(fact);
    }
    for (const round of p.funding_rounds) add(round.source.source_id, round.date);
    for (const person of p.people) {
      addFact(person.title);
      for (const role of person.history) addFact(role);
    }
  }
  return dates;
}

function CiteNumbers({ evidence }: { evidence: Evidence[] }) {
  const index = useContext(CiteContext);
  const numbers = [
    ...new Set(evidence.flatMap((item) => (item.source.id ? (index.get(item.source.id) ?? []) : []))),
  ].sort((a, b) => a - b);
  if (numbers.length === 0) return null;
  return (
    <span className="font-mono text-2xs whitespace-nowrap text-ink-secondary">
      {numbers.map((n) => (
        <a key={n} href={`#memo-source-${n}`} className="rounded-xs hover:text-accent">
          [{n}]
        </a>
      ))}
    </span>
  );
}

/**
 * A fact in the memo: the statement, its source chips on screen, and its numbers in the
 * source record (which is what prints). A statement the API sent without a source says
 * so in words: it is never dressed up as sourced.
 */
function Cited({
  evidence,
  estimate,
  children,
  className,
}: {
  evidence: Evidence[];
  estimate?: EstimateMeta | null;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1", className)}>
      <span>
        {estimate ? (
          <EstimateLabel kind={estimate.kind} basis={estimate.basis} showBasis>
            {children}
          </EstimateLabel>
        ) : (
          children
        )}
      </span>
      {evidence.length > 0 ? (
        <>
          <SourceLine evidence={evidence} className="print:hidden" />
          <CiteNumbers evidence={evidence} />
        </>
      ) : (
        <span className="font-mono text-2xs text-ink-muted">no source recorded</span>
      )}
    </span>
  );
}

const CitedFact = ({ fact, children }: { fact: AnyFact; children: React.ReactNode }) => (
  <Cited evidence={factEvidence(fact)} estimate={factEstimate(fact)}>
    {children}
  </Cited>
);

/* ───────────────────────── Layout pieces ───────────────────────── */

function Section({
  number,
  title,
  children,
}: {
  number?: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 border-t border-line-strong pt-8">
      <h3 className="flex items-baseline gap-3 font-serif text-2xl text-ink">
        {number ? <span className="font-mono text-sm text-ink-muted">{number}</span> : null}
        {title}
      </h3>
      {children}
    </section>
  );
}

const Sub = ({ children }: { children: React.ReactNode }) => (
  <h4 className="pt-2 text-sm font-medium text-ink">{children}</h4>
);

const Prose = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <p className={cn("max-w-(--layout-prose-max) text-base text-ink", className)}>{children}</p>
);

const Note = ({ children }: { children: React.ReactNode }) => (
  <p className="max-w-(--layout-prose-max) text-xs text-ink-secondary">{children}</p>
);

/** Label on the left, sourced value on the right. Rows without a value are left out. */
function FactTable({ rows }: { rows: [string, React.ReactNode | null][] }) {
  const present = rows.filter(([, value]) => value !== null);
  if (present.length === 0) return null;
  return (
    <dl className="divide-y divide-line border-y border-line text-dense">
      {present.map(([label, value]) => (
        <div key={label} className="grid gap-x-6 gap-y-1 py-2 sm:grid-cols-[11rem_minmax(0,1fr)]">
          <dt className="text-ink-muted">{label}</dt>
          <dd className="text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const titleCase = (value: string) =>
  value
    .split("_")
    .map((word) => (word.length <= 1 ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1)))
    .join(" ");

function formatAmount(usd: number): string {
  if (usd >= 1_000_000) return `$${(usd / 1_000_000).toFixed(1)}M`;
  if (usd >= 1_000) return `$${Math.round(usd / 1_000)}K`;
  return formatUsd(usd);
}

/* ───────────────────────── Sections ───────────────────────── */

function recommendedAction(detail: CaseDetail): string {
  if (detail.identity.state !== "confirmed") {
    return "Confirm which legal entity this case refers to. Nothing else can be judged until then.";
  }
  const items = detail.request_list?.items.length ?? 0;
  const status = detail.message?.status;
  if (items > 0 && (status === undefined || status === "draft")) {
    return `Review and approve the request for ${plural(items, "document")}. Each one would settle an open claim.`;
  }
  if (items > 0 && status === "sent") {
    return "Wait for the seller's documents, then upload them so the affected claims are checked again.";
  }
  if (items > 0 && status === "suppressed_test_mode") {
    return "The request was approved in test mode, so nothing reached the seller. Ask for the documents directly, or approve again once email sending is on.";
  }
  if (detail.claims.some((claim) => claim.status !== "supported")) {
    return "Review the open claims and decide which are worth a request to the seller.";
  }
  return "Take this memo to the decision-maker. Every checked claim is settled.";
}

function Summary({ detail }: { detail: CaseDetail }) {
  const counts = statusCounts(detail.claims);
  const settled = detail.claims.length - counts.not_checked;
  const assessment = detail.assessment;
  const reasons = assessment?.judgments.screening_disposition.reasons ?? [];
  const numberOf = new Map(detail.claims.map((claim) => [claim.id, claim.number]));
  const notRunReasons = [
    ...new Set(
      detail.claims
        .filter((claim) => claim.status === "not_checked")
        .map((claim) =>
          claim.not_checked_reason
            ? NOT_CHECKED_REASON_LABEL[claim.not_checked_reason]
            : "reason not recorded",
        ),
    ),
  ];
  const sufficiency = assessment?.judgments.evidence_sufficiency;
  const scored = detail.opportunity.criterion_results.length > 0;

  return (
    <div data-keep="" className="grid gap-x-10 gap-y-6 rounded-lg border border-line-strong p-5 md:grid-cols-2">
      <div className="flex flex-col items-start gap-3">
        <p className="text-xs text-ink-muted">Screening disposition</p>
        {assessment ? (
          <DispositionStamp
            disposition={assessment.judgments.screening_disposition.disposition}
            size="header"
          />
        ) : (
          <DispositionStamp disposition="cannot_assess" size="header" />
        )}
        <ul className="flex flex-col gap-1 text-dense text-ink">
          {assessment ? (
            reasons.map((reason) => {
              const refs = reason.claim_ids.flatMap((id) => numberOf.get(id) ?? []);
              return (
                <li key={reason.text}>
                  {reason.text}
                  {refs.length > 0 ? (
                    <span className="font-mono text-2xs text-ink-secondary">
                      {" "}
                      · rests on {refs.length === 1 ? "claim" : "claims"} {refs.join(", ")}
                    </span>
                  ) : null}
                </li>
              );
            })
          ) : (
            <li>No assessment has been produced, so nothing can be recommended yet</li>
          )}
        </ul>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <p className="text-xs text-ink-muted">Opportunity fit</p>
          {scored ? (
            <CriteriaStrip fit={toFit(detail.opportunity)} caption />
          ) : (
            <p className="font-mono text-sm font-medium text-ink">
              Fit not scored · this case has no criteria
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-xs text-ink-muted">Evidence sufficiency</p>
          <p className="font-mono text-sm font-medium text-ink">
            {settled} of {plural(detail.claims.length, "check")} settled
            {counts.not_checked > 0 ? ` · ${counts.not_checked} not checked` : null}
          </p>
          {detail.claims.length > 0 ? <StatusDistribution counts={counts} /> : null}
          {sufficiency ? (
            <p className="text-xs text-ink-secondary">
              {sufficiency.settled.length} of{" "}
              {plural(sufficiency.required_categories.length, "required category", "required categories")}{" "}
              settled
            </p>
          ) : null}
        </div>
      </div>

      {counts.not_checked > 0 ? (
        <HatchedBlock className="md:col-span-2" innerClassName="text-dense font-medium">
          {counts.not_checked === 1 ? "1 check was not run" : `${counts.not_checked} checks were not run`}{" "}
          ({notRunReasons.join(", ")}). Results are incomplete where marked Not checked.
        </HatchedBlock>
      ) : null}

      <p className="font-mono text-xs text-ink-secondary md:col-span-2">
        Case cost: {formatCredits(detail.cost.crustdata_credits)} of{" "}
        {formatCredits(detail.cost.credit_budget)} credits · {formatUsd(detail.cost.llm_usd)} model
        usage
      </p>
      <Note>
        First-pass screening before formal due diligence. Every finding rests on the dated
        sources recorded at the end of this memo.
      </Note>
    </div>
  );
}

function Criterion({ result }: { result: CriterionResult }) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <Cited evidence={result.evidence.map(toEvidence)}>
        <span className="text-ink">{result.label}</span>
        {result.kind === "must" ? (
          <span className="font-mono text-2xs text-ink-secondary"> must-have</span>
        ) : null}
        <span className="text-ink-secondary"> · {result.reason}</span>
      </Cited>
    </li>
  );
}

function Opportunity({ detail }: { detail: CaseDetail }) {
  const { opportunity, profile } = detail;
  const groups: [string, CriterionResult[]][] = [
    ["Criteria met", opportunity.criterion_results.filter((r) => r.state === "pass")],
    ["Criteria not met", opportunity.criterion_results.filter((r) => r.state === "fail")],
    ["Criteria unknown", opportunity.criterion_results.filter((r) => r.state === "unknown")],
  ];
  const type = profile?.company_type ?? detail.assessment?.company_type ?? null;

  return (
    <Section number={1} title="The opportunity">
      <Sub>Investment thesis</Sub>
      {opportunity.thesis_text ? (
        <Prose>{opportunity.thesis_text}</Prose>
      ) : (
        <Prose className="text-ink-secondary">
          No thesis is attached to this case. The company was verified directly.
        </Prose>
      )}

      {opportunity.relevance.length > 0 ? (
        <>
          <Sub>Why this company is relevant</Sub>
          <ul className="flex max-w-(--layout-prose-max) list-disc flex-col gap-1 pl-5 text-base text-ink">
            {opportunity.relevance.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <Note>Each point follows from the criteria below, where the sources are listed.</Note>
        </>
      ) : null}

      {opportunity.criterion_results.length > 0 ? (
        <>
          <Sub>Criteria summary</Sub>
          <div className="flex flex-col gap-3 text-dense">
            {groups.map(([label, results]) =>
              results.length > 0 ? (
                <div key={label} className="flex flex-col gap-1">
                  <p className="text-xs text-ink-muted">
                    {label} ({results.length})
                  </p>
                  <ul className="flex flex-col gap-1">
                    {results.map((result) => (
                      <Criterion key={result.criterion_id} result={result} />
                    ))}
                  </ul>
                </div>
              ) : null,
            )}
          </div>
        </>
      ) : null}

      {type ? (
        <Note>
          {type === "startup"
            ? "Evaluated as an early-stage business on thesis fit, founder relevance, team development and funding history."
            : "Evaluated as an established business on strategic fit, identity, operating scale, financial performance, commercial position and leadership continuity."}
          {profile?.company_type_reason ? ` Basis: ${profile.company_type_reason}.` : null}
        </Note>
      ) : null}
    </Section>
  );
}

function IdentityAndProfile({ detail }: { detail: CaseDetail }) {
  const { identity, profile } = detail;
  const confirmed = identity.state === "confirmed";

  return (
    <Section number={2} title="Identity and profile">
      {confirmed ? (
        <>
          <Prose>
            <span className="font-medium">Identity confirmed.</span> Records in this case were
            attached using the following identifiers, not on a matching name alone.
          </Prose>
          <FactTable
            rows={identity.keys.map((key) => [
              key.label,
              <Cited key={key.key} evidence={key.evidence.map(toEvidence)}>
                <span className="font-mono text-xs break-all">{key.value}</span>
              </Cited>,
            ])}
          />
        </>
      ) : (
        <>
          <Prose>
            <span className="font-medium">
              Identity {identity.state === "ambiguous" ? "ambiguous" : "unresolved"}.
            </span>{" "}
            DealProof found{" "}
            {plural(identity.candidates.length, "candidate legal entity", "candidate legal entities")}{" "}
            matching &ldquo;{detail.case.name}&rdquo; and did not attach unconfirmed records.
            The screening disposition remains Cannot assess until the entity is confirmed.
          </Prose>
          <ul className="divide-y divide-line border-y border-line text-dense">
            {identity.candidates.map((candidate) => (
              <li
                key={candidate.crustdata_company_id}
                className="grid gap-x-6 gap-y-1 py-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
              >
                <span className="text-ink">{candidate.name}</span>
                <span className="text-ink-secondary">
                  Matches: {candidate.matching.map((k) => `${k.label} ${k.value}`).join(", ") || "none"}
                  {" · "}
                  Differs: {candidate.differing.map((k) => `${k.label} ${k.value}`).join(", ") || "none"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {confirmed && profile ? (
        <>
          <Sub>Public profile</Sub>
          <FactTable
            rows={[
              [
                "Legal name",
                profile.legal_name ? (
                  <CitedFact fact={profile.legal_name}>{profile.legal_name.value}</CitedFact>
                ) : null,
              ],
              [
                "Business and industry",
                profile.description ? (
                  <CitedFact fact={profile.description}>
                    {profile.description.value}
                    {profile.industries ? ` (${profile.industries.value.join(", ")})` : null}
                  </CitedFact>
                ) : null,
              ],
              [
                "Headquarters",
                profile.headquarters ? (
                  <CitedFact fact={profile.headquarters}>
                    {[profile.headquarters.value, profile.country?.value].filter(Boolean).join(", ")}
                  </CitedFact>
                ) : null,
              ],
              [
                "Incorporated",
                profile.incorporation_date ? (
                  <CitedFact fact={profile.incorporation_date}>
                    {formatDate(profile.incorporation_date.value) ?? profile.incorporation_date.value}
                  </CitedFact>
                ) : profile.year_founded ? (
                  <CitedFact fact={profile.year_founded}>{profile.year_founded.value}</CitedFact>
                ) : null,
              ],
              [
                "Funding on record",
                profile.total_funding_usd ? (
                  <CitedFact fact={profile.total_funding_usd}>
                    {formatAmount(profile.total_funding_usd.value)} in total
                  </CitedFact>
                ) : null,
              ],
              ...profile.funding_rounds.map(
                (round, index): [string, React.ReactNode] => [
                  `Funding round ${index + 1}`,
                  <Cited key={index} evidence={sourceEvidence(round.source, round.date)}>
                    {[
                      round.round_type ? titleCase(round.round_type) : "Round",
                      formatDate(round.date) ?? "undated",
                      round.amount_usd != null ? formatAmount(round.amount_usd) : null,
                      round.investors.join(", ") || null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Cited>,
                ],
              ),
            ]}
          />

          {profile.people.length > 0 ? (
            <>
              <Sub>Leadership and founders</Sub>
              <ul className="divide-y divide-line border-y border-line text-dense">
                {profile.people.map((person) => (
                  <li
                    key={person.person_id ?? person.name}
                    className="grid gap-x-6 gap-y-1 py-2 sm:grid-cols-[11rem_minmax(0,1fr)]"
                  >
                    <span className="text-ink">{person.name}</span>
                    <span className="flex flex-col items-start gap-1">
                      {person.title ? (
                        <CitedFact fact={person.title}>{person.title.value}</CitedFact>
                      ) : null}
                      {person.history.map((role) => (
                        <CitedFact key={role.value} fact={role}>
                          <span className="text-ink-secondary">{role.value}</span>
                        </CitedFact>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
              <Note>
                Career records are attached only where matched on company identifier and name.
                Name-only matches are left out of this table.
              </Note>
            </>
          ) : null}

          {profile.headcount || profile.headcount_growth_yoy_pct || profile.hiring?.openings ? (
            <>
              <Sub>Operating signals</Sub>
              <FactTable
                rows={[
                  [
                    "Team size",
                    profile.headcount ? (
                      <CitedFact fact={profile.headcount}>{profile.headcount.value} people</CitedFact>
                    ) : null,
                  ],
                  [
                    "Headcount trend",
                    profile.headcount_growth_yoy_pct ? (
                      <CitedFact fact={profile.headcount_growth_yoy_pct}>
                        {profile.headcount_growth_yoy_pct.value < 0 ? "Down" : "Up"}{" "}
                        {Math.abs(profile.headcount_growth_yoy_pct.value)}% year on year
                      </CitedFact>
                    ) : null,
                  ],
                  [
                    "Open roles",
                    profile.hiring?.openings ? (
                      <CitedFact fact={profile.hiring.openings}>
                        {plural(profile.hiring.openings.value, "open role")}
                      </CitedFact>
                    ) : null,
                  ],
                ]}
              />
              <Note>
                Operating signals and profile-based headcount estimates are indirect
                indicators. They are not payroll counts and are never treated as proof of
                revenue.
              </Note>
            </>
          ) : null}
        </>
      ) : null}
    </Section>
  );
}

function MemoClaim({ claim }: { claim: ClaimOut }) {
  const notChecked = claim.status === "not_checked";
  const statedIn =
    claim.origin === "typed"
      ? `typed by ${claim.stated_in.typed_by_name ?? "a user"}`
      : `${claim.stated_in.filename ?? "seller document"}${
          claim.stated_in.page != null ? ` p. ${claim.stated_in.page}` : ""
        }`;
  return (
    <li
      className={cn(
        "grid gap-x-6 gap-y-2 px-3 py-3 text-dense sm:grid-cols-[1.5rem_minmax(0,5fr)_minmax(0,7fr)]",
        notChecked && "hatch border border-dashed border-not-checked-line",
      )}
    >
      <span className="font-mono text-xs text-ink-muted">{claim.number}</span>
      <div className="flex flex-col items-start gap-1">
        <p className="text-ink">&ldquo;{claim.original_text}&rdquo;</p>
        <p className="text-xs text-ink-muted">
          {CATEGORY_LABEL[claim.category]} · {statedIn}
        </p>
      </div>
      <div className="flex flex-col items-start gap-2">
        <StatusMark status={claim.status} reason={claim.not_checked_reason} />
        {notChecked ? (
          <p className="text-not-checked">No search was run for this claim.</p>
        ) : (
          <Cited evidence={claim.evidence.map(toEvidence)}>{claim.reason}</Cited>
        )}
        {claim.settle_with ? (
          <p className="text-ink">
            <span className="text-ink-muted">What would settle it: </span>
            {claim.settle_with}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function Claims({ detail }: { detail: CaseDetail }) {
  const { basePath } = useCase();
  const counts = statusCounts(detail.claims);
  return (
    <Section number={3} title="Claims">
      {detail.claims.length === 0 ? (
        <Prose className="text-ink-secondary">
          No claims are on file. Upload the seller&rsquo;s documents or type claims on the
          Claims tab.
        </Prose>
      ) : (
        <>
          <p className="text-dense text-ink">
            {CLAIM_STATUSES.map((status) => `${counts[status]} ${CLAIM_STATUS_LABEL[status]}`).join(" · ")}
          </p>
          <ul className="flex flex-col divide-y divide-line border-y border-line">
            {detail.claims.map((claim) => (
              <MemoClaim key={claim.id} claim={claim} />
            ))}
          </ul>
          <Note>
            Cannot verify is a finished screening result where available records cannot settle
            the question. Not checked means a check did not run, and it is excluded from
            settled counts.{" "}
            <Link href={`${basePath}/claims`} className="text-accent underline underline-offset-2 print:hidden">
              Open the full ledger
            </Link>
          </Note>
        </>
      )}
    </Section>
  );
}

function Events({ detail }: { detail: CaseDetail }) {
  const events = [...detail.events].sort((a, b) => b.event_date.localeCompare(a.event_date));
  const name = detail.profile?.legal_name?.value ?? detail.case.name;
  return (
    <Section number={4} title="Recent events">
      {events.length === 0 ? (
        <Prose className="text-ink-secondary">
          {detail.identity.state === "confirmed"
            ? "No recent dated public events were returned on record for this confirmed entity."
            : "Events are attached once the legal entity is confirmed."}
        </Prose>
      ) : (
        <>
          <p className="text-dense text-ink-secondary">
            Dated public events recorded for {name}, newest first.
          </p>
          <ul className="divide-y divide-line border-y border-line text-dense">
            {events.map((event) => (
              <li
                key={event.id}
                className="grid gap-x-6 gap-y-1 py-2 sm:grid-cols-[6.5rem_minmax(0,1fr)]"
              >
                <time dateTime={event.event_date} className="font-mono text-xs text-ink">
                  {formatDate(event.event_date)}
                </time>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Cited evidence={[toEvidence(event.evidence)]}>{event.title}</Cited>
                  <NatureTag nature={eventNature(event)} />
                </span>
              </li>
            ))}
          </ul>
          <Note>
            Company announcements describing planned launches or expansions are worded as
            plans unless independent records confirm execution.
          </Note>
        </>
      )}
    </Section>
  );
}

function Comparables({ detail }: { detail: CaseDetail }) {
  const { comparables } = detail;
  return (
    <Section number={5} title="Comparable companies">
      {comparables.companies.length === 0 ? (
        <>
          <Prose>
            <span className="font-medium">No fair comparison found.</span>{" "}
            {comparables.no_fair_comparison_reason
              ? `${comparables.no_fair_comparison_reason.replace(/\.$/, "")}.`
              : null}
          </Prose>
          <Note>
            DealProof does not substitute a weaker peer list when records do not support a
            fair comparison.
          </Note>
        </>
      ) : (
        <>
          <ComparisonBasis basis={comparables.basis} />
          <ul className="divide-y divide-line border-y border-line text-dense">
            {comparables.companies.map((peer) => (
              <li
                key={peer.crustdata_company_id}
                className="grid gap-x-6 gap-y-1 py-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
              >
                <span className="text-ink">{peer.name}</span>
                <CitedFact fact={peer.observation}>{peer.observation.value}</CitedFact>
              </li>
            ))}
          </ul>
          <Note>Same activity, region and size band. Informational only: comparables are not scored.</Note>
        </>
      )}
    </Section>
  );
}

function Financial({ detail }: { detail: CaseDetail }) {
  const financial = detail.assessment?.judgments.financial_assessment;
  const assessed = financial?.assessed === true && financial.figures.length > 0;
  return (
    <Section number={6} title="Financial evaluation">
      {assessed && financial ? (
        <>
          <FactTable
            rows={financial.figures.map((figure) => [
              figure.label,
              <span key={figure.label} className="flex flex-col items-start gap-1">
                <CitedFact fact={figure.fact}>{figure.fact.value}</CitedFact>
                {figure.assumption ? (
                  <span className="text-xs text-ink-secondary">Assumes: {figure.assumption}</span>
                ) : null}
              </span>,
            ])}
          />
          {financial.period ? <Note>Period: {financial.period}</Note> : null}
          {financial.conclusion ? <Prose>{financial.conclusion}</Prose> : null}
          <Note>
            These figures reflect stated scenarios from the supplied inputs under the
            assumptions listed. They are not a valuation, a verified fair value or financial
            due diligence.
          </Note>
        </>
      ) : (
        <>
          <HatchedBlock data-keep="" className="max-w-(--layout-prose-max)" innerClassName="flex flex-col gap-1">
            <p className="text-sm font-medium">
              Not assessed · {(financial?.reason ?? "no reliable financial inputs").toLowerCase()}
            </p>
            <p className="text-dense">
              Would need:{" "}
              {financial && financial.would_need.length > 0
                ? financial.would_need.join(", ").toLowerCase()
                : "audited financial statements"}
            </p>
          </HatchedBlock>
          <Note>
            No complete, current financial statements are on record for this entity, and none
            were supplied for this case. DealProof does not fill missing financial inputs with
            guesses.
          </Note>
        </>
      )}
    </Section>
  );
}

function Risks({ detail }: { detail: CaseDetail }) {
  const claimOf = new Map(detail.claims.map((claim) => [claim.id, claim]));
  const refs = (ids: string[]) => {
    const numbers = ids.flatMap((id) => claimOf.get(id)?.number ?? []);
    return numbers.length > 0 ? ` (claim ${numbers.join(", ")})` : "";
  };
  const settles = (ids: string[]) => {
    const docs = ids.flatMap((id) => claimOf.get(id)?.settle_with ?? []);
    return docs.length > 0 ? `. Would be resolved by: ${docs.join(", ").toLowerCase()}` : "";
  };
  const onRecord = detail.claims.filter(
    (claim) => claim.status === "contradicted" || claim.status === "conflicting_evidence",
  );
  const assumptions = detail.risks.filter((r) => r.kind === "assumption" || r.kind === "estimate_used");
  const unknowns = detail.risks.filter((r) => r.kind === "gap" || r.kind === "not_checked");
  const other = detail.risks.filter(
    (r) => !["assumption", "estimate_used", "gap", "not_checked"].includes(r.kind),
  );
  const list = "flex max-w-(--layout-prose-max) list-disc flex-col gap-1 pl-5 text-base text-ink";

  return (
    <Section number={7} title="Risks, assumptions and unknowns">
      <Note>Missing information is stated plainly and is not treated as negative performance.</Note>

      <Sub>Risks observed on record</Sub>
      {onRecord.length + other.length === 0 ? (
        <Prose className="text-ink-secondary">
          No material risks were identified within the sources checked. See the unknowns and
          any Not checked items below.
        </Prose>
      ) : (
        <ul className={list}>
          {onRecord.map((claim) => (
            <li key={claim.id}>
              <Cited evidence={claim.evidence.map(toEvidence)}>
                Claim {claim.number} is {CLAIM_STATUS_LABEL[claim.status].toLowerCase()}:{" "}
                {claim.reason}
              </Cited>
            </li>
          ))}
          {other.map((risk) => (
            <li key={risk.text}>
              {risk.text}
              {refs(risk.claim_ids)}
            </li>
          ))}
        </ul>
      )}

      <Sub>Assumptions stated</Sub>
      {assumptions.length === 0 ? (
        <Prose className="text-ink-secondary">
          No financial or operating assumptions were applied in this screening.
        </Prose>
      ) : (
        <ul className={list}>
          {assumptions.map((risk) => (
            <li key={risk.text}>
              {risk.text}
              {refs(risk.claim_ids)}
            </li>
          ))}
        </ul>
      )}

      <Sub>Unknowns remaining</Sub>
      {unknowns.length === 0 ? (
        <Prose className="text-ink-secondary">
          No material unknowns remain within the criteria and claims checked.
        </Prose>
      ) : (
        <ul className={list}>
          {unknowns.map((risk) => (
            <li key={risk.text}>
              {risk.text}
              {refs(risk.claim_ids)}
              {settles(risk.claim_ids)}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function NextStep({ detail }: { detail: CaseDetail }) {
  const assessment = detail.assessment;
  const numberOf = new Map(detail.claims.map((claim) => [claim.id, claim.number]));
  const disposition = assessment?.judgments.screening_disposition;
  return (
    <Section number={8} title="Recommended next step">
      <div data-keep="" className="flex flex-col items-start gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <DispositionStamp disposition={disposition?.disposition ?? "cannot_assess"} />
          {assessment ? (
            <span className="font-mono text-2xs text-ink-secondary">
              policy {assessment.policy_version}
            </span>
          ) : null}
        </div>
        {disposition ? (
          <ol className="flex max-w-(--layout-prose-max) list-decimal flex-col gap-1 pl-5 text-base text-ink">
            {disposition.reasons.map((reason) => {
              const refs = reason.claim_ids.flatMap((id) => numberOf.get(id) ?? []);
              return (
                <li key={reason.text}>
                  {reason.text}
                  {refs.length > 0 ? ` (claim ${refs.join(", ")})` : null}
                </li>
              );
            })}
          </ol>
        ) : (
          <Prose>
            {detail.identity.state === "confirmed"
              ? "No assessment has been produced for this case yet."
              : "Identity is not confirmed, so the case cannot be assessed."}
          </Prose>
        )}
      </div>
      <Sub>Recommended action</Sub>
      <Prose>{recommendedAction(detail)}</Prose>
      <Note>
        {assessment
          ? `This disposition is produced by stated rules under policy ${assessment.policy_version} from the records attached to this case. `
          : null}
        This is a first-pass screening recommendation, not a prediction of returns, legal
        advice or formal due diligence.
      </Note>
    </Section>
  );
}

function requestStatus(detail: CaseDetail): string {
  const message = detail.message;
  if (!message) return "Request status: Draft. Waiting for review and approval by a named person. Nothing has been sent.";
  const approver = message.approval?.approver_display_name ?? "a named person";
  const at = formatDateTime(message.approval?.approved_at) ?? "time not recorded";
  switch (message.status) {
    case "sent":
      return `Request status: Sent once. Approved by ${approver} on ${at}.`;
    case "suppressed_test_mode":
      return `Request status: Suppressed (test mode) · not sent. Approved by ${approver} on ${at}. Email sending was off; nothing left DealProof.`;
    case "failed":
      return `Request status: Failed · not sent. Attempted after approval by ${approver} on ${at}.${
        message.send?.error ? ` Provider error: ${message.send.error}.` : ""
      } No automatic retry occurred.`;
    case "approved":
      return `Request status: Approved by ${approver} on ${at}. Not sent yet.`;
    case "sending":
      return `Request status: Sending. Approved by ${approver} on ${at}.`;
    case "unknown":
      return "Request status: Unknown. The send could not be confirmed with the provider and was not repeated.";
    default:
      return "Request status: Draft. Waiting for review and approval by a named person. Nothing has been sent.";
  }
}

function Request({ detail }: { detail: CaseDetail }) {
  const { basePath } = useCase();
  const items = detail.request_list?.items ?? [];
  const claimOf = new Map(detail.claims.map((claim) => [claim.id, claim]));
  const suppressed = detail.message?.status === "suppressed_test_mode";
  return (
    <Section number={9} title="Information to request from the seller">
      {items.length === 0 ? (
        <Prose className="text-ink-secondary">No seller request is required at this stage.</Prose>
      ) : (
        <>
          <p className="text-dense text-ink-secondary">
            The following documents would settle the open claims in this case.
          </p>
          <ol className="flex flex-col divide-y divide-line border-y border-line text-dense">
            {items.map((item, index) => {
              const claims = item.claim_ids.flatMap((id) => claimOf.get(id) ?? []);
              return (
                <li
                  key={item.id}
                  className="grid gap-x-6 gap-y-1 py-2 sm:grid-cols-[1.5rem_minmax(0,2fr)_minmax(0,3fr)]"
                >
                  <span className="font-mono text-xs text-ink-muted">{index + 1}</span>
                  <span className="font-medium text-ink">{item.document}</span>
                  <span className="text-ink-secondary">
                    {claims.length > 0
                      ? claims
                          .map((claim) => `settles claim ${claim.number} (“${claim.original_text}”)`)
                          .join("; ")
                      : item.reason}
                  </span>
                </li>
              );
            })}
          </ol>
          {suppressed ? (
            <HatchedBlock data-keep="" innerClassName="text-dense">
              {requestStatus(detail)}
            </HatchedBlock>
          ) : (
            <p className="text-dense text-ink">{requestStatus(detail)}</p>
          )}
          <Link
            href={`${basePath}/request`}
            className="self-start rounded-xs text-dense text-accent underline underline-offset-2 transition-colors hover:text-accent-hover print:hidden"
          >
            Open request and approval
          </Link>
        </>
      )}
    </Section>
  );
}

function Sources({ detail, asOf }: { detail: CaseDetail; asOf: Map<string, Set<string>> }) {
  const live = detail.documents.filter((document) => !document.purged);
  const deletion = live
    .map((document) => document.delete_after)
    .sort()
    .at(-1);
  return (
    <Section number={10} title="Sources">
      {detail.sources.length === 0 ? (
        <Prose className="text-ink-secondary">
          No sources are on record yet. They are listed here as soon as a check reads one.
        </Prose>
      ) : (
        <>
          <p className="text-dense text-ink-secondary">
            Every source used in this case, so each finding can be audited and reproduced.
          </p>
          <ol className="flex flex-col divide-y divide-line border-y border-line text-dense">
            {detail.sources.map((source, index) => {
              const dates = [...(asOf.get(source.source_id) ?? [])].sort();
              const classLabel = SOURCE_CLASS_LABEL[source.source_class];
              return (
                <li
                  key={source.source_id}
                  id={`memo-source-${index + 1}`}
                  className="grid scroll-mt-24 gap-x-4 gap-y-1 py-2 sm:grid-cols-[2rem_minmax(0,1fr)]"
                >
                  <span className="font-mono text-xs text-ink-secondary">[{index + 1}]</span>
                  <div className="flex min-w-0 flex-col gap-1">
                    <p className="text-ink">
                      {source.label}
                      <span className="text-ink-secondary">
                        {source.label.toLowerCase().startsWith(classLabel.toLowerCase())
                          ? null
                          : ` · ${classLabel}`}
                        {source.publisher ? ` · ${source.publisher}` : null}
                      </span>
                      {source.attached ? null : (
                        <span className="text-not-checked">
                          {" "}
                          · not attached{source.unattached_reason ? `: ${source.unattached_reason}` : null}
                        </span>
                      )}
                    </p>
                    <p className="font-mono text-2xs break-all text-ink-secondary">
                      {source.url_or_endpoint}
                      {source.request ? ` ${JSON.stringify(source.request)}` : null}
                    </p>
                    <p className="font-mono text-2xs text-ink-secondary">
                      as of {dates.length > 0 ? dates.map((d) => formatDate(d)).join(", ") : "unknown date"}{" "}
                      · retrieved {formatDateTime(source.retrieved_at) ?? "time not recorded"}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      )}
      {detail.documents.length > 0 ? (
        <Note>
          Confidentiality: uploaded seller documents were used only for this case, were not
          used to train AI models and were not shared across customers.{" "}
          {deletion
            ? `They are scheduled for deletion on ${formatDate(deletion)}.`
            : "They have been deleted under the retention schedule."}
        </Note>
      ) : null}
    </Section>
  );
}

/* ───────────────────────── The memo ───────────────────────── */

/**
 * The finished case as a screening memo, in the order of docs/content/memo-template.md.
 * It reads on screen as a sheet of paper and prints to A4 through `memo-print.css`.
 */
export function Memo({ detail }: { detail: CaseDetail }) {
  const { basePath } = useCase();
  const index = useMemo(
    () => new Map(detail.sources.map((source, i) => [source.source_id, i + 1])),
    [detail.sources],
  );
  const asOf = useMemo(() => collectAsOf(detail), [detail]);
  const assessment = detail.assessment;
  const diff = assessment ? toDiff(assessment, detail.claims) : null;
  const legalName = detail.profile?.legal_name?.value ?? detail.case.name;
  // The company's name sits in the running header of every printed page.
  const runningHeader = `@media print { @page { @top-right { content: ${JSON.stringify(legalName)}; font: 9pt var(--font-sans); color: #454a54; } } }`;

  return (
    <CiteContext.Provider value={index}>
      <style>{runningHeader}</style>
      <article
        data-memo=""
        className="flex max-w-4xl flex-col gap-8 rounded-xl border border-line bg-surface px-5 py-8 shadow-xs sm:px-10 sm:py-12"
      >
        <header className="flex flex-col gap-2">
          <p className="text-sm text-ink-secondary">Screening memo</p>
          <h2 className="font-serif text-3xl text-ink">{legalName}</h2>
          <p className="font-mono text-xs text-ink-secondary">
            {assessment
              ? `Version ${assessment.version} · ${formatDate(assessment.created_at)} · policy ${assessment.policy_version}`
              : "No assessment version yet"}{" "}
            · prepared for {detail.case.owner.display_name}
          </p>
          {isFixtureMode ? (
            <p className="self-start rounded-xs border border-dashed border-line-strong px-2 py-0.5 text-xs text-ink-secondary">
              Illustration, not a real company
            </p>
          ) : null}
        </header>

        <Summary detail={detail} />

        {diff && assessment ? (
          <section className="flex flex-col gap-3">
            <h3 className="font-serif text-2xl text-ink">
              What changed since version {diff.from_version}
            </h3>
            <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">
              Updated on {formatDateTime(assessment.created_at)} after {assessment.trigger}.
              Version {diff.from_version} remains archived and readable in full.{" "}
              <Link
                href={`${basePath}/assessment`}
                className="text-accent underline underline-offset-2 print:hidden"
              >
                Assessment history
              </Link>
            </p>
            <VersionDiff diff={diff} />
          </section>
        ) : null}

        <Opportunity detail={detail} />
        <IdentityAndProfile detail={detail} />
        <Claims detail={detail} />
        <Events detail={detail} />
        <Comparables detail={detail} />
        <Financial detail={detail} />
        <Risks detail={detail} />
        <NextStep detail={detail} />
        <Request detail={detail} />
        <Sources detail={detail} asOf={asOf} />

        <p className="border-t border-line pt-4 text-xs text-ink-secondary print:hidden">
          Screening only. Not financial, legal or tax due diligence
        </p>
      </article>
    </CiteContext.Provider>
  );
}
