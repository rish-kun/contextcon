import type { Metadata } from "next";
import { Gallery } from "./gallery";

export const metadata: Metadata = {
  title: "Component gallery · DealProof",
  description: "Every DealProof component in every state, shown with sample data.",
  robots: { index: false },
};

export default function DesignPage() {
  return <Gallery />;
}
