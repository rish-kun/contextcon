import type { Metadata } from "next";
import { ThesisList } from "@/components/discover/thesis-list";

export const metadata: Metadata = { title: "Discover · DealProof" };

export default function DiscoverIndexPage() {
  return <ThesisList />;
}
