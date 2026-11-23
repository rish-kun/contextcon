"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AssessmentVersionOut, ClaimOut, DocumentOut, PolicyOut } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { CLAIM_STATUSES, type ClaimStatus } from "@/lib/types";
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
import { TextLink } from "@/components/ui/link";
import {
  CATEGORY_LABEL,
  COMPANY_TYPE_LABEL,
  claimNumbers,
  toAssessment,
  toDiff,
  toVersionMeta,
} from "./adapt";
import { TabSection, TabStack, Why } from "./parts";

/**
 * The version that arrived while this view was open, or null. The one-time highlight on a
 * diff reports an arrival the reader watched; the version the view opened on is recorded
 * silently, so reopening the page never plays a change that already happened.
 */
function useArrivedVersion(latest: number): number | null {
  const [opened] = useState(latest);
  return latest > opened ? latest : null;
}

/**
 * The status a claim held at an assessment version, read from that version's own record:
 * the claim's checks up to it, or the outcome the version stored for its required checks.
 * Null when nothing shows the claim existed then, so a claim added in version 3 is not
 * drawn into version 1.
 */
function statusAt(claim: ClaimOut, version: AssessmentVersionOut, isLatest: boolean): ClaimStatus | null {
  const upTo = claim.history
    .filter((check) =>
      check.assessment_version != null
        ? check.assessment_version <= version.version
        : check.created_at <= version.created_at,
    )
    .sort(
      (a, b) =>
        (b.assessment_version ?? 0) - (a.assessment_version ?? 0) || b.created_at.localeCompare(a.created_at),
    )[0];
  if (upTo) return upTo.status;
  const sufficiency = version.judgments.evidence_sufficiency;
  const recorded = [...sufficiency.settled, ...sufficiency.gaps].find((item) => item.claim_ids.includes(claim.id));
  if (recorded?.status) return recorded.status;
  const line = (version.diff_from_previous ?? []).find((l) => l.kind === "claim" && l.subject_id === claim.id);
  if (line && (CLAIM_STATUSES as readonly string[]).includes(line.after ?? "")) return line.after as ClaimStatus;
  // The current version is what the ledger shows today.
  return isLatest ? claim.status : null;
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
  const settledCount = rows.filter((row) => row.settled).length;

  return (
    <TabSection
      title="Required checks"
      meta={`${type ? `${COMPANY_TYPE_LABEL[type]} profile · ` : ""}${settledCount} of ${rows.length} settled`}
      why={
        type ? (
          <>
            {typeReason ? <p>{typeReason}</p> : null}
            <p>The profile decides which checks are required before a case can be prioritised.</p>
            {typeRule ? <p>Rule: {typeRule}</p> : null}
          </>
        ) : (
          <p>No company-type profile was applied to this version.</p>
        )
      }
      flush
    >
      <Table density="compact" flush>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Check</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Claims</TableHead>
            <TableHead>Settled by</TableHead>
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
                    <span className="text-ink-secondary">No claim made</span>
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs text-ink-secondary">
                  {numbers.length ? numbers.join(", ") : "–"}
                </TableCell>
                <TableCell className="text-ink-secondary">
                  {settled ? "Settled" : (item?.settle_with ?? item?.note ?? "–")}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TabSection>
  );
}

/**
 * The Assessment tab: five judgments kept apart, the profile they were judged under, and
 * the history. Any version opens read-only; the page says so while an old one is open.
 */
export function AssessmentView({
  basePath: base,
  versions,
  claims,
  documents,
  viewing,
  typeReason,
  policy,
  decisionFlip,
}: {
  /** The DecisionFlip panel, drawn under the judgments of the current version. */
  decisionFlip?: React.ReactNode;
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
  const arrived = useArrivedVersion(latest.version);

  // The claims a version covers, each with the status that version recorded for it.
  const claimsAt = (item: AssessmentVersionOut) =>
    claims.flatMap((claim) => {
      const status = statusAt(claim, item, item.version === latest.version);
      return status ? [{ claim, status }] : [];
    });

  // One entry per version: its state, what arrived before it, and what that changed.
  const entries: TimelineEntry[] = versions.map((item) => {
    const then = claimsAt(item);
    const diff = toDiff(item, then.map((row) => row.claim));
    const meta = toVersionMeta(item);
    return {
      meta,
      state: versionState(
        then.map((row) => row.status),
        item.judgments.screening_disposition.disposition,
      ),
      cause: diff ? timelineCause(meta.trigger, item.trigger_document_ids, diff, documents) : null,
      diff,
    };
  });

  const unchangedFor = (n: number): UnchangedClaim[] => {
    const at = versions.find((item) => item.version === n);
    if (!at) return [];
    const changed = new Set(
      (at.diff_from_previous ?? []).filter((line) => line.kind === "claim").map((line) => line.subject_id),
    );
    return claimsAt(at)
      .filter((row) => !changed.has(row.claim.id))
      .map(({ claim, status }) => ({
        number: claim.number,
        text: claim.original_text,
        status,
        not_checked_reason: status === "not_checked" ? claim.not_checked_reason : null,
      }));
  };

  return (
    <TabStack>
      {isCurrent ? null : (
        <ReadingOldVersionBanner reading={version.version} current={latest.version}>
          <TextLink href={base}>Open current version</TextLink>
        </ReadingOldVersionBanner>
      )}

      <JudgmentPanel assessment={toAssessment(version, claims)} />
      <p className="flex flex-wrap items-center justify-end gap-x-4 px-1 text-xs text-ink-muted">
        <Why label="Why five judgments?">
          <p>
            The five judgments are kept apart and never blended into one score. Fit measures the match to
            your criteria and says nothing about returns.
          </p>
        </Why>
        <TextLink href="/app/policy">Scoring policy</TextLink>
      </p>

      {isCurrent ? decisionFlip : null}

      <ProfileChecks
        version={version}
        claims={claims}
        typeReason={typeReason}
        typeRule={policy?.company_type_rule ?? null}
      />

      <TabSection
        title="History"
        meta={plural(versions.length, "version")}
        why={
          <p>
            New evidence updates the assessment in the open. What arrived sits between two versions; under
            the newer one, the disposition and judgments come first, then each claim that moved on its own
            evidence. Claims that changed for one shared reason are a single row that opens. Earlier
            versions stay readable.
          </p>
        }
      >
        <ChangeTimeline
          entries={entries}
          current={latest.version}
          viewing={version.version}
          highlightVersion={arrived}
          unchangedFor={unchangedFor}
          onOpen={(n) =>
            router.push(n === latest.version ? base : `${base}?v=${n}`, { scroll: false })
          }
        />
      </TabSection>
    </TabStack>
  );
}
