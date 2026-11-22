"use client";

import { BadgeCheck, CircleQuestionMark, Play, Printer, RotateCw } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  CostReadout,
  CriteriaStrip,
  DispositionStamp,
  RunProgress,
  StatusCounts,
} from "@/components/dealproof";
import { Button, Icon } from "@/components/ui";
import { statusCounts, toCaseCost, toFit, toRun } from "./adapt";
import { useCase } from "./case-context";

/** Why fit carries no number, in the reader's terms. */
const FIT_STATE_NOTE: Record<Exclude<CaseDetail["opportunity"]["fit_state"], "scored">, string> = {
  unavailable: "Fit unavailable · none of the criteria could be assessed",
  awaiting_strategy_criteria: "Fit not scored · this case has no criteria yet",
  identity_unresolved: "Fit not scored · waiting on identity",
};

function IdentityCell({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const { identity } = detail;
  if (identity.state === "confirmed") {
    const keys = identity.keys.map((key) => key.label.toLowerCase());
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Icon icon={BadgeCheck} className="shrink-0" />
          Identity confirmed
        </p>
        <p className="text-dense text-ink-secondary">
          {keys.length > 0 ? `Matched on ${keys.join(", ")}` : "Matching keys not recorded"}
        </p>
        <Link
          href={`${basePath}/identity`}
          className="self-start rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover print:hidden"
        >
          See the evidence
        </Link>
      </div>
    );
  }
  const ambiguous = identity.state === "ambiguous";
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <p className="flex items-center gap-2 text-sm font-medium text-cannot-verify">
        <Icon icon={CircleQuestionMark} className="shrink-0" />
        Identity {ambiguous ? "ambiguous" : "unresolved"}
        {identity.candidates.length > 0 ? (
          <span className="font-normal"> · {plural(identity.candidates.length, "candidate")}</span>
        ) : null}
      </p>
      <p className="text-dense text-ink-secondary">
        No record is attached on a matching name alone. Checks that depend on identity are
        paused
      </p>
      <Link
        href={`${basePath}/identity`}
        className="self-start rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover print:hidden"
      >
        Resolve identity
      </Link>
    </div>
  );
}

function FitCell({ detail }: { detail: CaseDetail }) {
  const { opportunity } = detail;
  if (opportunity.fit_state !== "scored" && opportunity.criterion_results.length === 0) {
    return (
      <p className="font-mono text-sm font-medium text-ink">
        {FIT_STATE_NOTE[opportunity.fit_state]}
      </p>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <CriteriaStrip
        fit={toFit(opportunity)}
        size="compact"
        className="flex-col items-stretch gap-2"
      />
      <p className="text-xs text-ink-muted">
        Fit measures match to your criteria. It says nothing about returns
      </p>
    </div>
  );
}

function DispositionCell({ detail, basePath }: { detail: CaseDetail; basePath: string }) {
  const assessment = detail.assessment;
  if (!assessment) {
    if (detail.identity.state !== "confirmed") {
      return (
        <div className="flex flex-col items-start gap-2">
          <DispositionStamp disposition="cannot_assess" size="header" />
          <p className="text-dense text-ink">Identity is not confirmed, so nothing can be judged</p>
        </div>
      );
    }
    return (
      <p className="hatch self-start rounded-sm border border-dashed border-not-checked-line px-3 py-2 text-dense font-medium text-not-checked">
        Not assessed yet · run verification to produce version 1
      </p>
    );
  }
  const { disposition, reasons } = assessment.judgments.screening_disposition;
  return (
    <div className="flex min-w-0 flex-col items-start gap-2">
      <DispositionStamp disposition={disposition} size="header" />
      <ul className="flex flex-col gap-1 text-dense text-ink">
        {reasons.slice(0, 3).map((reason) => (
          <li key={reason.text}>{reason.text}</li>
        ))}
      </ul>
      <Link
        href={`${basePath}/assessment`}
        className="rounded-xs font-mono text-2xs text-ink-secondary underline underline-offset-2 transition-colors hover:text-ink print:hidden"
      >
        policy {assessment.policy_version}
      </Link>
    </div>
  );
}

function LiveRun() {
  const { run, runActive, runError, basePath } = useCase();
  const [now, setNow] = useState(() => Date.now());
  // The finished line stays only for a run this session watched, so a past run adds no noise.
  const [watched, setWatched] = useState<string | null>(null);

  useEffect(() => {
    if (!runActive) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [runActive]);

  if (runActive && run && watched !== run.id) setWatched(run.id);

  return (
    <>
      {runError ? (
        <p role="alert" className="text-dense text-contradicted">
          The run did not start: {runError}
        </p>
      ) : null}
      {run && (runActive || watched === run.id) ? (
        <RunProgress run={toRun(run, now)} logHref={`${basePath}/cost`} className="print:hidden" />
      ) : null}
    </>
  );
}

/**
 * The case header: who the company is, whether that is confirmed, what the screening
 * says, how much of it could be assessed, and what did not run. It is the same on every
 * tab, so nothing on a tab has to repeat it.
 */
export function CaseHeader({ detail }: { detail: CaseDetail }) {
  const { basePath, runActive, verify } = useCase();
  const pathname = usePathname();
  const router = useRouter();
  const counts = statusCounts(detail.claims);
  const settled = detail.claims.length - counts.not_checked;
  const assessment = detail.assessment;
  const identityOpen = detail.identity.state !== "confirmed";
  const hasRun = detail.runs.length > 0 || detail.case.run != null;

  function printMemo() {
    if (pathname === basePath) window.print();
    else router.push(`${basePath}?print=1`);
  }

  return (
    <header className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-medium text-ink">{detail.case.name}</h1>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-secondary">
            {detail.case.website ? <span>{detail.case.website}</span> : null}
            <span>
              {assessment
                ? `v${assessment.version} · ${formatDate(assessment.created_at)}`
                : "No assessment version yet"}
            </span>
            <CostReadout cost={toCaseCost(detail.cost)} variant="compact" />
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <Button
            className="h-11 md:h-9"
            onClick={() => void verify()}
            disabled={runActive || identityOpen}
            title={identityOpen ? "Resolve identity before running checks" : undefined}
          >
            <Icon icon={hasRun ? RotateCw : Play} />
            {runActive ? "Verification running" : hasRun ? "Re-run verification" : "Run verification"}
          </Button>
          <Button className="h-11 md:h-9" onClick={printMemo}>
            <Icon icon={Printer} />
            Print memo
          </Button>
        </div>
      </div>

      <div
        className={cn(
          "grid gap-x-8 gap-y-4 rounded-lg border bg-surface p-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)_minmax(0,5fr)]",
          identityOpen ? "border-cannot-verify" : "border-line",
        )}
      >
        <IdentityCell detail={detail} basePath={basePath} />
        <FitCell detail={detail} />
        <DispositionCell detail={detail} basePath={basePath} />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {detail.claims.length > 0 ? (
          <>
            <StatusCounts counts={counts} />
            <p className="font-mono text-xs text-ink-secondary">
              {settled} of {plural(detail.claims.length, "claim")} settled
              {counts.not_checked > 0 ? ` · ${counts.not_checked} not checked` : null}
            </p>
          </>
        ) : (
          <p className="text-dense text-ink-secondary">No claims on file yet</p>
        )}
        {counts.not_checked > 0 ? (
          <p className="hatch flex items-center gap-2 rounded-sm border border-dashed border-not-checked-line px-2 py-0.5 text-dense font-medium text-not-checked">
            {counts.not_checked === 1
              ? "1 check was not run"
              : `${counts.not_checked} checks were not run`}
            <Link
              href={`${basePath}/claims?status=not_checked`}
              className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover print:hidden"
            >
              View
            </Link>
          </p>
        ) : null}
      </div>

      <LiveRun />
    </header>
  );
}
