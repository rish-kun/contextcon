import { Suspense } from "react";
import { CostTab } from "@/components/case-b/tabs";

export default function CostPage() {
  return (
    <Suspense>
      <CostTab />
    </Suspense>
  );
}
