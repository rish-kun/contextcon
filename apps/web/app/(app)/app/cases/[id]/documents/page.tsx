import { Suspense } from "react";
import { DocumentsTab } from "@/components/case/record-tabs";

export default function DocumentsPage() {
  return (
    <Suspense>
      <DocumentsTab />
    </Suspense>
  );
}
