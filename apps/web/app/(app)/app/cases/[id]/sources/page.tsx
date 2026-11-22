import { Suspense } from "react";
import { SourcesTab } from "@/components/case/record-tabs";

export default function SourcesPage() {
  return (
    <Suspense>
      <SourcesTab />
    </Suspense>
  );
}
