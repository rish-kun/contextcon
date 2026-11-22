import type { Metadata } from "next";
import { getCase, getPolicy, listAssessments } from "@/lib/api/client";
import { AssessmentView } from "@/components/case-b/assessment-view";
import { load } from "@/components/case-b/load";
import { EmptyState, LoadError } from "@/components/case-b/parts";

export const metadata: Metadata = { title: "Assessment · DealProof" };

export default async function AssessmentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ v?: string }>;
}) {
  const [{ id }, { v }] = await Promise.all([params, searchParams]);
  const [detail, history, policy] = await Promise.all([
    load((init) => getCase(id, init)),
    load((init) => listAssessments(id, init)),
    load((init) => getPolicy(init)),
  ]);

  if (!detail.ok) return <LoadError what="the assessment" status={detail.status} />;
  if (!history.ok) return <LoadError what="the assessment history" status={history.status} />;

  const versions = [...history.data].sort((a, b) => a.version - b.version);
  if (versions.length === 0) {
    return (
      <EmptyState
        heading="Not assessed yet"
        body={
          detail.data.case.identity_state === "confirmed"
            ? "The five judgments appear here once verification has run on this case."
            : "DealProof does not judge a company it has not identified. Resolve the identity first; until then the disposition is Cannot assess."
        }
        action={
          detail.data.case.identity_state === "confirmed"
            ? { href: `/app/cases/${id}/claims`, label: "Go to claims" }
            : { href: `/app/cases/${id}/identity`, label: "Resolve identity" }
        }
      />
    );
  }

  const latest = versions[versions.length - 1].version;
  const asked = Number(v);
  const viewing = versions.some((item) => item.version === asked) ? asked : latest;

  return (
    <AssessmentView
      caseId={id}
      versions={versions}
      claims={detail.data.claims}
      viewing={viewing}
      typeReason={detail.data.profile?.company_type_reason ?? null}
      policy={policy.ok ? policy.data : null}
    />
  );
}
