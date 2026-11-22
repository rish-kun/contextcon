import type { Metadata } from "next";
import { getCase } from "@/lib/api/client";
import { usesBySource } from "@/components/case-b/adapt";
import { load } from "@/components/case-b/load";
import { EmptyState, LoadError, TabHeader } from "@/components/case-b/parts";
import { SourcesTable } from "@/components/case-b/sources-table";

export const metadata: Metadata = { title: "Sources · DealProof" };

export default async function SourcesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await load((init) => getCase(id, init));
  if (!detail.ok) return <LoadError what="the source record" status={detail.status} />;

  const { sources } = detail.data;
  if (sources.length === 0) {
    return (
      <EmptyState
        heading="No sources recorded yet"
        body="Sources appear here with their dates and retrieval times as soon as verification begins."
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <TabHeader
        title="Source record"
        lead="Everything DealProof read for this case: where it came from, the exact page or request, when it was retrieved and which facts rest on it. Enough to repeat the work and reach the same record."
      />
      <SourcesTable
        sources={sources}
        uses={Object.fromEntries(usesBySource(detail.data))}
        exportName={id}
      />
    </div>
  );
}
