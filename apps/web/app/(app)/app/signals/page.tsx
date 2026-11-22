import type { Metadata } from "next";
import { Suspense } from "react";
import { Signals } from "@/components/signals/signals";

export const metadata: Metadata = { title: "Signals" };

export default function SignalsPage() {
  return (
    <Suspense>
      <Signals />
    </Suspense>
  );
}
