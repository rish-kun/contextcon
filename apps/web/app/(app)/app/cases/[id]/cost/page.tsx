import { Suspense } from "react";
import { CostTab } from "@/components/case/record-tabs";

export default function CostPage() {
  return (
    <Suspense>
      <CostTab />
    </Suspense>
  );
}
