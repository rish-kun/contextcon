import { Suspense } from "react";
import { RequestTab } from "@/components/case-b/tabs";

export default function RequestPage() {
  return (
    <Suspense>
      <RequestTab />
    </Suspense>
  );
}
