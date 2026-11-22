import type { Metadata } from "next";
import { Suspense } from "react";
import { Companies } from "@/components/companies/companies";

export const metadata: Metadata = { title: "Companies" };

export default function CompaniesPage() {
  return (
    <Suspense>
      <Companies />
    </Suspense>
  );
}
