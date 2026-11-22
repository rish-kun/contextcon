import type { Metadata } from "next";
import { getCase } from "@/lib/api/client";
import { CostPanel } from "@/components/case-b/cost-panel";
import { load } from "@/components/case-b/load";
import { EmptyState, LoadError } from "@/components/case-b/parts";

export const metadata: Metadata = { title: "Cost · DealProof" };

export default async function CostPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await load((init) => getCase(id, init));
  if (!detail.ok) return <LoadError what="the cost record" status={detail.status} />;

  const { cost } = detail.data;
  const nothingYet =
    cost.by_step.length === 0 &&
    cost.crustdata_credits === 0 &&
    cost.llm_usd === 0 &&
    cost.unknown_cost_calls === 0 &&
    !cost.shared_discovery;

  if (nothingYet) {
    return (
      <EmptyState
        heading="No usage recorded yet"
        body="Credits and model usage appear here once a search or verification step runs."
      />
    );
  }
  return <CostPanel cost={cost} caseId={id} />;
}
