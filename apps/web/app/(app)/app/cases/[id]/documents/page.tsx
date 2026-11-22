import { Suspense } from "react";
import { DocumentsTab } from "@/components/case-b/tabs";

export default function DocumentsPage() {
  return (
    <Suspense>
      <DocumentsTab />
    </Suspense>
  );
}
