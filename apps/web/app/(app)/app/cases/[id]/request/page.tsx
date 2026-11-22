import { Suspense } from "react";
import { RequestTab } from "@/components/case/record-tabs";

export default function RequestPage() {
  return (
    <Suspense>
      <RequestTab />
    </Suspense>
  );
}
