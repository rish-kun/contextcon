"use client";

import { BadgeCheck, Check, CircleQuestionMark, Minus, RotateCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  ApiError,
  type CaseDetail,
  type Schemas,
  isFixtureMode,
  pickIdentity,
} from "@/lib/api/client";
import { formatDate, formatDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Fact, HatchedBlock, SourceLine } from "@/components/dealproof";
import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Icon,
} from "@/components/ui";
import {
  type AnyFact,
  factEstimate,
  factEvidence,
  humanKey,
  sourceEvidence,
  toEvidence,
} from "./adapt";
import { useCase, useCaseDetail } from "./case-context";
import { TabHeading } from "./parts";

type Candidate = Schemas["IdentityCandidateOut"];
type IdentityKeyOut = Schemas["IdentityKeyOut"];

/** A key's evidence, or a plain statement that none was recorded. Never a blank. */
function KeyEvidence({ item }: { item: IdentityKeyOut }) {
  if (item.evidence.length === 0) {
    return <span className="font-mono text-2xs text-ink-muted">no evidence span recorded</span>;
  }
  return <SourceLine evidence={item.evidence.map(toEvidence)} />;
}

/* ───────────────────────── Confirmed ───────────────────────── */

function ProfileRow({
  label,
  fact,
  children,
}: {
  label: string;
  fact: AnyFact | null | undefined;
  children: React.ReactNode;
}) {
  if (!fact) return null;
  return (
    <div className="grid gap-x-6 gap-y-1 py-3 sm:grid-cols-[11rem_minmax(0,1fr)]">
      <dt className="text-dense text-ink-muted">{label}</dt>
      <dd className="text-dense">
        <Fact evidence={factEvidence(fact)} estimate={factEstimate(fact)}>
          {children}
        </Fact>
      </dd>
    </div>
  );
}

function Confirmed({ detail }: { detail: CaseDetail }) {
  const { verify, runActive } = useCase();
  const { identity, profile } = detail;
  const pick = identity.pick;
  const neverVerified = detail.assessment === null;

  return (
    <div className="flex flex-col gap-8">
      <section aria-label="Matching identifiers" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="flex items-center gap-2 text-sm font-medium text-ink">
            <Icon icon={BadgeCheck} />
            Identity confirmed
            <span className="font-normal text-ink-secondary">{identity.entity_name}</span>
          </h3>
          <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">
            Every record in this case is attached using these identifiers, never on a
            matching name alone
          </p>
        </div>

        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="hidden grid-cols-[12rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-6 border-b border-line-strong bg-surface-sunken px-4 py-2 text-xs font-medium text-ink-secondary sm:grid">
            <span>Identifier</span>
            <span>Confirmed value</span>
            <span>Evidence</span>
          </div>
          {identity.keys.length === 0 ? (
            <p className="px-4 py-3 text-dense text-ink-secondary">
              No matching identifiers were recorded for this entity
            </p>
          ) : (
            <dl className="divide-y divide-line">
              {identity.keys.map((item) => (
                <div
                  key={item.key}
                  className="grid gap-x-6 gap-y-1 px-4 py-3 text-dense sm:grid-cols-[12rem_minmax(0,1fr)_minmax(0,1fr)]"
                >
                  <dt className="text-ink-muted">{item.label}</dt>
                  <dd className="font-mono text-xs break-all text-ink">{item.value}</dd>
                  <dd>
                    <KeyEvidence item={item} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>

        {pick ? (
          <p className="font-mono text-2xs text-ink-secondary">
            Chosen by {pick.picked_by.display_name} · {formatDateTime(pick.picked_at)}
            {pick.matched_keys.length > 0
              ? ` · matched on ${pick.matched_keys.map(humanKey).join(", ")}`
              : null}
          </p>
        ) : null}

        {neverVerified ? (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-4 py-3">
            <p className="text-dense text-ink">
              Identity-dependent checks are unblocked. Nothing has been checked yet
            </p>
            <Button variant="primary" size="sm" onClick={() => void verify()} disabled={runActive}>
              <Icon icon={RotateCw} />
              {runActive ? "Verification running" : "Run verification"}
            </Button>
          </div>
        ) : null}
      </section>

      {profile ? (
        <section aria-label="Public profile" className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-ink">Public profile</h3>
          <dl className="divide-y divide-line border-y border-line">
            <ProfileRow label="Legal name" fact={profile.legal_name}>
              {profile.legal_name?.value}
            </ProfileRow>
            <ProfileRow label="Registration number" fact={profile.registry_id}>
              <span className="font-mono text-xs">{profile.registry_id?.value}</span>
            </ProfileRow>
            <ProfileRow label="Incorporated" fact={profile.incorporation_date}>
              {formatDate(profile.incorporation_date?.value) ?? profile.incorporation_date?.value}
            </ProfileRow>
            <ProfileRow label="Founded" fact={profile.year_founded}>
              {profile.year_founded?.value}
            </ProfileRow>
            <ProfileRow label="Headquarters" fact={profile.headquarters}>
              {[profile.headquarters?.value, profile.country?.value].filter(Boolean).join(", ")}
            </ProfileRow>
            <ProfileRow label="Domain" fact={profile.domain}>
              <span className="font-mono text-xs">{profile.domain?.value}</span>
            </ProfileRow>
            <ProfileRow label="Business" fact={profile.description}>
              {profile.description?.value}
            </ProfileRow>
            <ProfileRow label="Industries" fact={profile.industries}>
              {profile.industries?.value.join(", ")}
            </ProfileRow>
          </dl>
        </section>
      ) : null}

      {profile && profile.people.length > 0 ? (
        <section aria-label="Key people" className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-ink">Key people</h3>
          <ul className="divide-y divide-line border-y border-line">
            {profile.people.map((person) => (
              <li
                key={person.person_id ?? person.name}
                className="grid gap-x-6 gap-y-1 py-3 text-dense sm:grid-cols-[11rem_minmax(0,1fr)]"
              >
                <span className="text-ink">{person.name}</span>
                <div className="flex flex-col items-start gap-2">
                  {person.title ? (
                    <Fact evidence={factEvidence(person.title)}>{person.title.value}</Fact>
                  ) : (
                    <span className="text-ink-secondary">Role not on record</span>
                  )}
                  {person.history.map((role) => (
                    <Fact key={role.value} evidence={sourceEvidence(role.source, role.as_of)}>
                      <span className="text-ink-secondary">{role.value}</span>
                    </Fact>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className="max-w-(--layout-prose-max) text-xs text-ink-secondary">
            Career records are attached only where both the person&rsquo;s name and the
            company identifier match. A name-only match is left out
          </p>
        </section>
      ) : null}
    </div>
  );
}

/* ───────────────────────── Ambiguous or unresolved ───────────────────────── */

interface AttributeRow {
  key: string;
  label: string;
  /** True when the candidates do not all share one value: this attribute tells them apart. */
  distinguishing: boolean;
}

/** Every attribute any candidate carries, in one order, so the cards line up row for row. */
function attributeRows(candidates: Candidate[]): AttributeRow[] {
  const rows = new Map<string, AttributeRow>();
  for (const candidate of candidates) {
    for (const item of [...candidate.matching, ...candidate.differing]) {
      if (!rows.has(item.key)) rows.set(item.key, { key: item.key, label: item.label, distinguishing: false });
    }
  }
  for (const row of rows.values()) {
    const values = candidates.map(
      (c) => [...c.matching, ...c.differing].find((item) => item.key === row.key)?.value ?? null,
    );
    row.distinguishing = new Set(values).size > 1;
  }
  // The attributes that tell the candidates apart come first.
  return [...rows.values()].sort((a, b) => Number(b.distinguishing) - Number(a.distinguishing));
}

function CandidateCard({
  candidate,
  rows,
  onChoose,
}: {
  candidate: Candidate;
  rows: AttributeRow[];
  onChoose: () => void;
}) {
  return (
    <li className="flex flex-col rounded-lg border border-line-strong bg-surface">
      <div className="flex flex-col gap-1 border-b border-line px-4 py-3">
        <h4 className="text-sm font-medium text-ink">{candidate.name}</h4>
        <p className="font-mono text-2xs text-ink-secondary">
          company id {candidate.crustdata_company_id} · {candidate.matching.length} matching ·{" "}
          {candidate.differing.length} differing
        </p>
      </div>
      <dl className="flex flex-1 flex-col divide-y divide-line">
        {rows.map((row) => {
          const match = candidate.matching.find((item) => item.key === row.key);
          const differ = candidate.differing.find((item) => item.key === row.key);
          const item = match ?? differ;
          return (
            <div
              key={row.key}
              className={cn(
                "grid min-h-16 grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 px-4 py-3 text-dense",
                row.distinguishing && "bg-surface-raised",
              )}
            >
              <dt className="text-ink-muted">{row.label}</dt>
              <dd className="flex flex-col items-start gap-1">
                {item ? (
                  <>
                    <span className="break-all text-ink">{item.value}</span>
                    <span className="inline-flex items-center gap-1 text-xs text-ink-secondary">
                      <Icon icon={match ? Check : Minus} size={14} />
                      {match ? "Matches" : "Differs"}
                    </span>
                    <KeyEvidence item={item} />
                  </>
                ) : (
                  <span className="text-ink-muted">Not on record for this candidate</span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
      <div className="border-t border-line p-4">
        <Button
          variant="primary"
          className="h-11 w-full sm:w-auto md:h-9"
          onClick={onChoose}
          aria-label={`This is the company: ${candidate.name}`}
        >
          This is the company
        </Button>
      </div>
    </li>
  );
}

const BLOCKED: { label: string; segment: string; note: (detail: CaseDetail) => string }[] = [
  {
    label: "Claim checks",
    segment: "claims",
    note: (detail) =>
      detail.claims.length > 0
        ? `${plural(detail.claims.length, "claim")} waiting, marked Not checked · identity unresolved`
        : "No evidence is gathered for any claim",
  },
  { label: "Events", segment: "events", note: () => "No dated events are attached" },
  { label: "Comparables", segment: "comparables", note: () => "No peers are selected" },
  { label: "Assessment", segment: "assessment", note: () => "The disposition stays Cannot assess" },
  { label: "Request & approval", segment: "request", note: () => "No request list is drafted" },
];

function Unresolved({ detail }: { detail: CaseDetail }) {
  const { caseId, basePath, mutate, reload } = useCase();
  const { identity } = detail;
  const [choosing, setChoosing] = useState<Candidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rows = attributeRows(identity.candidates);
  const telling = rows.filter((row) => row.distinguishing);
  const ambiguous = identity.state === "ambiguous";

  async function confirm(candidate: Candidate) {
    setBusy(true);
    setError(null);
    try {
      await pickIdentity(caseId, candidate.crustdata_company_id);
      if (isFixtureMode) {
        // Fixtures cannot change; show what the pick does to the case.
        mutate((current) => ({
          ...current,
          case: {
            ...current.case,
            identity_state: "confirmed",
            crustdata_company_id: candidate.crustdata_company_id,
          },
          identity: {
            ...current.identity,
            state: "confirmed",
            entity_name: candidate.name,
            crustdata_company_id: candidate.crustdata_company_id,
            keys: candidate.matching,
            pick: {
              crustdata_company_id: candidate.crustdata_company_id,
              picked_by: current.case.owner,
              picked_at: new Date().toISOString(),
              matched_keys: candidate.matching.map((item) => item.key),
            },
            note: null,
          },
        }));
      } else {
        await reload();
      }
      setChoosing(null);
    } catch (cause) {
      setError(
        cause instanceof ApiError && typeof cause.detail === "string"
          ? cause.detail
          : "The choice was not saved. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section
        aria-label="Identity"
        className="flex flex-col gap-4 rounded-lg border border-cannot-verify bg-cannot-verify-tint p-4 sm:p-5"
      >
        <div className="flex flex-col gap-1">
          <h3 className="flex items-center gap-2 text-sm font-medium text-cannot-verify">
            <Icon icon={CircleQuestionMark} />
            Identity {ambiguous ? "ambiguous" : "unresolved"} ·{" "}
            {plural(identity.candidates.length, "candidate")}
          </h3>
          <p className="max-w-(--layout-prose-max) text-dense text-ink">
            {identity.candidates.length > 0
              ? `DealProof found ${plural(identity.candidates.length, "possible legal entity", "possible legal entities")} matching this name and will not attach records until you confirm which company this is.`
              : "No legal entity could be matched to this name and website. Check the website on the case, or verify the company under its registered name."}
          </p>
          <p className="font-mono text-2xs text-ink-secondary">
            You entered: {detail.case.name}
            {detail.case.website ? ` · ${detail.case.website}` : null}
          </p>
        </div>

        {telling.length > 0 ? (
          <p className="text-dense text-ink">
            <span className="text-ink-secondary">What tells them apart: </span>
            {telling.map((row) => row.label.toLowerCase()).join(", ")}
          </p>
        ) : null}

        {identity.candidates.length > 0 ? (
          <ul
            className={cn(
              "grid gap-4",
              identity.candidates.length === 2 ? "lg:grid-cols-2" : "lg:grid-cols-2 2xl:grid-cols-3",
            )}
          >
            {identity.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.crustdata_company_id}
                candidate={candidate}
                rows={rows}
                onChoose={() => {
                  setError(null);
                  setChoosing(candidate);
                }}
              />
            ))}
          </ul>
        ) : null}
      </section>

      <section aria-label="Blocked until identity is resolved" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-medium text-ink">Blocked until identity is resolved</h3>
          <p className="max-w-(--layout-prose-max) text-dense text-ink-secondary">
            These checks depend on knowing the legal entity. None of them has run
          </p>
        </div>
        <HatchedBlock innerClassName="p-0">
          <ul className="divide-y divide-dashed divide-not-checked-line">
            {BLOCKED.map((item) => (
              <li
                key={item.segment}
                className="grid gap-x-6 gap-y-1 px-3 py-2 text-dense sm:grid-cols-[11rem_minmax(0,1fr)]"
              >
                <Link
                  href={`${basePath}/${item.segment}`}
                  className="self-start rounded-xs font-medium text-not-checked underline underline-offset-2"
                >
                  {item.label}
                </Link>
                <span className="text-ink-secondary">{item.note(detail)}</span>
              </li>
            ))}
          </ul>
        </HatchedBlock>
      </section>

      <Dialog open={choosing !== null} onOpenChange={(open) => (open ? null : setChoosing(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Attach this case to {choosing?.name}</DialogTitle>
            <DialogDescription>
              Every record in this case will be attached to this legal entity, and the choice
              is recorded under your name. Checks that were blocked can then run.
            </DialogDescription>
          </DialogHeader>
          {choosing ? (
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-dense">
              {[...choosing.matching, ...choosing.differing].map((item) => (
                <div key={item.key} className="contents">
                  <dt className="text-ink-muted">{item.label}</dt>
                  <dd className="break-all text-ink">{item.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {error ? (
            <p role="alert" className="text-dense text-contradicted">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button>Go back</Button>
            </DialogClose>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => (choosing ? void confirm(choosing) : undefined)}
            >
              {busy ? "Saving" : "This is the company"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Identity comes before everything else in a case. Confirmed shows the identifiers that
 * matched and their evidence. Ambiguous shows the candidates side by side, row for row,
 * with what tells them apart, and one action that records the choice.
 */
export function IdentityTab() {
  const detail = useCaseDetail();
  const confirmed = detail.identity.state === "confirmed";
  return (
    <div className="flex flex-col gap-6">
      <TabHeading
        title="Identity"
        summary={
          confirmed
            ? `${plural(detail.identity.keys.length, "matching identifier")} on record`
            : "Records are not attached until the legal entity is confirmed"
        }
      />
      {detail.identity.note && !confirmed ? (
        <p className="text-dense text-ink-secondary">{detail.identity.note}</p>
      ) : null}
      {confirmed ? <Confirmed detail={detail} /> : <Unresolved detail={detail} />}
    </div>
  );
}
