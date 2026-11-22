import type { Metadata } from "next";
import { getCase, listAssessments } from "@/lib/api/client";
import { DocumentsPanel } from "@/components/case-b/documents-panel";
import { load } from "@/components/case-b/load";
import { EmptyState, LoadError } from "@/components/case-b/parts";

export const metadata: Metadata = { title: "Documents · DealProof" };

export default async function DocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [detail, history] = await Promise.all([
    load((init) => getCase(id, init)),
    load((init) => listAssessments(id, init)),
  ]);
  if (!detail.ok) return <LoadError what="the documents" status={detail.status} />;

  const { documents, deletions, request_list } = detail.data;
  if (documents.length === 0 && deletions.length === 0) {
    return (
      <EmptyState
        heading="No files on this case"
        body="Seller documents you upload appear here with the date they will be deleted. They are used only for this case."
        action={{ href: `/app/cases/${id}/claims`, label: "Go to claims" }}
      />
    );
  }

  return (
    <DocumentsPanel
      caseId={id}
      documents={documents}
      deletions={deletions}
      requestList={request_list}
      versions={history.ok ? history.data : []}
    />
  );
}
