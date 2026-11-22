import { Suspense } from "react";
import { AssessmentTab } from "@/components/case-b/tabs";

export default function ShowcaseAssessmentPage() {
  return (
    <Suspense>
      <AssessmentTab />
    </Suspense>
  );
}
