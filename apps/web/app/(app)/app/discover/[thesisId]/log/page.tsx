import type { Metadata } from "next";
import { ThesisRunLog } from "@/components/discover/thesis-run-log";

export const metadata: Metadata = { title: "Run log" };

export default async function ThesisRunLogPage({ params }: { params: Promise<{ thesisId: string }> }) {
  const { thesisId } = await params;
  return <ThesisRunLog thesisId={thesisId} />;
}
