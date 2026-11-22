import { Suspense } from "react";
import { DocumentsTab } from "@/components/case-b/tabs";

export default function ShowcaseDocumentsPage() {
  return (
    <Suspense>
      <DocumentsTab />
    </Suspense>
  );
}
