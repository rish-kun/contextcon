import type { Metadata } from "next";
import { Principles, ProfileForm } from "@/components/investors";

export const metadata: Metadata = { title: "Find investors · DealProof" };

const FIELDS = ["sector", "location", "stage", "size", "funding_sought"] as const;

export default async function NewInvestorSearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // "Edit search" links back here with the previous profile in the query string.
  const params = await searchParams;
  const initial: Partial<Record<(typeof FIELDS)[number], string>> = {};
  for (const field of FIELDS) {
    const value = params[field];
    if (typeof value === "string" && value) initial[field] = value;
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex max-w-2xl flex-col gap-1">
        <h1 className="text-2xl font-medium text-ink">Find investors</h1>
        <p className="text-sm text-ink-secondary">
          Describe the business and the funding it wants. DealProof finds comparable
          companies that have raised money, reads who invested in them and when, and groups
          those rounds by investor.
        </p>
      </header>
      <div className="grid items-start gap-x-12 gap-y-8 xl:grid-cols-[minmax(0,40rem)_minmax(0,22rem)]">
        <ProfileForm initial={initial} />
        <Principles />
      </div>
    </div>
  );
}
