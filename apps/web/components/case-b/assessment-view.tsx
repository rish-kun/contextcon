"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { AssessmentVersionOut, ClaimOut, DocumentOut, PolicyOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import type { ClaimStatus } from "@/lib/types";
import { JudgmentPanel } from "@/components/dealproof/judgment-panel";
import { StatusMark } from "@/components/dealproof/status-mark";
import { ReadingOldVersionBanner } from "@/components/dealproof/version-diff";
import { ChangeTimeline, type UnchangedClaim } from "@/components/explainers/change-timeline";
import { timelineCause, versionState, type TimelineEntry } from "@/components/explainers/derive";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CATEGORY_LABEL } from "@/components/case/adapt";
import {
  COMPANY_TYPE_LABEL,
  claimNumbers,
  toAssessment,
  toDiff,
  toVersionMeta,
} from "./adapt";
import { Section, TextLink } from "./parts";

const SEEN_KEY = "dealproof:seen-assessment-version";

function readSeen(): Record<string, number> {
  try {
    return JSON.parse(window.localStorage.getItem(SEEN_KEY) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

/**
 * The version this reader has not seen before, or null. The one-time highlight on a diff
 * reports that a version arrived since the reader last looked, so it is taken from a
 * record kept in the browser and never from a mount: a first visit records the version
 * silently, and reopening the same diff later shows it still.
 */
function useUnseenVersion(caseId: string, latest: number): number | null {
  const [unseen, setUnseen] = useState<number | null>(null);
  useEffect(() => {
    const seen = readSeen();
    const before = seen[caseId];
    if (before === latest) return;
    try {
      window.localStorage.setItem(SEEN_KEY, JSON.stringify({ ...seen, [caseId]: latest }));
    } catch {
      /* storage unavailable: nothing is highlighted, nothing is lost */
    }
    // Reading the browser's record is the external sync this effect exists for.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (before !== undefined && latest > before) setUnseen(latest);
  }, [caseId, latest]);
  return unseen;
}

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
  basePath: base,
  versions,
  claims,
  documents,
  viewing,
  typeReason,
  policy,
}: {
  /** Keys the reader's record of versions already seen. */
  caseId: string;
  /** `/app/cases/{id}/assessment` */
  basePath: string;
  /** Oldest first. */
  versions: AssessmentVersionOut[];
  claims: ClaimOut[];
  /** The case's uploads, so a version can name the document that caused it. */
  documents: DocumentOut[];
  /** The version number open on the page. */
  viewing: number;
  typeReason: string | null;
  policy: PolicyOut | null;
}) {
  const router = useRouter();

  const latest = versions[versions.length - 1];
  const version = versions.find((item) => item.version === viewing) ?? latest;
  const isCurrent = version.version === latest.version;
  const unseen = useUnseenVersion(caseId, latest.version);

  // One entry per version: its state, what arrived before it, and what that changed.
  const entries: TimelineEntry[] = versions.map((item) => {
    const diff = toDiff(item, claims);
    const meta = toVersionMeta(item);
    return {
      meta,
      state: versionState(
        claims.map((claim) => statusAt(claim, item.version)),
        item.judgments.screening_disposition.disposition,
      ),
      cause: diff ? timelineCause(meta.trigger, item.trigger_document_ids, diff, documents) : null,
      diff,
    };
  });

  const unchangedFor = (n: number): UnchangedClaim[] => {
    const changed = new Set(
      (versions.find((item) => item.version === n)?.diff_from_previous ?? [])
        .filter((line) => line.kind === "claim")
        .map((line) => line.subject_id),
    );
    return claims
      .filter((claim) => !changed.has(claim.id))
      .map((claim) => ({
        number: claim.number,
        text: claim.original_text,
        status: statusAt(claim, n),
        not_checked_reason: claim.not_checked_reason,
      }));
  };

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
        lead="New evidence updates the assessment in the open. What arrived sits between two versions; under the newer one, each claim that moved is followed by what moved because of it. Earlier versions stay readable."
      >
        <ChangeTimeline
          entries={entries}
          current={latest.version}
          viewing={version.version}
          highlightVersion={unseen}
          unchangedFor={unchangedFor}
          onOpen={(n) =>
            router.push(n === latest.version ? base : `${base}?v=${n}`, { scroll: false })
          }
        />
      </Section>
    </div>
  );
}
