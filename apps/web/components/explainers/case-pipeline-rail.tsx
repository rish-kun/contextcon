"use client";

import { statusCounts } from "@/components/case/adapt";
import { useCase } from "@/components/case/case-context";
import { cn } from "@/lib/utils";
import { pipelineStations } from "./derive";
import { PipelineRail } from "./pipeline-rail";

/**
 * The pipeline rail for the case on screen, read from the shared case loader. Mounted in
 * the case header, so it is the same on every tab.
 */
export function CasePipelineRail({ className }: { className?: string }) {
  const { detail, basePath, run, runActive } = useCase();
  if (!detail) return null;

  const { assessment, message, request_list: list, opportunity } = detail;
  const stations = pipelineStations({
    basePath,
    created_at: detail.case.created_at,
    owner_name: detail.case.owner.display_name,
    thesis_id: detail.case.thesis_id,
    identity_confirmed: detail.identity.state === "confirmed",
    runs: detail.runs,
    live_run_kind: runActive && run ? run.kind : null,
    claim_counts: statusCounts(detail.claims),
    assessment: assessment
      ? {
          version: assessment.version,
          created_at: assessment.created_at,
          disposition: assessment.judgments.screening_disposition.disposition,
          assessable_share:
            opportunity.criterion_results.length > 0 ? opportunity.assessable_pct / 100 : null,
        }
      : null,
    request: list
      ? {
          status: message?.status ?? "draft",
          documents: list.items.length,
          at: message?.send?.completed_at ?? message?.approval?.approved_at ?? null,
        }
      : null,
  });

  return (
    <PipelineRail
      stations={stations}
      className={cn("rounded-lg border border-line bg-surface p-4", className)}
    />
  );
}
