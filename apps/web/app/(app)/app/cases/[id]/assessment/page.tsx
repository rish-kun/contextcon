import { Suspense } from "react";
import { AssessmentTab } from "@/components/case/record-tabs";

export default function AssessmentPage() {
  return (
    <Suspense>
      <AssessmentTab />
    </Suspense>
  );
}
