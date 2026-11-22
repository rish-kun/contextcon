import type { Metadata } from "next";
import { getShowcase } from "@/lib/api/client";
import { ThesisView } from "@/components/discover/thesis-view";

export const metadata: Metadata = { title: "Discovery" };

/** The showcase's real discovery run, read-only (the client reads the public route). */
export default async function ShowcaseDiscoveryPage() {
  const index = await getShowcase().catch(() => null);
  return <ThesisView thesisId={index?.thesis_id ?? "showcase"} live={false} />;
}
