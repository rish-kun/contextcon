import type { Metadata } from "next";
import { InvestorRunLog } from "@/components/investors/investor-run-log";

export const metadata: Metadata = { title: "Run log" };

export default async function InvestorRunLogPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InvestorRunLog id={id} />;
}
