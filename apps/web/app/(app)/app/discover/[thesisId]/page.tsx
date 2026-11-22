import type { Metadata } from "next";
import { ThesisView } from "@/components/discover/thesis-view";

export const metadata: Metadata = { title: "Shortlist · DealProof" };

/**
 * `?live=1` is set by the criteria step when it has just started the run, so the page
 * follows that run from its first step.
 */
export default async function ThesisPage({
  params,
  searchParams,
}: {
  params: Promise<{ thesisId: string }>;
  searchParams: Promise<{ live?: string | string[] }>;
}) {
  const [{ thesisId }, { live }] = await Promise.all([params, searchParams]);
  return <ThesisView thesisId={thesisId} live={live === "1"} />;
}
