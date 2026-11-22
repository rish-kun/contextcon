import { Suspense } from "react";
import { AssessmentTab } from "@/components/case/record-tabs";

export default function ShowcaseAssessmentPage() {
  return (
    <Suspense>
      <AssessmentTab />
    </Suspense>
  );
}
