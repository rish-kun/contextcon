"use client";

import { BadgeCheck, CircleQuestionMark, Play, Printer, RotateCw } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  CostReadout,
  CriteriaStrip,
  DispositionStamp,
  StatusCounts,
} from "@/components/dealproof";
import { Button, Icon } from "@/components/ui";
import { statusCounts, toCaseCost, toFit } from "./adapt";
import { useCase } from "./case-context";
import { CaseRun } from "./case-run";
import { ProfileBand, profileSummary } from "./profile-band";

/** Why fit carries no number, in a few words. The longer reason is the hint. */
const FIT_STATE_NOTE: Record<
  Exclude<CaseDetail["opportunity"]["fit_state"], "scored">,
  { text: string; why: string }
> = {
  unavailable: { text: "Fit not scored", why: "None of the criteria could be assessed from the records found" },
  awaiting_strategy_criteria: { text: "No criteria yet", why: "Fit is scored against a thesis. This case was opened without one" },
  identity_unresolved: { text: "Fit waits on identity", why: "Fit is scored once the legal entity is confirmed" },
};

const cell = "flex min-w-0 flex-col items-start justify-center gap-1 px-4 py-3";
const cellLink =
  "rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover print:hidden";

function IdentityCell({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const { identity } = detail;
  if (identity.state === "confirmed") {
    const keys = identity.keys.map((key) => key.label.toLowerCase());
    return (
      <div className={cell}>
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Icon icon={BadgeCheck} className="shrink-0" />
          Identity confirmed
        </p>
        <p className="text-xs text-ink-secondary">
          {keys.length > 0 ? `Matched on ${keys.join(", ")}` : "Matching keys not recorded"}
          {" · "}
          <Link href={`${basePath}/identity`} className={cellLink}>
            Evidence
          </Link>
        </p>
      </div>
    );
  }
  const ambiguous = identity.state === "ambiguous";
  return (
    <div className={cell}>
      <p className="flex items-center gap-2 text-sm font-medium text-cannot-verify">
        <Icon icon={CircleQuestionMark} className="shrink-0" />
        Identity {ambiguous ? "ambiguous" : "unresolved"}
        {identity.candidates.length > 0 ? (
          <span className="font-normal"> · {plural(identity.candidates.length, "candidate")}</span>
        ) : null}
      </p>
      <p className="text-xs text-ink-secondary">
        Checks are paused ·{" "}
        <Link href={`${basePath}/identity`} className={cellLink}>
          Resolve identity
        </Link>
      </p>
    </div>
  );
}

function FitCell({ detail }: { detail: CaseDetail }) {
  const { opportunity } = detail;
  if (opportunity.fit_state !== "scored" && opportunity.criterion_results.length === 0) {
    const note = FIT_STATE_NOTE[opportunity.fit_state];
    return (
      <div className={cell}>
        <p className="text-sm font-medium text-ink" title={note.why}>
          {note.text}
        </p>
        <p className="text-xs text-ink-secondary">
          {opportunity.fit_state === "identity_unresolved" ? (
            note.why
          ) : (
            <Link href="/app/discover/new" className={cellLink}>
              Add criteria with a screening
            </Link>
          )}
        </p>
      </div>
    );
  }
  return (
    <div className={cell}>
      <CriteriaStrip
        fit={toFit(opportunity)}
        size="compact"
        className="w-full flex-col items-stretch gap-2"
      />
    </div>
  );
}

function DispositionCell({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const assessment = detail.assessment;
  if (!assessment) {
    if (detail.identity.state !== "confirmed") {
      return (
        <div className={cell}>
          <DispositionStamp disposition="cannot_assess" />
          <p className="text-xs text-ink-secondary">Identity is not confirmed</p>
        </div>
      );
    }
    return (
      <div className={cell}>
        <p className="rounded-sm border border-dashed border-not-checked-line bg-not-checked-tint px-2 py-0.5 text-sm font-medium text-not-checked">
          Not assessed yet
        </p>
        <p className="text-xs text-ink-secondary">Run verification to produce version 1</p>
      </div>
    );
  }
  const { disposition, reasons } = assessment.judgments.screening_disposition;
  return (
    <div className={cell}>
      <DispositionStamp disposition={disposition} />
      <p className="text-xs text-ink-secondary" title={reasons.map((reason) => reason.text).join(". ")}>
        <span className="line-clamp-1">{reasons[0]?.text}</span>
        <Link href={`${basePath}/assessment`} className={cellLink}>
          {reasons.length > 1 ? `All ${reasons.length} reasons` : "Assessment"}
        </Link>
      </p>
    </div>
  );
}

function ClaimsCell({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const counts = statusCounts(detail.claims);
  const settled = detail.claims.length - counts.not_checked;
  if (detail.claims.length === 0) {
    return (
      <div className={cell}>
        <p className="text-sm font-medium text-ink">No claims yet</p>
        <p className="text-xs text-ink-secondary">
          <Link href={`${basePath}/claims`} className={cellLink}>
            Add a claim or a seller document
          </Link>
        </p>
      </div>
    );
  }
  return (
    <div className={cell}>
      <StatusCounts counts={counts} />
      <p className="font-mono text-xs text-ink-secondary">
        {settled} of {detail.claims.length} settled
        {counts.not_checked > 0 ? (
          <>
            {" · "}
            <Link href={`${basePath}/claims?status=not_checked`} className={cn(cellLink, "font-sans")}>
              {counts.not_checked} not run
            </Link>
          </>
        ) : null}
      </p>
    </div>
  );
}

/**
 * The case header: who the company is, whether that is confirmed, what the screening
 * says, how much of it could be assessed, and what did not run. It is the same on every
 * tab, so nothing on a tab has to repeat it.
 */
export function CaseHeader({ detail }: { detail: CaseDetail }) {
  const { basePath, runActive, verify, readOnly } = useCase();
  const pathname = usePathname();
  const router = useRouter();
  const assessment = detail.assessment;
  const identityOpen = detail.identity.state !== "confirmed";
  const hasRun = detail.runs.length > 0 || detail.case.run != null;

  function printMemo() {
    if (pathname === basePath) window.print();
    else router.push(`${basePath}?print=1`);
  }

  const summary = profileSummary(detail.profile);

  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 lg:flex-nowrap">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-medium text-ink">{detail.case.name}</h1>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-dense text-ink-secondary">
            {summary ? <span>{summary}</span> : null}
            <span className="flex flex-wrap items-center gap-x-3 font-mono text-xs">
              {detail.case.website ? <span>{detail.case.website}</span> : null}
              {assessment ? (
                <span>
                  v{assessment.version} · {formatDate(assessment.created_at)}
                </span>
              ) : null}
              <CostReadout cost={toCaseCost(detail.cost)} variant="compact" />
            </span>
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 print:hidden">
          {readOnly ? null : (
            <Button
              className="h-11 md:h-9"
              onClick={() => void verify()}
              disabled={runActive || identityOpen}
              title={identityOpen ? "Resolve identity before running checks" : undefined}
            >
              <Icon icon={hasRun ? RotateCw : Play} />
              {runActive ? "Verification running" : hasRun ? "Re-run verification" : "Run verification"}
            </Button>
          )}
          <Button className="h-11 md:h-9" onClick={printMemo}>
            <Icon icon={Printer} />
            Print memo
          </Button>
        </div>
      </div>

      <div
        className={cn(
          "grid divide-y divide-line overflow-hidden rounded-lg border bg-surface sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4",
          identityOpen ? "border-cannot-verify" : "border-line",
        )}
      >
        <DispositionCell detail={detail} basePath={basePath} />
        <IdentityCell detail={detail} basePath={basePath} />
        <FitCell detail={detail} />
        <ClaimsCell detail={detail} basePath={basePath} />
      </div>

      <ProfileBand detail={detail} />

      <CaseRun />
    </header>
  );
}
