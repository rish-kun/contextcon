import type { Metadata } from "next";
import { RunGallery } from "./run-gallery";

export const metadata: Metadata = {
  title: "Live run view · DealProof",
  description: "The live run view replaying each fixture run, live and as a log.",
  robots: { index: false },
};

export default function RunDesignPage() {
  return <RunGallery />;
}
