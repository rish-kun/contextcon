import type { Metadata } from "next";
import { NewCaseForm } from "@/components/case/new-case-form";

export const metadata: Metadata = { title: "New case" };

export default function NewCasePage() {
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-medium text-ink">New case</h1>
        <p className="text-ink-secondary">
          Start verification for a company you already have in mind
        </p>
      </div>
      <div className="rounded-xl border border-line bg-surface p-5 sm:p-6">
        <NewCaseForm />
      </div>
    </div>
  );
}
