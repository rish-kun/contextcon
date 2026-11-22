import type { Metadata } from "next";
import { Pipeline } from "@/components/pipeline/pipeline";

export const metadata: Metadata = { title: "Pipeline" };

export default function PipelinePage() {
  return <Pipeline />;
}
