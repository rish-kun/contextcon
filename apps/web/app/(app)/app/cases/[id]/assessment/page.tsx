import { Suspense } from "react";
import { AssessmentTab } from "@/components/case-b/tabs";

export default function AssessmentPage() {
  return (
    <Suspense>
      <AssessmentTab />
    </Suspense>
  );
}
