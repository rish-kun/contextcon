import { Suspense } from "react";
import { SourcesTab } from "@/components/case/record-tabs";

export default function ShowcaseSourcesPage() {
  return (
    <Suspense>
      <SourcesTab />
    </Suspense>
  );
}
