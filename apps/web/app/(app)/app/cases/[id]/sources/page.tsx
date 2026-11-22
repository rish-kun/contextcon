import { Suspense } from "react";
import { SourcesTab } from "@/components/case-b/tabs";

export default function SourcesPage() {
  return (
    <Suspense>
      <SourcesTab />
    </Suspense>
  );
}
