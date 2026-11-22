import { Suspense } from "react";
import { RequestTab } from "@/components/case/record-tabs";

export default function ShowcaseRequestPage() {
  return (
    <Suspense>
      <RequestTab />
    </Suspense>
  );
}
