import { Suspense } from "react";
import { DocumentsTab } from "@/components/case/record-tabs";

export default function ShowcaseDocumentsPage() {
  return (
    <Suspense>
      <DocumentsTab />
    </Suspense>
  );
}
