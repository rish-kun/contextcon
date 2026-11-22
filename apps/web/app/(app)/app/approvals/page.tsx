import type { Metadata } from "next";
import { Approvals } from "@/components/approvals/approvals";

export const metadata: Metadata = { title: "Approvals" };

export default function ApprovalsPage() {
  return <Approvals />;
}
