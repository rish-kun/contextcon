import { Suspense } from "react";
import { CostTab } from "@/components/case-b/tabs";

export default function ShowcaseCostPage() {
  return (
    <Suspense>
      <CostTab />
    </Suspense>
  );
}
