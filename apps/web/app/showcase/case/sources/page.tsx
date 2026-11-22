import { Suspense } from "react";
import { SourcesTab } from "@/components/case-b/tabs";

export default function ShowcaseSourcesPage() {
  return (
    <Suspense>
      <SourcesTab />
    </Suspense>
  );
}
