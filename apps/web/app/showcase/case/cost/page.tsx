import { Suspense } from "react";
import { CostTab } from "@/components/case/record-tabs";

export default function ShowcaseCostPage() {
  return (
    <Suspense>
      <CostTab />
    </Suspense>
  );
}
