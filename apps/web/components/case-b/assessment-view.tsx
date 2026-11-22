"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AssessmentVersionOut, ClaimOut, PolicyOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import type { ClaimStatus } from "@/lib/types";
import { JudgmentPanel } from "@/components/dealproof/judgment-panel";
import { StatusMark } from "@/components/dealproof/status-mark";
import {
  ReadingOldVersionBanner,
  VersionDiff,
  VersionRail,
} from "@/components/dealproof/version-diff";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  CATEGORY_LABEL,
  COMPANY_TYPE_LABEL,
  claimNumbers,
  toAssessment,
  toDiff,
  toVersionMeta,
} from "./adapt";
import { Section, TextLink } from "./parts";

/** The status a claim held at a given assessment version. */
function statusAt(claim: ClaimOut, version: number): ClaimStatus {
  const earlier = claim.history
    .filter((check) => check.assessment_version != null && check.assessment_version <= version)
    .sort((a, b) => (b.assessment_version ?? 0) - (a.assessment_version ?? 0))[0];
  return earlier?.status ?? claim.status;
}

/**
 * Which profile the policy applied, and the checks that profile requires, each with where
 * it stands in this version. A check that is still open names the document that would
 * settle it.
 */
function ProfileChecks({
  version,
  claims,
  typeReason,
  typeRule,
}: {
  version: AssessmentVersionOut;
  claims: ClaimOut[];
  typeReason: string | null;
  typeRule: string | null;
}) {
  const sufficiency = version.judgments.evidence_sufficiency;
  const rows = sufficiency.required_categories.map((category) => {
    const settled = sufficiency.settled.find((item) => item.category === category);
    const item = settled ?? sufficiency.gaps.find((gap) => gap.category === category);
    return { category, item, settled: Boolean(settled) };
  });
  const type = version.company_type;

  return (
    <Section
      title={type ? `${COMPANY_TYPE_LABEL[type]} profile` : "Company-type profile"}
      meta={`${plural(rows.length, "required check")}`}
      lead={
        type ? (
          <>
            {typeReason ? `${typeReason}. ` : null}
            The profile decides which checks are required before a case can be prioritised.
            {typeRule ? ` Rule: ${typeRule}.` : null}
          </>
        ) : (
          "No company-type profile was applied to this version."
        )
      }
    >
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Required check</TableHead>
            <TableHead>Where it stands</TableHead>
            <TableHead>Claims</TableHead>
            <TableHead>What would settle it</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(({ category, item, settled }) => {
            const numbers = item ? claimNumbers(item.claim_ids, claims) : [];
            return (
              <TableRow key={category}>
                <TableCell className="text-ink">{CATEGORY_LABEL[category]}</TableCell>
                <TableCell>
                  {item?.status ? (
                    <StatusMark
                      status={item.status}
                      reason={claims.find((c) => item.claim_ids.includes(c.id))?.not_checked_reason}
                    />
                  ) : (
                    <span className="text-ink-secondary">No claim was made on this</span>
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs text-ink-secondary">
                  {numbers.length ? numbers.map((n) => `Claim ${n}`).join(", ") : "–"}
                </TableCell>
                <TableCell className="text-ink-secondary">
                  {settled ? "Settled" : (item?.settle_with ?? item?.note ?? "Not stated by the policy")}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Section>
  );
}

/**
 * The Assessment tab: five judgments kept apart, the profile they were judged under, and
 * the history. Any version opens read-only; the page says so while an old one is open.
 */
export function AssessmentView({
  caseId,
  versions,
  claims,
  viewing,
  typeReason,
  policy,
}: {
  caseId: string;
  /** Oldest first. */
  versions: AssessmentVersionOut[];
  claims: ClaimOut[];
  /** The version number open on the page. */
  viewing: number;
  typeReason: string | null;
  policy: PolicyOut | null;
}) {
  const router = useRouter();
  const [showUnchanged, setShowUnchanged] = useState(false);

  const latest = versions[versions.length - 1];
  const version = versions.find((item) => item.version === viewing) ?? latest;
  const isCurrent = version.version === latest.version;
  const diff = toDiff(version, claims);
  const changedIds = new Set(
    (version.diff_from_previous ?? []).filter((l) => l.kind === "claim").map((l) => l.subject_id),
  );
  const unchanged = claims.filter((claim) => !changedIds.has(claim.id));
  const base = `/app/cases/${caseId}/assessment`;

  return (
    <div className="flex flex-col gap-8">
      {isCurrent ? null : (
        <ReadingOldVersionBanner reading={version.version} current={latest.version}>
          <TextLink href={base}>Open current version</TextLink>
        </ReadingOldVersionBanner>
      )}

      <div className="flex flex-col gap-3">
        <JudgmentPanel assessment={toAssessment(version, claims)} />
        <p className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 text-xs text-ink-secondary">
          <span>
            Five judgments, kept apart. DealProof never blends them into one score. Fit measures
            match to your criteria and says nothing about returns
          </span>
          <TextLink href="/app/policy">Read scoring policy</TextLink>
        </p>
      </div>

      <ProfileChecks
        version={version}
        claims={claims}
        typeReason={typeReason}
        typeRule={policy?.company_type_rule ?? null}
      />

      <Section
        title="Assessment history"
        meta={plural(versions.length, "version")}
        lead="New evidence updates the assessment in the open. Earlier versions stay readable, and every change states its cause and source."
      >
        <div className="grid gap-6 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <VersionRail
            versions={versions.map(toVersionMeta)}
            current={latest.version}
            viewing={version.version}
            onOpen={(n) =>
              router.push(n === latest.version ? base : `${base}?v=${n}`, { scroll: false })
            }
            className="self-start rounded-lg border border-line bg-surface p-4"
          />

          <div className="flex min-w-0 flex-col gap-3">
            {diff ? (
              <>
                <VersionDiff
                  key={version.version}
                  diff={diff}
                  highlight={isCurrent}
                  onShowUnchanged={
                    unchanged.length > 0 && !showUnchanged ? () => setShowUnchanged(true) : undefined
                  }
                />
                {showUnchanged ? (
                  <div className="rounded-lg border border-line bg-surface">
                    <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2">
                      <h4 className="text-xs font-medium text-ink-secondary">
                        Unchanged in v{version.version}
                      </h4>
                      <button
                        type="button"
                        onClick={() => setShowUnchanged(false)}
                        className="rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
                      >
                        Hide
                      </button>
                    </div>
                    <ul className="flex flex-col divide-y divide-line text-dense">
                      {unchanged.map((claim) => (
                        <li
                          key={claim.id}
                          className="grid grid-cols-[4rem_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-2"
                        >
                          <span className="font-mono text-xs text-ink-muted">Claim {claim.number}</span>
                          <span className="truncate text-ink">“{claim.original_text}”</span>
                          <StatusMark
                            status={statusAt(claim, version.version)}
                            reason={claim.not_checked_reason}
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-secondary">
                Version {version.version} is the initial screening. There is no earlier version to
                compare it with.
              </p>
            )}
          </div>
        </div>
      </Section>
    </div>
  );
}
