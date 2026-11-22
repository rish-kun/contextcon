import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SearchesList } from "@/components/investors";

export const metadata: Metadata = { title: "Investors · DealProof" };

export default function InvestorsPage() {
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex max-w-2xl flex-col gap-1">
          <h1 className="text-2xl font-medium text-ink">Investors</h1>
          <p className="text-sm text-ink-secondary">
            Shortlists of investors who have backed comparable companies, each built from
            dated funding records.
          </p>
        </div>
        <Button asChild variant="primary">
          <Link href="/app/investors/new">Find investors</Link>
        </Button>
      </header>
      <SearchesList />
    </div>
  );
}
